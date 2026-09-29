"""SIMULAÇÃO: análise de sensibilidade dos parâmetros do pipeline (pendência #4, T5).

Mede como o resultado do pipeline muda com `eps_metros` e `min_confirmacoes`, sobre a
MESMA simulação (mesma semente e opções de `gerar_dados_sinteticos`). Para cada
combinação da grade `GRADE_EPS_METROS` × `GRADE_MIN_CONFIRMACOES` (minpoints fica o
da configuração), conta: barreiras confirmadas e pendentes obtidas × esperadas,
acerto por categoria, grupos fragmentados, fusões indevidas (uma barreira com alertas
de mais de um grupo verdadeiro) e ruído classificado como barreira.

Uso (a partir de `backend/`):

    uv run python -m scripts.analisar_sensibilidade

Saída: tabela rotulada "SIMULAÇÃO" no console e
`backend/scripts/saida/sensibilidade-semente-<N>.csv` (cada linha com a coluna
`rotulo`, para que nenhum recorte do CSV perca a marca de simulação).

Honestidade do que fica no banco (G10, R14):

1. Apaga os dados de simulação existentes (como `--limpar`), gera a simulação UMA
   vez e faz commit.
2. Cada combinação da grade roda dentro de uma transação DESFEITA (rollback): as
   medições são lidas dentro dela e nada fica gravado, nem em `barreiras` nem em
   `execucoes_pipeline`.
3. No fim, roda o pipeline UMA vez com os parâmetros da CONFIGURAÇÃO e faz commit.

Assim o banco, `execucoes_pipeline` e `GET /validacao/estatisticas?origem=simulacao`
(e a figura do funil, que lê as estatísticas) correspondem sempre à rodada da
configuração, nunca a uma combinação da grade. Os dados reais nunca são tocados.
"""

import argparse
import csv
import math
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import Connection

from app.config import Configuracoes, obter_configuracoes
from app.validacao.pipeline import executar_pipeline
from scripts.gerar_dados_sinteticos import (
    DIRETORIO_SAIDA,
    ORIGEM,
    ROTULO_SIMULACAO,
    Avaliacao,
    ItemGerado,
    ItemRegistrado,
    OpcoesGeracao,
    adicionar_opcoes_de_geracao,
    avaliar,
    cabecalho_simulacao,
    caminho_para_exibir,
    formatar_execucao,
    formatar_metros,
    formatar_tabela,
    formatar_taxa,
    gerar_populacoes,
    ler_estado_final,
    ler_tipos_ativos,
    limpar_simulacao,
    opcoes_dos_argumentos,
    registrar_populacoes,
)

# Grade da análise (Task 4). eps em METROS, medido no SRID de cálculo (G6).
GRADE_EPS_METROS = (2, 4, 8, 12, 20)
GRADE_MIN_CONFIRMACOES = (2, 3, 4)

_CATEGORIAS_DENTRO = ("aglomerado", "sessao_repetida", "ruido")


@dataclass(frozen=True)
class RodadaSensibilidade:
    """Uma combinação da grade e a avaliação medida dentro da transação desfeita."""

    eps_metros: float
    min_pontos: int
    min_confirmacoes: int
    avaliacao: Avaliacao


def analisar_grade(
    conexao: Connection,
    registrados: Sequence[ItemRegistrado],
    *,
    grade_eps_metros: Sequence[float],
    grade_min_confirmacoes: Sequence[int],
    min_pontos: int,
    srid_calculo: int,
    srid_armazenamento: int,
) -> list[RodadaSensibilidade]:
    """Roda o pipeline da simulação para cada combinação e avalia o resultado.

    Cada rodada fica dentro de `conexao.transaction(force_rollback=True)`: com a
    conexão ociosa isso é um BEGIN … ROLLBACK; dentro de uma transação já aberta
    (a fixture dos testes), um SAVEPOINT desfeito. Nos dois casos a rodada não
    deixa rastro. Como o pipeline reconstrói tudo do zero (D6), cada rodada começa
    do mesmo estado.
    """
    rodadas: list[RodadaSensibilidade] = []
    for eps_metros in grade_eps_metros:
        for min_confirmacoes in grade_min_confirmacoes:
            with conexao.transaction(force_rollback=True):
                executar_pipeline(
                    conexao,
                    origem=ORIGEM,
                    eps_metros=eps_metros,
                    min_pontos=min_pontos,
                    min_confirmacoes=min_confirmacoes,
                    srid_calculo=srid_calculo,
                    srid_armazenamento=srid_armazenamento,
                )
                avaliacao = avaliar(
                    registrados, ler_estado_final(conexao), min_confirmacoes=min_confirmacoes
                )
            rodadas.append(RodadaSensibilidade(eps_metros, min_pontos, min_confirmacoes, avaliacao))
    return rodadas


