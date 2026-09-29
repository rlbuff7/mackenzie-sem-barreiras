"""SIMULAÇÃO: análise de sensibilidade dos parâmetros do pipeline (pendência #4, T5).

Mede como o resultado do pipeline muda com `eps_metros` e `min_confirmacoes`, sobre a
MESMA simulação. Para cada combinação da grade `GRADE_EPS_METROS` ×
`GRADE_MIN_CONFIRMACOES` (minpoints fica o da configuração), avalia duas populações
separadamente (R16):

- **Controle** (as 5 populações de `gerar_dados_sinteticos`, bem separadas de
  propósito). Aqui os aglomerados têm de 2 a 5 sessões distintas (`--sessoes-variaveis`,
  ligado por padrão só neste script), e o status esperado de cada grupo segue a regra
  das sessões para cada `min_confirmacoes`: a tabela mostra o efeito real dele em
  confirmadas × pendentes. Conta também fragmentação, fusões indevidas e ruído
  classificado como barreira. As fusões do controle são 0 POR CONSTRUÇÃO (grupos a
  ≥ 4 × eps da config): isso não mede robustez.
- **Sequências** (`--sequencias`, 5 por padrão aqui): linhas de barreiras DISTINTAS a
  `--espacamento-sequencia-metros` (15 m) umas das outras, isoladas a 4 × o maior eps
  da grade de todo ponto do mesmo tipo fora delas. É a população que mede o
  encadeamento (T5): a partir de que eps barreiras vizinhas de verdade se fundem numa
  só.

Uso (a partir de `backend/`):

    uv run python -m scripts.analisar_sensibilidade

Saída: tabela rotulada "SIMULAÇÃO" no console e
`backend/scripts/saida/sensibilidade-semente-<N>.csv` (cada linha com a coluna
`rotulo`, para que nenhum recorte do CSV perca a marca de simulação).

A análise NÃO GRAVA NADA no banco (R18). Tudo roda numa única transação, desfeita
(rollback) no fim (`executar_analise`):

1. apaga a simulação existente (como `--limpar`) e gera a da análise UMA vez;
2. roda cada combinação da grade num SAVEPOINT desfeito, lendo as medições dentro dele;
3. desfaz a transação inteira.

O banco continua exatamente como estava antes: normalmente a simulação canônica do
gerador, com a sua linha em `execucoes_pipeline`. Assim as estatísticas e a figura do
funil nunca passam a mostrar a população de estresse desta análise, e a ordem em que
os scripts rodam não importa. Os resultados ficam só no console e no CSV. Os dados
reais nunca são tocados.
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
    FATOR_SEPARACAO,
    ORIGEM,
    ROTULO_SIMULACAO,
    Avaliacao,
    ItemGerado,
    ItemRegistrado,
    OpcoesGeracao,
    adicionar_opcoes_de_geracao,
    avaliar,
    avisos_de_geracao,
    cabecalho_simulacao,
    caminho_para_exibir,
    contar_alertas_da_simulacao,
    distancia_de_isolamento_metros,
    formatar_metros,
    formatar_tabela,
    formatar_taxa,
    gerar_populacoes,
    grupos_fora_de_alcance,
    ler_estado_final,
    ler_tipos_ativos,
    limpar_simulacao,
    opcoes_dos_argumentos,
    registrar_populacoes,
    sufixo_das_opcoes,
)

# Grade da análise (Task 4). eps em METROS, medido no SRID de cálculo (G6).
GRADE_EPS_METROS = (2, 4, 8, 12, 20)
GRADE_MIN_CONFIRMACOES = (2, 3, 4)

# Padrões deste script: os do gerador, com os aglomerados de sessões variáveis e as
# sequências ligados (R16). O gerador canônico continua com os dois desligados.
PADRAO_SENSIBILIDADE = OpcoesGeracao(sessoes_variaveis=True, sequencias=5)

_CATEGORIAS_DENTRO = ("aglomerado", "sessao_repetida", "ruido", "sequencia")
_GRUPOS_DE_CONTROLE = ("aglomerado", "sessao_repetida")


@dataclass(frozen=True)
class RodadaSensibilidade:
    """Uma combinação da grade e as avaliações medidas dentro da transação desfeita:
    a do controle e a das sequências, cada uma só com os itens da sua população."""

    eps_metros: float
    min_pontos: int
    min_confirmacoes: int
    controle: Avaliacao
    sequencia: Avaliacao


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

    Cada rodada fica dentro de `conexao.transaction(force_rollback=True)`, que dentro
    da transação da análise (`executar_analise`) ou da fixture dos testes é um
    SAVEPOINT desfeito: a rodada não deixa rastro, e como o pipeline reconstrói tudo
    do zero (D6), a seguinte começa do mesmo estado.

    O controle e as sequências são avaliados à parte, sobre o mesmo snapshot: cada
    avaliação só conta as barreiras que tocam os seus itens.
    """
    controle = [r for r in registrados if r.item.categoria != "sequencia"]
    sequencias = [r for r in registrados if r.item.categoria == "sequencia"]
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
                estado = ler_estado_final(conexao)
            rodadas.append(
                RodadaSensibilidade(
                    eps_metros,
                    min_pontos,
                    min_confirmacoes,
                    controle=avaliar(controle, estado, min_confirmacoes=min_confirmacoes),
                    sequencia=avaliar(sequencias, estado, min_confirmacoes=min_confirmacoes),
                )
            )
    return rodadas


