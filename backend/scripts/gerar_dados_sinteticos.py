"""SIMULAÇÃO: gerador de dados sintéticos e teste de eficácia do pipeline (CLAUDE.md §9, D8).

Gera cinco populações de relatos com o destino conhecido de antemão (a "verdade"),
grava tudo pelo mesmo caminho da API (`registrar_alerta`, estágios 1 e 2) com
`origem='simulacao'` e, com `--avaliar`, compara o que o pipeline decidiu com o que
cada população deveria virar:

- `aglomerado`: N relatos do mesmo tipo, a poucos metros, cada um de uma sessão
  diferente. Esperado: 1 barreira `confirmada` por grupo.
- `sessao_repetida`: UMA sessão relatando N vezes no mesmo lugar. Esperado: 1 barreira
  `pendente` por grupo (prova o estágio 4: contam sessões, não alertas).
- `ruido`: relatos isolados, sem vizinho do mesmo tipo. Esperado: `ruido_isolado`.
- `fora_da_area`: relatos válidos entre 700 e 1500 m do centro. Esperado: `descartado`
  com `motivo_descarte='fora_da_area'` (estágio 2).
- `invalido`: payloads malformados. Esperado: reprovados no estágio 1, gravados em
  `alertas_rejeitados`.

Uso (a partir de `backend/`):

    uv run python -m scripts.gerar_dados_sinteticos --limpar --executar-pipeline --avaliar

Honestidade acadêmica (CLAUDE.md §9, G10): todo dado gerado aqui tem `origem='simulacao'`,
a descrição de cada relato começa com "SIMULAÇÃO" e toda saída (console e JSON) é
rotulada como simulação. Nada disso é coleta real, e a origem `real` nunca é tocada.

Transação: este é um ponto de entrada. `main()` abre a própria conexão e faz o commit
no fim (se algo falhar, nada fica gravado). As outras funções recebem a conexão e
nunca fazem commit, para que os testes as rodem dentro de uma transação desfeita.

Geometria: os pontos são sorteados num plano local em METROS centrado no campus e só
então convertidos para graus (`deslocar_ponto`). A separação mínima é 4 × eps (o
`DBSCAN_EPS_METROS` da configuração): entre os centros de dois grupos quaisquer e
entre cada ruído e qualquer outro ponto do mesmo tipo. Com os padrões (eps 8 m,
dispersão de até 3 m) o cenário é bem separado de propósito: é o caso em que o
pipeline TEM de acertar tudo. Cenários mais difíceis ficam para a análise de
sensibilidade (`scripts/analisar_sensibilidade.py`).
"""

import argparse
import json
import math
import random
import sys
import textwrap
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

from app.config import Configuracoes, obter_configuracoes
from app.validacao.entrada import ResultadoEntrada, registrar_alerta
from app.validacao.estatisticas import ROTULOS_POR_ORIGEM
from app.validacao.pipeline import CHAVE_LOCK_PIPELINE, ResumoExecucao, executar_pipeline

ORIGEM = "simulacao"
ROTULO_SIMULACAO = ROTULOS_POR_ORIGEM[ORIGEM]  # "SIMULAÇÃO — dados sintéticos"
AVISO_SIMULACAO = (
    "Dados sintéticos para desenvolver e avaliar o pipeline. Não são coleta real "
    "e não podem ser apresentados como tal (CLAUDE.md §9)."
)

# Centroide do campus Higienópolis (OSM), o mesmo centro do polígono provisório da
# área de estudo (db/seeds/002_area_estudo.sql: círculo de 500 m).
CENTRO_LATITUDE = -23.5471938
CENTRO_LONGITUDE = -46.6524631

# Grupos e ruído caem a até 400 m do centro: o polígono de 32 lados do seed tem raio
# inscrito de ~497,6 m, então sobra folga para a dispersão sem encostar na borda.
RAIO_GERACAO_METROS = 400.0
# "Fora da área" entre 700 e 1500 m do centro: longe da borda de 500 m, para que o
# geofence decida sem ambiguidade.
RAIO_FORA_MINIMO_METROS = 700.0
RAIO_FORA_MAXIMO_METROS = 1500.0

# Separação mínima = FATOR_SEPARACAO × eps. Com 4 × eps, dois grupos (ou um ruído e
# um grupo) nunca ficam ao alcance um do outro no DBSCAN, mesmo somando a dispersão.
FATOR_SEPARACAO = 4
# Tentativas da amostragem com rejeição por ponto. Passou disso, as opções pedem
# mais pontos do que cabem na área com a separação exigida.
MAX_TENTATIVAS = 10_000

CATEGORIAS = ("aglomerado", "sessao_repetida", "ruido", "fora_da_area", "invalido")

# Com `sessoes_variaveis`, cada aglomerado sorteia daqui quantas sessões distintas (e
# quantos relatos, um por sessão) terá. Assim uns grupos passam e outros não passam
# de min_confirmacoes, e a análise de sensibilidade mostra o efeito real dele.
SESSOES_VARIAVEIS = (2, 3, 4, 5)

# Cada inválido tem UM defeito só; o resto do payload é válido e dentro da área.
VARIACOES_INVALIDAS = (
    "latitude_fora_da_faixa",
    "tipo_inexistente",
    "severidade_invalida",
    "campo_faltando",
    "campo_extra",
)

# Destino final das categorias avaliadas relato a relato (ver `destino_final`). Os
# grupos têm o status esperado dado pela regra das sessões (`status_esperado`).
DESTINO_ESPERADO = {
    "ruido": "ruido_isolado",
    "fora_da_area": "descartado:fora_da_area",
    "invalido": "rejeitado_schema",
}
# Ordem das colunas da matriz de confusão (destinos inesperados entram no fim).
ORDEM_DESTINOS = (
    "rejeitado_schema",
    "descartado:fora_da_area",
    "bruto",
    "ruido_isolado",
    "barreira_pendente",
    "barreira_confirmada",
)
_CATEGORIAS_DE_GRUPO = ("aglomerado", "sessao_repetida")

_RAIZ_REPO = Path(__file__).resolve().parent.parent.parent
DIRETORIO_SAIDA = Path(__file__).resolve().parent / "saida"

# (norte, leste) em METROS no plano local centrado no campus: é assim que o gerador
# sorteia e compara posições. Só `deslocar_ponto` converte para graus.
PontoMetros = tuple[float, float]