@dataclass(frozen=True)
class DistanciasDeReferencia:
    """Distâncias da simulação que explicam a tabela (metros, plano local).

    Com minpoints = 2, todo alerta com um vizinho a até eps é núcleo, e o DBSCAN
    liga vizinhos de vizinhos. Então:

    - `maior_salto_dentro_de_grupo_metros`: no pior grupo, a maior aresta da árvore
      geradora mínima dos seus relatos. eps abaixo disso DIVIDE esse grupo.
    - `menor_entre_grupos_metros`: menor distância entre relatos de grupos
      diferentes do mesmo tipo. eps a partir disso FUNDE dois grupos.
    - `menor_do_ruido_metros`: menor distância de um ruído a outro relato do mesmo
      tipo. eps a partir disso transforma ruído em barreira.

    `None` quando não há par para medir.
    """

    maior_salto_dentro_de_grupo_metros: float | None
    menor_entre_grupos_metros: float | None
    menor_do_ruido_metros: float | None


def distancias_de_referencia(itens: Sequence[ItemGerado]) -> DistanciasDeReferencia:
    """Calcula as `DistanciasDeReferencia` dos itens que entram no agrupamento
    (grupos e ruído; fora da área e inválidos nunca chegam ao DBSCAN), sempre entre
    itens do MESMO tipo, porque o DBSCAN agrupa por tipo."""
    dentro = [item for item in itens if item.categoria in _CATEGORIAS_DENTRO]

    pontos_do_grupo: dict[tuple[str, int], list[ItemGerado]] = defaultdict(list)
    for item in dentro:
        if item.grupo is not None:
            pontos_do_grupo[(item.categoria, item.grupo)].append(item)
    saltos = [_maior_salto_da_arvore(pontos) for pontos in pontos_do_grupo.values()]

    entre_grupos: list[float] = []
    do_ruido: list[float] = []
    for indice, a in enumerate(dentro):
        for b in dentro[indice + 1 :]:
            if a.payload["tipo"] != b.payload["tipo"]:
                continue
            distancia_metros = _distancia_metros(a, b)
            if a.categoria == "ruido" or b.categoria == "ruido":
                do_ruido.append(distancia_metros)
            elif (a.categoria, a.grupo) != (b.categoria, b.grupo):
                entre_grupos.append(distancia_metros)

    return DistanciasDeReferencia(
        maior_salto_dentro_de_grupo_metros=max(saltos, default=None),
        menor_entre_grupos_metros=min(entre_grupos, default=None),
        menor_do_ruido_metros=min(do_ruido, default=None),
    )


def _distancia_metros(a: ItemGerado, b: ItemGerado) -> float:
    return math.hypot(a.norte_metros - b.norte_metros, a.leste_metros - b.leste_metros)


def _maior_salto_da_arvore(pontos: Sequence[ItemGerado]) -> float:
    """Maior aresta da árvore geradora mínima (algoritmo de Prim): o menor eps que
    mantém todos os pontos ligados por vizinhos de vizinhos."""
    if len(pontos) < 2:
        return 0.0
    distancias_ate_a_arvore_metros = {
        i: _distancia_metros(pontos[0], pontos[i]) for i in range(1, len(pontos))
    }
    maior_salto_metros = 0.0
    while distancias_ate_a_arvore_metros:
        mais_perto = min(
            distancias_ate_a_arvore_metros, key=distancias_ate_a_arvore_metros.__getitem__
        )
        maior_salto_metros = max(maior_salto_metros, distancias_ate_a_arvore_metros.pop(mais_perto))
        for i in distancias_ate_a_arvore_metros:
            distancias_ate_a_arvore_metros[i] = min(
                distancias_ate_a_arvore_metros[i], _distancia_metros(pontos[mais_perto], pontos[i])
            )
    return maior_salto_metros


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