@dataclass(frozen=True)
class ResultadoAnalise:
    """O que `executar_analise` mediu. `alertas_de_simulacao_antes` é quantos alertas
    de simulação o banco tinha antes, e continua tendo depois."""

    itens: list[ItemGerado]
    rodadas: list[RodadaSensibilidade]
    alertas_de_simulacao_antes: int


def executar_analise(
    conexao: Connection,
    opcoes: OpcoesGeracao,
    *,
    config: Configuracoes,
    grade_eps_metros: Sequence[float] = GRADE_EPS_METROS,
    grade_min_confirmacoes: Sequence[int] = GRADE_MIN_CONFIRMACOES,
) -> ResultadoAnalise:
    """A análise inteira dentro de `conexao.transaction(force_rollback=True)` (R18).

    Apaga a simulação existente, gera a da análise (isolando as sequências a 4 × o maior
    eps da grade), registra tudo pelo caminho da API e roda a grade. No fim a transação
    é desfeita: nada disso fica no banco, nem a limpeza, nem a geração, nem as linhas
    que o pipeline grava em `execucoes_pipeline`. Com a conexão ociosa, é um
    BEGIN … ROLLBACK; dentro de uma transação já aberta (a fixture dos testes), um
    SAVEPOINT desfeito.

    Só as sequências de id (BIGSERIAL) avançam: o Postgres não as desfaz no rollback.
    """
    with conexao.transaction(force_rollback=True):
        alertas_antes = contar_alertas_da_simulacao(conexao)
        limpar_simulacao(conexao)
        itens = gerar_populacoes(
            opcoes,
            tipos=ler_tipos_ativos(conexao),
            eps_metros=config.dbscan_eps_metros,
            eps_maximo_metros=max(grade_eps_metros),
        )
        registrados = registrar_populacoes(conexao, itens, config=config)
        rodadas = analisar_grade(
            conexao,
            registrados,
            grade_eps_metros=grade_eps_metros,
            grade_min_confirmacoes=grade_min_confirmacoes,
            min_pontos=config.dbscan_min_points,
            srid_calculo=config.srid_calculo,
            srid_armazenamento=config.srid_armazenamento,
        )
    return ResultadoAnalise(itens, rodadas, alertas_antes)


@dataclass(frozen=True)
class DistanciasDeReferencia:
    """Distâncias da simulação que explicam a tabela (metros, plano local).

    Com minpoints = 2, todo alerta com um vizinho a até eps é núcleo, e o DBSCAN
    liga vizinhos de vizinhos. Então:

    - `maior_salto_dentro_de_grupo_metros`: no pior grupo (inclusive as barreiras das
      sequências), a maior aresta da árvore geradora mínima dos seus relatos. eps
      abaixo disso DIVIDE esse grupo.
    - `menor_entre_grupos_metros`: menor distância entre relatos de grupos de
      CONTROLE diferentes do mesmo tipo. eps a partir disso FUNDE dois grupos.
    - `menor_do_ruido_metros`: menor distância de um ruído a outro relato do mesmo
      tipo. eps a partir disso transforma ruído em barreira.
    - `menor_entre_barreiras_da_sequencia_metros`: menor distância entre relatos de
      barreiras diferentes da MESMA sequência. eps a partir disso as barreiras de uma
      sequência começam a se fundir (encadeamento, T5).
    - `menor_da_sequencia_ao_resto_metros`: menor distância de um relato de sequência a
      qualquer relato do mesmo tipo fora dela (confere o isolamento).

    `None` quando não há par para medir.
    """

    maior_salto_dentro_de_grupo_metros: float | None
    menor_entre_grupos_metros: float | None
    menor_do_ruido_metros: float | None
    menor_entre_barreiras_da_sequencia_metros: float | None
    menor_da_sequencia_ao_resto_metros: float | None