# Elipsoide WGS84 (o do SRID 4326).
_SEMIEIXO_MAIOR_METROS = 6_378_137.0
_ACHATAMENTO = 1 / 298.257223563
_EXCENTRICIDADE_QUADRADA = _ACHATAMENTO * (2 - _ACHATAMENTO)


# ---------------------------------------------------------------------------
# Geração (pura: nada de banco, determinística dada a semente)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpcoesGeracao:
    """Quantas unidades de cada população gerar (os padrões são os da CLI).

    `aglomerados` e `sessao_repetida` contam GRUPOS; cada grupo tem
    `pontos_por_aglomerado` relatos. Com `sessoes_variaveis`, cada aglomerado tem, em
    vez disso, k relatos de k sessões distintas, k sorteado de `SESSOES_VARIAVEIS`.
    As demais contam relatos (ou payloads).
    `dispersao_metros` é o RAIO MÁXIMO em torno do centro do grupo (sorteio uniforme
    no disco): dois relatos do mesmo grupo ficam a no máximo 2 × dispersão.
    """

    semente: int = 42
    aglomerados: int = 20
    pontos_por_aglomerado: int = 4
    dispersao_metros: float = 3.0
    sessao_repetida: int = 5
    ruido: int = 40
    fora_da_area: int = 30
    invalidos: int = 10
    sessoes_variaveis: bool = False

    def __post_init__(self) -> None:
        for nome in ("aglomerados", "sessao_repetida", "ruido", "fora_da_area", "invalidos"):
            if getattr(self, nome) < 0:
                raise ValueError(f"{nome} não pode ser negativo (recebido: {getattr(self, nome)})")
        if self.pontos_por_aglomerado < 2:
            raise ValueError(
                "pontos_por_aglomerado deve ser pelo menos 2: um relato sozinho é ruído "
                f"(recebido: {self.pontos_por_aglomerado})"
            )
        if not (self.dispersao_metros >= 0):
            raise ValueError(
                f"dispersao_metros deve ser 0 ou mais (recebido: {self.dispersao_metros})"
            )


@dataclass(frozen=True)
class ItemGerado:
    """Um relato sintético e a verdade sobre ele.

    `grupo` numera os grupos de `aglomerado` e de `sessao_repetida` (a identidade de
    um grupo é o par categoria + grupo); é `None` nas outras categorias. `variacao` é
    o defeito de um `invalido`. `norte_metros`/`leste_metros` são a posição no plano
    local em relação ao centro do campus. `payload` é exatamente o que vai para
    `registrar_alerta`, como viria do navegador.
    """

    categoria: str
    grupo: int | None
    variacao: str | None
    norte_metros: float
    leste_metros: float
    payload: dict[str, Any]


def deslocar_ponto(
    latitude: float, longitude: float, norte_metros: float, leste_metros: float
) -> tuple[float, float]:
    """(latitude, longitude) do ponto a `norte_metros` ao norte e `leste_metros` a
    leste do ponto dado, por aproximação local (plano tangente).

    Um grau não tem tamanho fixo em metros. Aqui se usam os raios de curvatura do
    elipsoide WGS84 NA latitude de partida: o meridiano (norte-sul) e o paralelo
    (leste-oeste, que encolhe com o cosseno da latitude). Usar a Terra esférica
    ("1° ≈ 111 km") erraria ~0,4% em São Paulo; com os raios do elipsoide, o erro
    relativo de distância medido contra `ST_Distance` em `geography` (distância no
    elipsoide) foi de no máximo 0,002% a 1,5 km do centro (0,0005% a 400 m), bem
    abaixo do limite de 0,1% que `tests/test_dados_sinteticos.py` exige.
    """
    phi = math.radians(latitude)
    w = math.sqrt(1 - _EXCENTRICIDADE_QUADRADA * math.sin(phi) ** 2)
    raio_meridiano_metros = _SEMIEIXO_MAIOR_METROS * (1 - _EXCENTRICIDADE_QUADRADA) / w**3
    raio_paralelo_metros = _SEMIEIXO_MAIOR_METROS / w * math.cos(phi)
    return (
        latitude + math.degrees(norte_metros / raio_meridiano_metros),
        longitude + math.degrees(leste_metros / raio_paralelo_metros),
    )


def gerar_populacoes(
    opcoes: OpcoesGeracao, *, tipos: Sequence[str], eps_metros: float
) -> list[ItemGerado]:
    """As cinco populações (D8), na ordem de `CATEGORIAS`.

    Determinística dada a semente. Cada categoria tem o seu próprio gerador
    aleatório (semente + nome da categoria), então mudar a quantidade de uma
    população não move as outras que não dependem dela. Dependências: os centros de
    `sessao_repetida` evitam os de `aglomerado`; o ruído evita todos os pontos de
    grupo do mesmo tipo.

    `tipos` são os códigos de tipo aceitos (a taxonomia ainda está aberta, #2; o
    script lê os ativos do banco). `eps_metros` define a separação mínima
    (`FATOR_SEPARACAO` × eps). `ValueError` se a separação não couber na área.
    """
    if not tipos:
        raise ValueError("nenhum tipo de barreira informado (rode ./db/banco.sh migrar)")
    if not (eps_metros > 0):
        raise ValueError(f"eps_metros deve ser maior que 0 (recebido: {eps_metros})")
    tipos = list(tipos)
    separacao_metros = FATOR_SEPARACAO * eps_metros

    centros_ocupados: list[PontoMetros] = []
    pontos_por_tipo: dict[str, list[PontoMetros]] = defaultdict(list)
    itens: list[ItemGerado] = []

    for categoria, quantidade in (
        ("aglomerado", opcoes.aglomerados),
        ("sessao_repetida", opcoes.sessao_repetida),
    ):
        grupos = _gerar_grupos(
            _gerador(opcoes.semente, categoria),
            categoria,
            quantidade,
            opcoes,
            tipos=tipos,
            separacao_metros=separacao_metros,
            centros_ocupados=centros_ocupados,
        )
        for item in grupos:
            pontos_por_tipo[item.payload["tipo"]].append((item.norte_metros, item.leste_metros))
        itens.extend(grupos)

    itens.extend(
        _gerar_ruido(
            _gerador(opcoes.semente, "ruido"),
            opcoes.ruido,
            tipos=tipos,
            separacao_metros=separacao_metros,
            pontos_por_tipo=pontos_por_tipo,
        )
    )
    itens.extend(_gerar_fora_da_area(_gerador(opcoes.semente, "fora_da_area"), opcoes, tipos))
    itens.extend(_gerar_invalidos(_gerador(opcoes.semente, "invalido"), opcoes, tipos))
    return itens