COLUNAS_CSV = (
    "rotulo",
    "semente",
    "dispersao_metros",
    "pontos_por_aglomerado",
    "eps_metros",
    "min_pontos",
    "min_confirmacoes",
    "rodada_da_configuracao",
    "confirmadas_esperadas",
    "confirmadas_obtidas",
    "pendentes_esperadas",
    "pendentes_obtidas",
    "acerto_aglomerado",
    "acerto_sessao_repetida",
    "acerto_ruido",
    "grupos_fragmentados",
    "fusoes_indevidas",
    "ruido_em_barreira",
)


def _e_da_configuracao(rodada: RodadaSensibilidade, config: Configuracoes) -> bool:
    return (
        rodada.eps_metros == config.dbscan_eps_metros
        and rodada.min_pontos == config.dbscan_min_points
        and rodada.min_confirmacoes == config.min_confirmacoes
    )


def linha_csv(
    rodada: RodadaSensibilidade, opcoes: OpcoesGeracao, config: Configuracoes
) -> dict[str, object]:
    """Uma linha do CSV. Taxas como fração (0 a 1), com ponto decimal: o CSV é para
    planilha e script; o console usa vírgula e percentual."""
    a = rodada.avaliacao
    return {
        "rotulo": ROTULO_SIMULACAO,
        "semente": opcoes.semente,
        "dispersao_metros": opcoes.dispersao_metros,
        "pontos_por_aglomerado": opcoes.pontos_por_aglomerado,
        "eps_metros": rodada.eps_metros,
        "min_pontos": rodada.min_pontos,
        "min_confirmacoes": rodada.min_confirmacoes,
        "rodada_da_configuracao": "sim" if _e_da_configuracao(rodada, config) else "nao",
        "confirmadas_esperadas": a.barreiras_esperadas["confirmada"],
        "confirmadas_obtidas": a.barreiras_obtidas["confirmada"],
        "pendentes_esperadas": a.barreiras_esperadas["pendente"],
        "pendentes_obtidas": a.barreiras_obtidas["pendente"],
        "acerto_aglomerado": a.por_categoria["aglomerado"].taxa,
        "acerto_sessao_repetida": a.por_categoria["sessao_repetida"].taxa,
        "acerto_ruido": a.por_categoria["ruido"].taxa,
        "grupos_fragmentados": a.grupos_fragmentados,
        "fusoes_indevidas": a.fusoes_indevidas,
        "ruido_em_barreira": a.ruido_em_barreira,
    }