def distancias_de_referencia(itens: Sequence[ItemGerado]) -> DistanciasDeReferencia:
    """Calcula as `DistanciasDeReferencia` dos itens que entram no agrupamento
    (grupos e ruído; fora da área e inválidos nunca chegam ao DBSCAN), sempre entre
    itens do MESMO tipo, porque o DBSCAN agrupa por tipo."""
    dentro = [item for item in itens if item.categoria in _CATEGORIAS_DENTRO]

    pontos_do_grupo: dict[tuple[str, int], list[ItemGerado]] = defaultdict(list)
    for item in dentro:
        if item.grupo is not None:
            pontos_do_grupo[(item.categoria, item.grupo)].append(item)
    saltos_metros = [_maior_salto_da_arvore(pontos) for pontos in pontos_do_grupo.values()]

    entre_grupos_metros: list[float] = []
    do_ruido_metros: list[float] = []
    entre_barreiras_da_sequencia_metros: list[float] = []
    da_sequencia_ao_resto_metros: list[float] = []
    for indice, a in enumerate(dentro):
        for b in dentro[indice + 1 :]:
            if a.payload["tipo"] != b.payload["tipo"]:
                continue
            distancia_metros = _distancia_metros(a, b)
            if "ruido" in (a.categoria, b.categoria):
                do_ruido_metros.append(distancia_metros)
            if (
                a.categoria in _GRUPOS_DE_CONTROLE
                and b.categoria in _GRUPOS_DE_CONTROLE
                and (a.categoria, a.grupo) != (b.categoria, b.grupo)
            ):
                entre_grupos_metros.append(distancia_metros)
            if "sequencia" in (a.categoria, b.categoria):
                if a.sequencia == b.sequencia:
                    if a.grupo != b.grupo:
                        entre_barreiras_da_sequencia_metros.append(distancia_metros)
                else:
                    da_sequencia_ao_resto_metros.append(distancia_metros)

    return DistanciasDeReferencia(
        maior_salto_dentro_de_grupo_metros=max(saltos_metros, default=None),
        menor_entre_grupos_metros=min(entre_grupos_metros, default=None),
        menor_do_ruido_metros=min(do_ruido_metros, default=None),
        menor_entre_barreiras_da_sequencia_metros=min(
            entre_barreiras_da_sequencia_metros, default=None
        ),
        menor_da_sequencia_ao_resto_metros=min(da_sequencia_ao_resto_metros, default=None),
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

# Cada linha carrega o contexto da geração e as distâncias de referência: um recorte do
# CSV continua dizendo de que simulação veio (R17).
_COLUNAS_DE_REFERENCIA = (
    "maior_salto_dentro_de_grupo_metros",
    "menor_entre_grupos_metros",
    "menor_do_ruido_metros",
    "menor_entre_barreiras_da_sequencia_metros",
    "menor_da_sequencia_ao_resto_metros",
)
COLUNAS_CSV = (
    "rotulo",
    "semente",
    "dispersao_metros",
    "pontos_por_aglomerado",
    "sessoes_variaveis",
    "sequencias",
    "barreiras_por_sequencia",
    "espacamento_sequencia_metros",
    "separacao_minima_metros",
    "isolamento_sequencia_metros",
    *_COLUNAS_DE_REFERENCIA,
    "eps_metros",
    "min_pontos",
    "min_confirmacoes",
    "rodada_da_configuracao",
    "controle_confirmadas_esperadas",
    "controle_confirmadas_obtidas",
    "controle_pendentes_esperadas",
    "controle_pendentes_obtidas",
    "acerto_aglomerado",
    "acerto_sessao_repetida",
    "acerto_ruido",
    "controle_grupos_fragmentados",
    "controle_fusoes",
    "ruido_em_barreira",
    "sequencia_barreiras_esperadas",
    "sequencia_barreiras_obtidas",
    "acerto_sequencia",
    "sequencia_fusoes",
    "sequencia_fragmentadas",
)


def _e_da_configuracao(rodada: RodadaSensibilidade, config: Configuracoes) -> bool:
    return (
        rodada.eps_metros == config.dbscan_eps_metros
        and rodada.min_pontos == config.dbscan_min_points
        and rodada.min_confirmacoes == config.min_confirmacoes
    )


def linha_csv(
    rodada: RodadaSensibilidade,
    opcoes: OpcoesGeracao,
    config: Configuracoes,
    referencias: DistanciasDeReferencia,
    *,
    eps_maximo_metros: float,
) -> dict[str, object]:
    """Uma linha do CSV. Taxas como fração (0 a 1), com ponto decimal: o CSV é para
    planilha e script; o console usa vírgula e percentual."""
    c, s = rodada.controle, rodada.sequencia
    return {
        "rotulo": ROTULO_SIMULACAO,
        "semente": opcoes.semente,
        "dispersao_metros": opcoes.dispersao_metros,
        "pontos_por_aglomerado": opcoes.pontos_por_aglomerado,
        "sessoes_variaveis": "sim" if opcoes.sessoes_variaveis else "nao",
        "sequencias": opcoes.sequencias,
        "barreiras_por_sequencia": opcoes.barreiras_por_sequencia,
        "espacamento_sequencia_metros": opcoes.espacamento_sequencia_metros,
        "separacao_minima_metros": FATOR_SEPARACAO * config.dbscan_eps_metros,
        "isolamento_sequencia_metros": distancia_de_isolamento_metros(
            config.dbscan_eps_metros, eps_maximo_metros
        ),
        **{
            coluna: None
            if getattr(referencias, coluna) is None
            else round(getattr(referencias, coluna), 2)
            for coluna in _COLUNAS_DE_REFERENCIA
        },
        "eps_metros": rodada.eps_metros,
        "min_pontos": rodada.min_pontos,
        "min_confirmacoes": rodada.min_confirmacoes,
        "rodada_da_configuracao": "sim" if _e_da_configuracao(rodada, config) else "nao",
        "controle_confirmadas_esperadas": c.barreiras_esperadas["confirmada"],
        "controle_confirmadas_obtidas": c.barreiras_obtidas["confirmada"],
        "controle_pendentes_esperadas": c.barreiras_esperadas["pendente"],
        "controle_pendentes_obtidas": c.barreiras_obtidas["pendente"],
        "acerto_aglomerado": c.por_categoria["aglomerado"].taxa,
        "acerto_sessao_repetida": c.por_categoria["sessao_repetida"].taxa,
        "acerto_ruido": c.por_categoria["ruido"].taxa,
        "controle_grupos_fragmentados": c.grupos_fragmentados,
        "controle_fusoes": c.fusoes_indevidas,
        "ruido_em_barreira": c.ruido_em_barreira,
        "sequencia_barreiras_esperadas": s.por_categoria["sequencia"].esperado,
        "sequencia_barreiras_obtidas": sum(s.barreiras_obtidas.values()),
        "acerto_sequencia": s.por_categoria["sequencia"].taxa,
        "sequencia_fusoes": s.fusoes_indevidas,
        "sequencia_fragmentadas": s.grupos_fragmentados,
    }


def gravar_csv(caminho: Path, linhas: Sequence[dict[str, object]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_CSV)
        escritor.writeheader()
        escritor.writerows(linhas)


def cabecalho_do_controle(*, min_pontos: int, fusoes_zero_por_construcao: bool) -> str:
    """Título da tabela do controle. Só diz que as fusões são 0 por construção quando
    a dispersão garante isso (`grupos_fora_de_alcance`); senão, houve AVISO antes, e
    as fusões do controle passam a ser uma medida de verdade."""
    nota = (
        "As fusões do controle são 0 por construção (grupos a ≥ 4 × eps da config): não "
        "medem robustez."
        if fusoes_zero_por_construcao
        else "Com esta dispersão, as fusões do controle ficam sem essa garantia (ver o "
        "AVISO acima): aqui elas medem algo."
    )
    return (
        f"[SIMULAÇÃO] CONTROLE: grade eps × min_confirmacoes (minpoints = {min_pontos}), "
        f"cada rodada num savepoint desfeito. {nota}"
    )


def formatar_grade_controle(rodadas: Sequence[RodadaSensibilidade], config: Configuracoes) -> str:
    linhas = []
    for rodada in rodadas:
        c = rodada.controle
        linhas.append(
            [
                rodada.eps_metros,
                rodada.min_confirmacoes,
                f"{c.barreiras_obtidas['confirmada']} / {c.barreiras_esperadas['confirmada']}",
                f"{c.barreiras_obtidas['pendente']} / {c.barreiras_esperadas['pendente']}",
                formatar_taxa(c.por_categoria["aglomerado"].taxa),
                formatar_taxa(c.por_categoria["sessao_repetida"].taxa),
                formatar_taxa(c.por_categoria["ruido"].taxa),
                c.grupos_fragmentados,
                c.fusoes_indevidas,
                c.ruido_em_barreira,
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


def formatar_grade_sequencias(rodadas: Sequence[RodadaSensibilidade], config: Configuracoes) -> str:
    """Uma linha por eps. A fusão não depende de min_confirmacoes; usa a rodada com o
    min_confirmacoes da configuração (ou a primeira do eps, se ele não está na grade)."""
    por_eps: dict[float, RodadaSensibilidade] = {}
    for rodada in rodadas:
        if rodada.eps_metros not in por_eps or rodada.min_confirmacoes == config.min_confirmacoes:
            por_eps[rodada.eps_metros] = rodada
    linhas = []
    for eps_metros, rodada in por_eps.items():
        s = rodada.sequencia
        resultado = s.por_categoria["sequencia"]
        linhas.append(
            [
                eps_metros,
                resultado.esperado,
                sum(s.barreiras_obtidas.values()),
                resultado.obtido,
                formatar_taxa(resultado.taxa),
                s.fusoes_indevidas,
                s.grupos_fragmentados,
            ]
        )
    return formatar_tabela(
        [
            "eps (m)",
            "barreiras verdadeiras",
            "barreiras obtidas",
            "separadas corretamente",
            "acerto",
            "fusões",
            "fragmentadas",
        ],
        linhas,
    )


def formatar_referencias(referencias: DistanciasDeReferencia, *, min_pontos: int) -> str:
    """As distâncias de referência, com a leitura de cada uma. A leitura pela árvore
    geradora mínima (o "salto" que divide um grupo) só é exata com minpoints = 2:
    com mais, um ponto precisa de vários vizinhos para ser núcleo. Nesse caso a linha
    do salto sai e as outras valem como condição necessária (eps menor que a
    distância impede a fusão; maior não a garante)."""

    def texto(valor_metros: float | None) -> str:
        return "—" if valor_metros is None else formatar_metros(round(valor_metros, 1))

    linhas = [
        f"[SIMULAÇÃO] Distâncias de referência (entre relatos do mesmo tipo; minpoints = "
        f"{min_pontos}):"
    ]
    if min_pontos == 2:
        linhas.append(
            f"  maior salto dentro de um grupo: "
            f"{texto(referencias.maior_salto_dentro_de_grupo_metros)} "
            "(eps abaixo disso divide esse grupo)"
        )
    else:
        linhas.append(
            f"  AVISO: com minpoints = {min_pontos}, a leitura pela árvore geradora mínima não "
            "vale e fica de fora; as distâncias abaixo são só condição necessária para a "
            "fusão (eps menor que elas a impede, maior não a garante)."
        )
    return "\n".join(
        [
            *linhas,
            f"  menor distância entre grupos:   {texto(referencias.menor_entre_grupos_metros)} "
            "(eps a partir disso funde dois grupos)",
            f"  menor distância de um ruído:    {texto(referencias.menor_do_ruido_metros)} "
            "(eps a partir disso ruído vira barreira)",
            "  menor distância entre barreiras da mesma sequência: "
            f"{texto(referencias.menor_entre_barreiras_da_sequencia_metros)} "
            "(eps a partir disso barreiras vizinhas se fundem)",
            "  menor distância de uma sequência ao resto:          "
            f"{texto(referencias.menor_da_sequencia_ao_resto_metros)} (isolamento)",
        ]
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.analisar_sensibilidade",
        description=(
            "SIMULAÇÃO: mede o pipeline na grade eps × min_confirmacoes sobre uma "
            "simulação gerada uma vez. Tudo roda numa transação desfeita: nada é gravado "
            "no banco."
        ),
    )
    adicionar_opcoes_de_geracao(parser, PADRAO_SENSIBILIDADE)
    args = parser.parse_args(argv)
    try:
        opcoes = opcoes_dos_argumentos(args)
    except ValueError as erro:
        parser.error(str(erro))

    config = obter_configuracoes()
    print(cabecalho_simulacao("análise de sensibilidade (pendência #4, T5)"))
    print(
        f"Banco: {config.postgres_db} em {config.postgres_host}:{config.postgres_porta} "
        f"(origem = '{ORIGEM}'). A análise inteira roda numa transação desfeita no fim: "
        "nada é gravado.\n"
    )
    try:
        with psycopg.connect(config.conninfo) as conexao:
            resultado = executar_analise(conexao, opcoes, config=config)
    except ValueError as erro:
        print(f"erro: {erro}. Nada foi gravado no banco (rollback).", file=sys.stderr)
        return 1
    itens, rodadas = resultado.itens, resultado.rodadas

    sessoes = (
        "de 2 a 5 sessões (sorteadas)"
        if opcoes.sessoes_variaveis
        else f"{opcoes.pontos_por_aglomerado} sessões"
    )
    isolamento_metros = distancia_de_isolamento_metros(
        config.dbscan_eps_metros, max(GRADE_EPS_METROS)
    )
    print(
        f"[SIMULAÇÃO] Simulação da análise gerada UMA vez, dentro da transação: semente "
        f"{opcoes.semente}; CONTROLE: "
        f"{opcoes.aglomerados} aglomerados com {sessoes}, {opcoes.sessao_repetida} sessões "
        f"repetidas de {opcoes.pontos_por_aglomerado} relatos, {opcoes.ruido} ruídos, "
        f"{opcoes.fora_da_area} fora da área, {opcoes.invalidos} inválidos (dispersão de até "
        f"{formatar_metros(opcoes.dispersao_metros)}); SEQUÊNCIAS: {opcoes.sequencias} de "
        f"{opcoes.barreiras_por_sequencia} barreiras a "
        f"{formatar_metros(opcoes.espacamento_sequencia_metros)}, isoladas a "
        f"{formatar_metros(isolamento_metros)}.\n"
    )
    for aviso in avisos_de_geracao(
        opcoes,
        eps_metros=config.dbscan_eps_metros,
        min_confirmacoes=config.min_confirmacoes,
        eps_maximo_metros=max(GRADE_EPS_METROS),
    ):
        print(aviso + "\n")
    referencias = distancias_de_referencia(itens)
    print(formatar_referencias(referencias, min_pontos=config.dbscan_min_points) + "\n")
    fusoes_zero_por_construcao = grupos_fora_de_alcance(
        opcoes, eps_metros=config.dbscan_eps_metros, eps_maximo_metros=max(GRADE_EPS_METROS)
    )
    print(
        cabecalho_do_controle(
            min_pontos=config.dbscan_min_points,
            fusoes_zero_por_construcao=fusoes_zero_por_construcao,
        )
        + "\n"
        + formatar_grade_controle(rodadas, config)
        + "\n"
    )
    if opcoes.sequencias:
        print(
            "[SIMULAÇÃO] SEQUÊNCIAS (encadeamento, T5): barreiras distintas a "
            f"{formatar_metros(opcoes.espacamento_sequencia_metros)} em linha; por eps, com "
            f"min_confirmacoes = {config.min_confirmacoes}\n"
            + formatar_grade_sequencias(rodadas, config)
            + "\n"
        )

    sufixo = sufixo_das_opcoes(opcoes, PADRAO_SENSIBILIDADE)
    caminho = DIRETORIO_SAIDA / f"sensibilidade-semente-{opcoes.semente}{sufixo}.csv"
    gravar_csv(
        caminho,
        [
            linha_csv(rodada, opcoes, config, referencias, eps_maximo_metros=max(GRADE_EPS_METROS))
            for rodada in rodadas
        ],
    )
    print(f"CSV (SIMULAÇÃO): {caminho_para_exibir(caminho)}")
    print(
        "Nada foi gravado no banco: a transação da análise foi desfeita (rollback). O banco "
        f"continua como estava, com {resultado.alertas_de_simulacao_antes} alertas de "
        "simulação e a mesma linha em execucoes_pipeline; as estatísticas e a figura do "
        "funil não mudam."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