def _gerador(semente: int, categoria: str) -> random.Random:
    """Gerador aleatório próprio da categoria. Semente em texto: o `random` a
    converte por SHA-512, de forma estável entre execuções e versões do Python."""
    return random.Random(f"{semente}/{categoria}")


def _ponto_no_disco(rng: random.Random, raio_metros: float) -> PontoMetros:
    """(norte, leste) uniforme na ÁREA do disco: raio = R·√u, não R·u (que
    concentraria os pontos perto do centro)."""
    raio_sorteado_metros = raio_metros * math.sqrt(rng.random())
    angulo = rng.uniform(0, 2 * math.pi)
    return raio_sorteado_metros * math.cos(angulo), raio_sorteado_metros * math.sin(angulo)


def _ponto_no_anel(
    rng: random.Random, raio_minimo_metros: float, raio_maximo_metros: float
) -> PontoMetros:
    """(norte, leste) uniforme na área do anel entre os dois raios."""
    raio_sorteado_metros = math.sqrt(rng.uniform(raio_minimo_metros**2, raio_maximo_metros**2))
    angulo = rng.uniform(0, 2 * math.pi)
    return raio_sorteado_metros * math.cos(angulo), raio_sorteado_metros * math.sin(angulo)


def _nova_sessao(rng: random.Random) -> str:
    """UUID de sessão (D1) tirado do gerador da semente, para ser reproduzível."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _longe_de_todos(
    ponto: PontoMetros, outros: Sequence[PontoMetros], distancia_metros: float
) -> bool:
    return all(math.hypot(ponto[0] - n, ponto[1] - e) >= distancia_metros for n, e in outros)


def _sortear_longe(
    rng: random.Random,
    outros: Sequence[PontoMetros],
    separacao_metros: float,
    descricao: str,
) -> PontoMetros:
    """Amostragem com rejeição: sorteia no disco de geração até achar um ponto a
    pelo menos `separacao_metros` de todos os `outros`."""
    for _ in range(MAX_TENTATIVAS):
        ponto = _ponto_no_disco(rng, RAIO_GERACAO_METROS)
        if _longe_de_todos(ponto, outros, separacao_metros):
            return ponto
    raise ValueError(
        f"{descricao} não coube a {separacao_metros:g} m dos demais em {MAX_TENTATIVAS} "
        f"tentativas, num disco de {RAIO_GERACAO_METROS:g} m: reduza as quantidades"
    )


def _payload(
    rng: random.Random,
    norte_metros: float,
    leste_metros: float,
    *,
    tipo: str,
    sessao_id: str,
    descricao: str,
) -> dict[str, Any]:
    latitude, longitude = deslocar_ponto(
        CENTRO_LATITUDE, CENTRO_LONGITUDE, norte_metros, leste_metros
    )
    return {
        "latitude": latitude,
        "longitude": longitude,
        "tipo": tipo,
        "severidade": rng.choice((1, 2, 3)),
        "descricao": descricao,
        "sessao_id": sessao_id,
    }


def _gerar_grupos(
    rng: random.Random,
    categoria: str,
    quantidade: int,
    opcoes: OpcoesGeracao,
    *,
    tipos: list[str],
    separacao_metros: float,
    centros_ocupados: list[PontoMetros],
) -> list[ItemGerado]:
    """Grupos de `aglomerado` (uma sessão por relato) ou de `sessao_repetida` (uma
    sessão para o grupo todo). Acrescenta os centros sorteados a `centros_ocupados`."""
    nome = "aglomerado" if categoria == "aglomerado" else "sessão repetida"
    itens: list[ItemGerado] = []
    for grupo in range(quantidade):
        centro_metros = _sortear_longe(
            rng, centros_ocupados, separacao_metros, f"o centro do grupo {grupo + 1} ({nome})"
        )
        centros_ocupados.append(centro_metros)
        tipo = rng.choice(tipos)
        sessao_do_grupo = _nova_sessao(rng) if categoria == "sessao_repetida" else None
        relatos = opcoes.pontos_por_aglomerado
        if categoria == "aglomerado" and opcoes.sessoes_variaveis:
            relatos = rng.choice(SESSOES_VARIAVEIS)
        for relato in range(relatos):
            desvio_norte_metros, desvio_leste_metros = _ponto_no_disco(rng, opcoes.dispersao_metros)
            norte_metros, leste_metros = (
                centro_metros[0] + desvio_norte_metros,
                centro_metros[1] + desvio_leste_metros,
            )
            payload = _payload(
                rng,
                norte_metros,
                leste_metros,
                tipo=tipo,
                sessao_id=sessao_do_grupo or _nova_sessao(rng),
                descricao=f"SIMULAÇÃO: {nome} {grupo + 1} (relato {relato + 1} de {relatos})",
            )
            itens.append(ItemGerado(categoria, grupo, None, norte_metros, leste_metros, payload))
    return itens


def _gerar_ruido(
    rng: random.Random,
    quantidade: int,
    *,
    tipos: list[str],
    separacao_metros: float,
    pontos_por_tipo: dict[str, list[PontoMetros]],
) -> list[ItemGerado]:
    """Relatos isolados: cada um a ≥ `separacao_metros` de qualquer outro ponto
    gerado do MESMO tipo (o DBSCAN agrupa por tipo, então só esses importam)."""
    itens: list[ItemGerado] = []
    for indice in range(quantidade):
        tipo = rng.choice(tipos)
        norte_metros, leste_metros = _sortear_longe(
            rng, pontos_por_tipo[tipo], separacao_metros, f"o ruído {indice + 1} ({tipo})"
        )
        pontos_por_tipo[tipo].append((norte_metros, leste_metros))
        payload = _payload(
            rng,
            norte_metros,
            leste_metros,
            tipo=tipo,
            sessao_id=_nova_sessao(rng),
            descricao="SIMULAÇÃO: ruído isolado",
        )
        itens.append(ItemGerado("ruido", None, None, norte_metros, leste_metros, payload))
    return itens


def _gerar_fora_da_area(
    rng: random.Random, opcoes: OpcoesGeracao, tipos: list[str]
) -> list[ItemGerado]:
    """Relatos válidos entre 700 e 1500 m do centro: o geofence deve descartá-los."""
    itens: list[ItemGerado] = []
    for _ in range(opcoes.fora_da_area):
        tipo = rng.choice(tipos)
        norte_metros, leste_metros = _ponto_no_anel(
            rng, RAIO_FORA_MINIMO_METROS, RAIO_FORA_MAXIMO_METROS
        )
        payload = _payload(
            rng,
            norte_metros,
            leste_metros,
            tipo=tipo,
            sessao_id=_nova_sessao(rng),
            descricao="SIMULAÇÃO: fora da área",
        )
        itens.append(ItemGerado("fora_da_area", None, None, norte_metros, leste_metros, payload))
    return itens


def _gerar_invalidos(
    rng: random.Random, opcoes: OpcoesGeracao, tipos: list[str]
) -> list[ItemGerado]:
    """Payloads com UM defeito cada, alternando as `VARIACOES_INVALIDAS`. Fora o
    defeito, o payload é válido e cai dentro da área: se ele passasse do estágio 1,
    viraria um alerta normal, e o teste acusaria."""
    itens: list[ItemGerado] = []
    for indice in range(opcoes.invalidos):
        variacao = VARIACOES_INVALIDAS[indice % len(VARIACOES_INVALIDAS)]
        norte_metros, leste_metros = _ponto_no_disco(rng, RAIO_GERACAO_METROS)
        payload = _payload(
            rng,
            norte_metros,
            leste_metros,
            tipo=rng.choice(tipos),
            sessao_id=_nova_sessao(rng),
            descricao=f"SIMULAÇÃO: inválido ({variacao})",
        )
        if variacao == "latitude_fora_da_faixa":
            payload["latitude"] *= 10  # vírgula no lugar errado: -235,47°
        elif variacao == "tipo_inexistente":
            payload["tipo"] = "tipo_inexistente"
        elif variacao == "severidade_invalida":
            payload["severidade"] = 7
        elif variacao == "campo_faltando":
            del payload["sessao_id"]
        elif variacao == "campo_extra":
            payload["campo_extra"] = "campo que não existe no contrato"
        itens.append(ItemGerado("invalido", None, variacao, norte_metros, leste_metros, payload))
    return itens


# ---------------------------------------------------------------------------
# Banco (recebem a conexão; nunca fazem commit)
# ---------------------------------------------------------------------------


@dataclass
class ItemRegistrado:
    """Um item gerado e o que a entrada (`registrar_alerta`) respondeu para ele."""

    item: ItemGerado
    resultado: ResultadoEntrada


def ler_tipos_ativos(conexao: Connection) -> list[str]:
    """Códigos dos tipos de barreira ativos, em ordem alfabética (estável)."""
    linhas = conexao.execute(
        "SELECT codigo FROM tipos_barreira WHERE ativo ORDER BY codigo"
    ).fetchall()
    return [codigo for (codigo,) in linhas]


def contar_alertas_da_simulacao(conexao: Connection) -> int:
    return conexao.execute(
        "SELECT count(*) FROM alertas WHERE origem = %(origem)s", {"origem": ORIGEM}
    ).fetchone()[0]


def limpar_simulacao(conexao: Connection) -> dict[str, int]:
    """Apaga TODOS os dados `origem='simulacao'` e devolve quantas linhas saíram de
    cada tabela. A origem `real` nunca é tocada.

    Ordem das FKs: `alertas.barreira_id` referencia `barreiras`, então os alertas
    saem antes. `alertas_rejeitados` não tem FK. A linha de `execucoes_pipeline` da
    simulação também sai: ela descreve dados que deixaram de existir.

    Toma o mesmo advisory lock do pipeline (`CHAVE_LOCK_PIPELINE`): uma execução do
    pipeline disparada pela API ao mesmo tempo espera esta transação terminar.
    """
    conexao.execute(
        "SELECT pg_advisory_xact_lock(%(chave)s::bigint)", {"chave": CHAVE_LOCK_PIPELINE}
    )
    parametros = {"origem": ORIGEM}
    return {
        "alertas": conexao.execute(
            "DELETE FROM alertas WHERE origem = %(origem)s", parametros
        ).rowcount,
        "barreiras": conexao.execute(
            "DELETE FROM barreiras WHERE origem = %(origem)s", parametros
        ).rowcount,
        "alertas_rejeitados": conexao.execute(
            "DELETE FROM alertas_rejeitados WHERE origem = %(origem)s", parametros
        ).rowcount,
        "execucoes_pipeline": conexao.execute(
            "DELETE FROM execucoes_pipeline WHERE origem = %(origem)s", parametros
        ).rowcount,
    }


def registrar_populacoes(
    conexao: Connection, itens: Sequence[ItemGerado], *, config: Configuracoes
) -> list[ItemRegistrado]:
    """Envia cada payload por `registrar_alerta(..., origem="simulacao")`: o mesmo
    caminho de `POST /alertas` (estágios 1 e 2), nunca inserção direta (D2)."""
    return [
        ItemRegistrado(
            item=item,
            resultado=registrar_alerta(conexao, item.payload, origem=ORIGEM, config=config),
        )
        for item in itens
    ]


@dataclass(frozen=True)
class EstadoAlerta:
    status: str
    motivo_descarte: str | None
    barreira_id: int | None


@dataclass(frozen=True)
class EstadoFinal:
    """Fotografia da simulação no banco: TODOS os alertas e barreiras da origem,
    não só os desta execução (assim um alerta estranho numa barreira aparece)."""

    alertas: dict[int, EstadoAlerta]
    barreiras: dict[int, str]  # id → status


def ler_estado_final(conexao: Connection) -> EstadoFinal:
    """Status de cada alerta e de cada barreira da simulação, numa consulta só (um
    snapshot: alertas e barreiras sempre do mesmo instante)."""
    linhas = conexao.execute(
        """
        SELECT 'alerta', id, status, motivo_descarte, barreira_id
        FROM alertas WHERE origem = %(origem)s
        UNION ALL
        SELECT 'barreira', id, status, NULL, NULL
        FROM barreiras WHERE origem = %(origem)s
        """,
        {"origem": ORIGEM},
    ).fetchall()
    alertas: dict[int, EstadoAlerta] = {}
    barreiras: dict[int, str] = {}
    for tabela, id_, status, motivo_descarte, barreira_id in linhas:
        if tabela == "alerta":
            alertas[id_] = EstadoAlerta(status, motivo_descarte, barreira_id)
        else:
            barreiras[id_] = status
    return EstadoFinal(alertas=alertas, barreiras=barreiras)


# ---------------------------------------------------------------------------
# Avaliação (pura)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoCategoria:
    """Esperado × obtido de uma categoria. `unidade` diz o que se conta: GRUPOS
    (aglomerado, sessão repetida), ALERTAS (ruído, fora da área) ou PAYLOADS
    (inválidos, que nunca viram alerta)."""

    categoria: str
    unidade: str
    esperado: int
    obtido: int

    @property
    def taxa(self) -> float | None:
        """Taxa de acerto; `None` quando não havia nada a acertar."""
        return self.obtido / self.esperado if self.esperado else None


@dataclass
class Avaliacao:
    """Resultado do teste de eficácia.

    - `por_categoria`: acertos por categoria (ver `avaliar`).
    - `confusao`: categoria → destino final → contagem, em alertas (payloads para
      os inválidos). Só aparecem os destinos com contagem > 0.
    - `barreiras_esperadas`/`barreiras_obtidas`: por status. Esperadas vêm dos grupos
      GERADOS (um grupo reprovado na entrada continua no denominador); obtidas conta
      as barreiras do banco com pelo menos um alerta dos itens avaliados. Assim a
      mesma função avalia uma população de cada vez (a análise de sensibilidade
      separa o controle das sequências).
    - `barreiras_corretas`: grupos acertados, pelo status esperado.
    - `grupos_incompletos`: grupos com algum relato reprovado no estágio 1 ou ausente
      do banco. Nunca contam como acerto: o grupo gerado não chegou inteiro.
    - `grupos_fragmentados`: grupos completos cujos alertas não terminaram todos numa
      mesma barreira (divididos entre barreiras, ou em parte/todo ruído).
    - `fusoes_indevidas`: barreiras com alertas de mais de um grupo verdadeiro.
    - `ruido_em_barreira`: alertas de ruído que acabaram agrupados numa barreira.
    """

    por_categoria: dict[str, ResultadoCategoria]
    confusao: dict[str, dict[str, int]]
    barreiras_esperadas: dict[str, int]
    barreiras_obtidas: dict[str, int]
    barreiras_corretas: dict[str, int]
    grupos_incompletos: int
    grupos_fragmentados: int
    fusoes_indevidas: int
    ruido_em_barreira: int
    destinos: list[str] = field(repr=False, default_factory=list)


def destino_final(registrado: ItemRegistrado, estado: EstadoFinal) -> str:
    """Onde o item terminou: `rejeitado_schema` (estágio 1), `descartado:<motivo>`
    (estágio 2), `bruto`, `ruido_isolado` ou `barreira_<status>` (estágios 3 e 4)."""
    if not registrado.resultado.aceito:
        return "rejeitado_schema"
    alerta = estado.alertas.get(registrado.resultado.id)
    if alerta is None:
        return "ausente"
    if alerta.status == "descartado":
        return f"descartado:{alerta.motivo_descarte}"
    if alerta.status == "agrupado":
        return f"barreira_{estado.barreiras[alerta.barreira_id]}"
    return alerta.status


def status_esperado(sessoes_distintas: int, min_confirmacoes: int) -> str:
    """Status que um grupo gerado DEVERIA ter: `confirmada` se tem pelo menos
    `min_confirmacoes` sessões distintas, `pendente` se não.

    É a regra do estágio 4 (CLAUDE.md §6), escrita de novo aqui de propósito, sem
    chamar `decidir_status_barreira`: a verdade da simulação não pode depender do
    código que está sendo avaliado.
    """
    return "confirmada" if sessoes_distintas >= min_confirmacoes else "pendente"


def avaliar(
    registrados: Sequence[ItemRegistrado], estado: EstadoFinal, *, min_confirmacoes: int
) -> Avaliacao:
    """Compara o destino de cada item com a verdade de quem o gerou.

    Grupos (`aglomerado`, `sessao_repetida`): o status esperado de cada grupo vem das
    sessões distintas que ele tem na geração e de `min_confirmacoes`
    (`status_esperado`). Com os padrões (4 sessões por aglomerado, 1 por sessão
    repetida, min_confirmacoes = 3): aglomerado → `confirmada`, sessão repetida →
    `pendente`.

    Os grupos são os GERADOS, com todos os seus relatos, aceitos ou não. Um grupo é
    ACERTO quando todos os seus relatos viraram alertas, todos estão numa MESMA
    barreira, essa barreira tem o status esperado e não tem nenhum outro alerta (de
    outro grupo, de ruído ou de fora desta execução). Um relato reprovado na entrada
    ou ausente do banco torna o grupo incompleto; um grupo inteiro numa barreira de
    outro grupo é fusão; um grupo espalhado é fragmentação. Nenhum desses é acerto.

    Ruído, fora da área e inválidos: acerto por alerta (payload), quando o destino
    final é o esperado (`DESTINO_ESPERADO`).
    """
    destinos = [destino_final(r, estado) for r in registrados]

    confusao: dict[str, Counter[str]] = {categoria: Counter() for categoria in CATEGORIAS}
    for registrado, destino in zip(registrados, destinos, strict=True):
        confusao[registrado.item.categoria][destino] += 1

    membros_do_grupo: dict[tuple[str, int], list[ItemRegistrado]] = defaultdict(list)
    grupo_do_alerta: dict[int, tuple[str, int]] = {}
    for registrado in registrados:
        item = registrado.item
        if item.grupo is not None:
            chave = (item.categoria, item.grupo)
            membros_do_grupo[chave].append(registrado)
            if registrado.resultado.aceito:
                grupo_do_alerta[registrado.resultado.id] = chave

    membros_da_barreira: dict[int, set[int]] = defaultdict(set)
    for alerta_id, alerta in estado.alertas.items():
        if alerta.barreira_id is not None:
            membros_da_barreira[alerta.barreira_id].add(alerta_id)

    acertos_de_grupo: Counter[str] = Counter()
    esperadas: Counter[str] = Counter()
    corretas: Counter[str] = Counter()
    grupos_incompletos = grupos_fragmentados = 0
    for (categoria, _), membros in membros_do_grupo.items():
        status_do_grupo = status_esperado(
            len({m.item.payload.get("sessao_id") for m in membros}), min_confirmacoes
        )
        esperadas[status_do_grupo] += 1
        alerta_ids = {m.resultado.id for m in membros if m.resultado.aceito}
        if len(alerta_ids) < len(membros) or not alerta_ids <= estado.alertas.keys():
            grupos_incompletos += 1
            continue
        barreiras_do_grupo = {estado.alertas[i].barreira_id for i in alerta_ids}
        if len(barreiras_do_grupo) != 1 or None in barreiras_do_grupo:
            grupos_fragmentados += 1
            continue
        (barreira_id,) = barreiras_do_grupo
        if (
            membros_da_barreira[barreira_id] == alerta_ids
            and estado.barreiras[barreira_id] == status_do_grupo
        ):
            acertos_de_grupo[categoria] += 1
            corretas[status_do_grupo] += 1

    fusoes_indevidas = sum(
        1
        for membros in membros_da_barreira.values()
        if len({grupo_do_alerta[i] for i in membros if i in grupo_do_alerta}) > 1
    )

    por_categoria: dict[str, ResultadoCategoria] = {}
    for categoria in CATEGORIAS:
        if categoria in _CATEGORIAS_DE_GRUPO:
            esperado = sum(1 for chave in membros_do_grupo if chave[0] == categoria)
            obtido = acertos_de_grupo[categoria]
            unidade = "grupos"
        else:
            esperado = sum(confusao[categoria].values())
            obtido = confusao[categoria][DESTINO_ESPERADO[categoria]]
            unidade = "payloads" if categoria == "invalido" else "alertas"
        por_categoria[categoria] = ResultadoCategoria(categoria, unidade, esperado, obtido)

    barreiras_tocadas = {
        estado.alertas[r.resultado.id].barreira_id
        for r in registrados
        if r.resultado.aceito and r.resultado.id in estado.alertas
    } - {None}
    status_obtidos = Counter(estado.barreiras[i] for i in barreiras_tocadas)
    return Avaliacao(
        por_categoria=por_categoria,
        confusao={
            categoria: {destino: n for destino, n in contagem.items() if n}
            for categoria, contagem in confusao.items()
        },
        barreiras_esperadas={status: esperadas[status] for status in ("confirmada", "pendente")},
        barreiras_obtidas={
            "confirmada": status_obtidos["confirmada"],
            "pendente": status_obtidos["pendente"],
        },
        barreiras_corretas={status: corretas[status] for status in ("confirmada", "pendente")},
        grupos_incompletos=grupos_incompletos,
        grupos_fragmentados=grupos_fragmentados,
        fusoes_indevidas=fusoes_indevidas,
        ruido_em_barreira=sum(
            n for destino, n in confusao["ruido"].items() if destino.startswith("barreira_")
        ),
        destinos=destinos,
    )


# ---------------------------------------------------------------------------
# Saída (console e JSON)
# ---------------------------------------------------------------------------


def formatar_tabela(cabecalho: Sequence[str], linhas: Sequence[Sequence[object]]) -> str:
    """Tabela de texto. Colunas numéricas (números, percentuais, "—") à direita; as
    de texto, à esquerda."""
    textos = [[str(c) for c in cabecalho]] + [[str(c) for c in linha] for linha in linhas]
    larguras = [max(len(linha[i]) for linha in textos) for i in range(len(cabecalho))]
    a_direita = [
        all(_e_numerico(linha[indice]) for linha in linhas) for indice in range(len(cabecalho))
    ]

    def formatar(linha: list[str]) -> str:
        celulas = [
            celula.rjust(larguras[i]) if a_direita[i] else celula.ljust(larguras[i])
            for i, celula in enumerate(linha)
        ]
        return "  ".join(celulas).rstrip()

    separador = "  ".join("-" * largura for largura in larguras)
    return "\n".join([formatar(textos[0]), separador, *(formatar(t) for t in textos[1:])])


def _e_numerico(celula: object) -> bool:
    if isinstance(celula, int | float):
        return True
    return isinstance(celula, str) and (celula in ("", "—") or celula.endswith("%"))


def formatar_taxa(taxa: float | None) -> str:
    """ "100,0%" (vírgula decimal, como no texto do TCC) ou "—" sem nada a acertar."""
    return "—" if taxa is None else f"{taxa * 100:.1f}%".replace(".", ",")


def formatar_metros(valor_metros: float) -> str:
    return f"{valor_metros:g}".replace(".", ",") + " m"


def cabecalho_simulacao(titulo: str) -> str:
    linha = "=" * 78
    aviso = textwrap.fill(AVISO_SIMULACAO, width=78)
    return f"{linha}\n{ROTULO_SIMULACAO.upper()} · {titulo}\n{aviso}\n{linha}"


def formatar_geracao(
    itens: Sequence[ItemGerado],
    opcoes: OpcoesGeracao,
    *,
    eps_metros: float,
    min_confirmacoes: int,
) -> str:
    contagem = Counter(item.categoria for item in itens)
    grupos = {
        categoria: len({item.grupo for item in itens if item.categoria == categoria})
        for categoria in _CATEGORIAS_DE_GRUPO
    }
    fixo = opcoes.pontos_por_aglomerado
    if opcoes.sessoes_variaveis:
        sessoes_do_aglomerado = "sessões sorteadas de 2 a 5"
        destino_do_aglomerado = (
            f"1 barreira por grupo: confirmada se sessões ≥ {min_confirmacoes}, senão pendente"
        )
    else:
        sessoes_do_aglomerado = f"{fixo} sessões"
        destino_do_aglomerado = (
            f"1 barreira {status_esperado(fixo, min_confirmacoes)} por grupo "
            f"({fixo} sessões; min_confirmacoes = {min_confirmacoes})"
        )
    esperado = {
        "aglomerado": destino_do_aglomerado,
        "sessao_repetida": f"1 barreira {status_esperado(1, min_confirmacoes)} por grupo "
        "(1 sessão)",
        "ruido": "ruido_isolado",
        "fora_da_area": "descartado (fora_da_area)",
        "invalido": "rejeitado no schema (estágio 1)",
    }
    linhas = [
        [
            categoria,
            grupos.get(categoria, "—"),
            contagem[categoria],
            "payloads" if categoria == "invalido" else "alertas",
            esperado[categoria],
        ]
        for categoria in CATEGORIAS
        if contagem[categoria]
    ]
    linhas.append(["total", "", sum(contagem.values()), "", ""])
    separacao = FATOR_SEPARACAO * eps_metros
    return (
        f"[SIMULAÇÃO] Gerado (semente {opcoes.semente}; aglomerados com "
        f"{sessoes_do_aglomerado}, sessões repetidas com {fixo} relatos; dispersão de até "
        f"{formatar_metros(opcoes.dispersao_metros)}; separação mínima "
        f"{formatar_metros(separacao)} = {FATOR_SEPARACAO} × eps de "
        f"{formatar_metros(eps_metros)})\n"
        + formatar_tabela(
            ["categoria", "grupos", "enviados", "unidade", "destino esperado"], linhas
        )
    )


def formatar_entrada(registrados: Sequence[ItemRegistrado]) -> str:
    aceitos = [r.resultado for r in registrados if r.resultado.aceito]
    status = Counter(
        r.status if r.motivo_descarte is None else f"{r.status}/{r.motivo_descarte}"
        for r in aceitos
    )
    detalhes = ", ".join(f"{n} {s}" for s, n in sorted(status.items()))
    return (
        f"[SIMULAÇÃO] Entrada (estágios 1 e 2, registrar_alerta): {len(aceitos)} alertas "
        f"aceitos ({detalhes}); {len(registrados) - len(aceitos)} payloads rejeitados no schema"
    )


def formatar_execucao(resumo: ResumoExecucao) -> str:
    p = resumo.parametros
    return (
        f"[SIMULAÇÃO] Pipeline (estágios 3 e 4) com eps = {formatar_metros(p['eps_metros'])}, "
        f"minpoints = {p['min_pontos']}, min_confirmacoes = {p['min_confirmacoes']}:\n"
        f"  {resumo.alertas_processados} alertas processados: {resumo.agrupados} agrupados, "
        f"{resumo.ruido_isolado} ruído isolado; barreiras: {resumo.barreiras_confirmadas} "
        f"confirmadas, {resumo.barreiras_pendentes} pendentes"
    )


def formatar_avaliacao(avaliacao: Avaliacao) -> str:
    destinos = list(ORDEM_DESTINOS)
    for contagem in avaliacao.confusao.values():
        destinos += [d for d in contagem if d not in destinos]
    matriz = formatar_tabela(
        ["categoria \\ destino", *destinos, "total"],
        [
            [
                categoria,
                *(avaliacao.confusao[categoria].get(d, 0) for d in destinos),
                sum(avaliacao.confusao[categoria].values()),
            ]
            for categoria in CATEGORIAS
        ],
    )
    barreiras = formatar_tabela(
        ["status da barreira", "esperadas", "obtidas", "corretas"],
        [
            [
                status,
                avaliacao.barreiras_esperadas[status],
                avaliacao.barreiras_obtidas[status],
                avaliacao.barreiras_corretas[status],
            ]
            for status in ("confirmada", "pendente")
        ],
    )
    acertos = formatar_tabela(
        ["categoria", "unidade", "esperado", "obtido", "acerto"],
        [
            [r.categoria, r.unidade, r.esperado, r.obtido, formatar_taxa(r.taxa)]
            for r in avaliacao.por_categoria.values()
        ],
    )
    return "\n\n".join(
        [
            "[SIMULAÇÃO] Matriz categoria → destino final (em alertas; inválidos em payloads)\n"
            + matriz,
            "[SIMULAÇÃO] Barreiras esperadas × obtidas (aglomerado → confirmada, "
            "sessão repetida → pendente)\n" + barreiras,
            "[SIMULAÇÃO] Taxa de acerto por categoria\n" + acertos,
            "[SIMULAÇÃO] Grupos incompletos (relato reprovado na entrada ou ausente): "
            f"{avaliacao.grupos_incompletos} · fragmentados: {avaliacao.grupos_fragmentados}"
            f" · fusões indevidas: {avaliacao.fusoes_indevidas} · ruído classificado como "
            f"barreira: {avaliacao.ruido_em_barreira}",
        ]
    )


def avaliacao_para_json(avaliacao: Avaliacao) -> dict[str, Any]:
    return {
        "por_categoria": {
            c: {"unidade": r.unidade, "esperado": r.esperado, "obtido": r.obtido, "taxa": r.taxa}
            for c, r in avaliacao.por_categoria.items()
        },
        "confusao": avaliacao.confusao,
        "barreiras_esperadas": avaliacao.barreiras_esperadas,
        "barreiras_obtidas": avaliacao.barreiras_obtidas,
        "barreiras_corretas": avaliacao.barreiras_corretas,
        "grupos_incompletos": avaliacao.grupos_incompletos,
        "grupos_fragmentados": avaliacao.grupos_fragmentados,
        "fusoes_indevidas": avaliacao.fusoes_indevidas,
        "ruido_em_barreira": avaliacao.ruido_em_barreira,
    }


def gravar_json(caminho: Path, dados: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def caminho_para_exibir(caminho: Path) -> str:
    try:
        return str(caminho.relative_to(_RAIZ_REPO))
    except ValueError:
        return str(caminho)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def adicionar_opcoes_de_geracao(
    parser: argparse.ArgumentParser, padrao: OpcoesGeracao | None = None
) -> None:
    """Opções de `OpcoesGeracao`, compartilhadas com `analisar_sensibilidade`, que
    passa os seus próprios padrões em `padrao`."""
    padrao = padrao or OpcoesGeracao()
    grupo = parser.add_argument_group("geração (SIMULAÇÃO)")
    grupo.add_argument(
        "--semente",
        type=int,
        default=padrao.semente,
        help="semente do gerador aleatório (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--aglomerados",
        type=int,
        default=padrao.aglomerados,
        help="grupos de relatos de sessões distintas (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--pontos-por-aglomerado",
        type=int,
        default=padrao.pontos_por_aglomerado,
        help="relatos por grupo, nas duas populações de grupo (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--dispersao-metros",
        type=float,
        default=padrao.dispersao_metros,
        help="raio máximo, em metros, em torno do centro do grupo (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--sessao-repetida",
        type=int,
        default=padrao.sessao_repetida,
        help="grupos em que UMA sessão relata várias vezes (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--ruido", type=int, default=padrao.ruido, help="relatos isolados (padrão: %(default)s)"
    )
    grupo.add_argument(
        "--fora-da-area",
        type=int,
        default=padrao.fora_da_area,
        help="relatos entre 700 e 1500 m do centro (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--invalidos",
        type=int,
        default=padrao.invalidos,
        help="payloads malformados (padrão: %(default)s)",
    )
    grupo.add_argument(
        "--sessoes-variaveis",
        action=argparse.BooleanOptionalAction,
        default=padrao.sessoes_variaveis,
        help="cada aglomerado sorteia de 2 a 5 sessões distintas, em vez de "
        f"--pontos-por-aglomerado (padrão: {'sim' if padrao.sessoes_variaveis else 'não'})",
    )


def opcoes_dos_argumentos(args: argparse.Namespace) -> OpcoesGeracao:
    return OpcoesGeracao(
        **{campo.name: getattr(args, campo.name) for campo in fields(OpcoesGeracao)}
    )


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.gerar_dados_sinteticos",
        description=(
            "SIMULAÇÃO: gera dados sintéticos (origem='simulacao') no banco da "
            "configuração, pelo mesmo caminho da API, e avalia o pipeline de validação."
        ),
    )
    adicionar_opcoes_de_geracao(parser)
    parser.add_argument(
        "--limpar",
        action="store_true",
        help="apaga antes TODOS os dados origem='simulacao' (a origem 'real' nunca é tocada)",
    )
    parser.add_argument(
        "--executar-pipeline",
        action="store_true",
        help="roda o pipeline (estágios 3 e 4) com os parâmetros do .env",
    )
    parser.add_argument(
        "--avaliar",
        action="store_true",
        help="compara o resultado com a verdade de cada população (exige --executar-pipeline)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = criar_parser()
    args = parser.parse_args(argv)
    if args.avaliar and not args.executar_pipeline:
        parser.error("--avaliar exige --executar-pipeline: a avaliação lê o resultado do pipeline")
    try:
        opcoes = opcoes_dos_argumentos(args)
    except ValueError as erro:
        parser.error(str(erro))

    config = obter_configuracoes()
    print(cabecalho_simulacao("gerador e teste de eficácia do pipeline"))
    print(
        f"Banco: {config.postgres_db} em {config.postgres_host}:{config.postgres_porta} "
        f"(origem = '{ORIGEM}')\n"
    )

    resumo: ResumoExecucao | None = None
    avaliacao: Avaliacao | None = None
    apagados: dict[str, int] | None = None
    try:
        with psycopg.connect(config.conninfo) as conexao:
            if args.limpar:
                apagados = limpar_simulacao(conexao)
            else:
                existentes = contar_alertas_da_simulacao(conexao)
                if existentes:
                    print(
                        f"AVISO: já havia {existentes} alertas de simulação no banco e "
                        "--limpar não foi pedido. Eles se somam aos novos (a mesma semente "
                        "repete os mesmos pontos) e a avaliação sai distorcida.\n"
                    )
            tipos = ler_tipos_ativos(conexao)
            itens = gerar_populacoes(opcoes, tipos=tipos, eps_metros=config.dbscan_eps_metros)
            registrados = registrar_populacoes(conexao, itens, config=config)
            if args.executar_pipeline:
                resumo = executar_pipeline(
                    conexao,
                    origem=ORIGEM,
                    eps_metros=config.dbscan_eps_metros,
                    min_pontos=config.dbscan_min_points,
                    min_confirmacoes=config.min_confirmacoes,
                    srid_calculo=config.srid_calculo,
                    srid_armazenamento=config.srid_armazenamento,
                )
            if args.avaliar:
                avaliacao = avaliar(
                    registrados,
                    ler_estado_final(conexao),
                    min_confirmacoes=config.min_confirmacoes,
                )
            conexao.commit()
    except ValueError as erro:
        print(f"erro: {erro}. Nada foi gravado (rollback).", file=sys.stderr)
        return 1

    if apagados is not None:
        print(
            "[SIMULAÇÃO] --limpar apagou: "
            + ", ".join(f"{n} de {tabela}" for tabela, n in apagados.items())
            + "\n"
        )
    print(
        formatar_geracao(
            itens,
            opcoes,
            eps_metros=config.dbscan_eps_metros,
            min_confirmacoes=config.min_confirmacoes,
        )
        + "\n"
    )
    print(formatar_entrada(registrados) + "\n")
    if resumo is not None:
        print(formatar_execucao(resumo) + "\n")
        if not opcoes.sessoes_variaveis and opcoes.pontos_por_aglomerado < config.min_confirmacoes:
            print(
                f"AVISO: {opcoes.pontos_por_aglomerado} relatos por aglomerado com "
                f"MIN_CONFIRMACOES = {config.min_confirmacoes}: nenhum aglomerado pode ser "
                "confirmado.\n"
            )
    if avaliacao is not None:
        print(formatar_avaliacao(avaliacao) + "\n")

    caminho = DIRETORIO_SAIDA / f"simulacao-semente-{opcoes.semente}.json"
    gravar_json(
        caminho,
        {
            "rotulo": ROTULO_SIMULACAO,
            "aviso": AVISO_SIMULACAO,
            "gerado_em": datetime.now(UTC).isoformat(),
            "banco": config.postgres_db,
            "opcoes": asdict(opcoes),
            "separacao_minima_metros": FATOR_SEPARACAO * config.dbscan_eps_metros,
            "tipos": tipos,
            "limpeza": apagados,
            "pipeline": None
            if resumo is None
            else {
                **asdict(resumo),
                "executado_em": resumo.executado_em.astimezone(UTC).isoformat(),
            },
            "avaliacao": None if avaliacao is None else avaliacao_para_json(avaliacao),
            "itens": [
                {
                    "categoria": r.item.categoria,
                    "grupo": r.item.grupo,
                    "variacao": r.item.variacao,
                    "norte_metros": r.item.norte_metros,
                    "leste_metros": r.item.leste_metros,
                    "payload": r.item.payload,
                    "aceito": r.resultado.aceito,
                    "alerta_id": r.resultado.id,
                    "status_na_entrada": r.resultado.status,
                    "motivo_descarte": r.resultado.motivo_descarte,
                    "destino_final": None if avaliacao is None else avaliacao.destinos[indice],
                }
                for indice, r in enumerate(registrados)
            ],
        },
    )
    print(f"Commit feito: {len(registrados)} itens de SIMULAÇÃO gravados (origem='{ORIGEM}').")
    print(f"Relatório (SIMULAÇÃO): {caminho_para_exibir(caminho)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