def gravar_csv(caminho: Path, linhas: Sequence[dict[str, object]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_CSV)
        escritor.writeheader()
        escritor.writerows(linhas)


def formatar_grade(rodadas: Sequence[RodadaSensibilidade], config: Configuracoes) -> str:
    linhas = []
    for rodada in rodadas:
        a = rodada.avaliacao
        linhas.append(
            [
                rodada.eps_metros,
                rodada.min_confirmacoes,
                f"{a.barreiras_obtidas['confirmada']} / {a.barreiras_esperadas['confirmada']}",
                f"{a.barreiras_obtidas['pendente']} / {a.barreiras_esperadas['pendente']}",
                formatar_taxa(a.por_categoria["aglomerado"].taxa),
                formatar_taxa(a.por_categoria["sessao_repetida"].taxa),
                formatar_taxa(a.por_categoria["ruido"].taxa),
                a.grupos_fragmentados,
                a.fusoes_indevidas,
                a.ruido_em_barreira,
                "← configuração" if _e_da_configuracao(rodada, config) else "",
            ]
        )
    return formatar_tabela(
        [
            "eps (m)",
            "min_conf",
            "confirmadas obt. / esp.",
            "pendentes obt. / esp.",
            "acerto aglom.",
            "acerto sessão rep.",
            "acerto ruído",
            "fragmentados",
            "fusões",
            "ruído→barreira",
            "nota",
        ],
        linhas,
    )


def formatar_referencias(referencias: DistanciasDeReferencia) -> str:
    def texto(valor_metros: float | None) -> str:
        return "—" if valor_metros is None else formatar_metros(round(valor_metros, 1))

    return "\n".join(
        [
            "[SIMULAÇÃO] Distâncias de referência (entre relatos do mesmo tipo; minpoints = 2):",
            f"  maior salto dentro de um grupo: "
            f"{texto(referencias.maior_salto_dentro_de_grupo_metros)} "
            "(eps abaixo disso divide esse grupo)",
            f"  menor distância entre grupos:   {texto(referencias.menor_entre_grupos_metros)} "
            "(eps a partir disso funde dois grupos)",
            f"  menor distância de um ruído:    {texto(referencias.menor_do_ruido_metros)} "
            "(eps a partir disso ruído vira barreira)",
        ]
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.analisar_sensibilidade",
        description=(
            "SIMULAÇÃO: gera a simulação uma vez (apaga antes a simulação existente) e "
            "mede o pipeline na grade eps × min_confirmacoes, cada rodada desfeita; no "
            "fim confirma só a rodada com os parâmetros do .env."
        ),
    )
    adicionar_opcoes_de_geracao(parser)
    args = parser.parse_args(argv)
    try:
        opcoes = opcoes_dos_argumentos(args)
    except ValueError as erro:
        parser.error(str(erro))

    config = obter_configuracoes()
    print(cabecalho_simulacao("análise de sensibilidade (pendência #4, T5)"))
    print(
        f"Banco: {config.postgres_db} em {config.postgres_host}:{config.postgres_porta} "
        f"(origem = '{ORIGEM}')\n"
    )
    try:
        with psycopg.connect(config.conninfo) as conexao:
            apagados = limpar_simulacao(conexao)
            itens = gerar_populacoes(
                opcoes, tipos=ler_tipos_ativos(conexao), eps_metros=config.dbscan_eps_metros
            )
            registrados = registrar_populacoes(conexao, itens, config=config)
            conexao.commit()  # 1. a simulação, gerada uma vez

            rodadas = analisar_grade(  # 2. cada rodada desfeita
                conexao,
                registrados,
                grade_eps_metros=GRADE_EPS_METROS,
                grade_min_confirmacoes=GRADE_MIN_CONFIRMACOES,
                min_pontos=config.dbscan_min_points,
                srid_calculo=config.srid_calculo,
                srid_armazenamento=config.srid_armazenamento,
            )

            resumo = executar_pipeline(  # 3. a rodada da configuração, confirmada
                conexao,
                origem=ORIGEM,
                eps_metros=config.dbscan_eps_metros,
                min_pontos=config.dbscan_min_points,
                min_confirmacoes=config.min_confirmacoes,
                srid_calculo=config.srid_calculo,
                srid_armazenamento=config.srid_armazenamento,
            )
            conexao.commit()
    except ValueError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1

    print(
        f"[SIMULAÇÃO] Simulação anterior apagada ({apagados['alertas']} alertas) e gerada "
        f"de novo UMA vez, com commit: semente {opcoes.semente}; {opcoes.aglomerados} "
        f"aglomerados e {opcoes.sessao_repetida} sessões repetidas de "
        f"{opcoes.pontos_por_aglomerado} relatos (dispersão de até "
        f"{formatar_metros(opcoes.dispersao_metros)}); {opcoes.ruido} ruídos; "
        f"{opcoes.fora_da_area} fora da área; {opcoes.invalidos} inválidos.\n"
    )
    print(formatar_referencias(distancias_de_referencia(itens)) + "\n")
    print(
        f"[SIMULAÇÃO] Grade eps × min_confirmacoes (minpoints = {config.dbscan_min_points}), "
        "cada rodada numa transação desfeita (rollback)\n" + formatar_grade(rodadas, config) + "\n"
    )
    print(
        "[SIMULAÇÃO] Rodada final, confirmada no banco, com os parâmetros da configuração:\n"
        + formatar_execucao(resumo)
        + "\n  execucoes_pipeline e GET /validacao/estatisticas?origem=simulacao mostram "
        "estes parâmetros, não os da grade.\n"
    )

    caminho = DIRETORIO_SAIDA / f"sensibilidade-semente-{opcoes.semente}.csv"
    gravar_csv(caminho, [linha_csv(rodada, opcoes, config) for rodada in rodadas])
    print(f"CSV (SIMULAÇÃO): {caminho_para_exibir(caminho)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
