"""Figura do funil de validação, a partir das estatísticas do banco (CLAUDE.md §6-7).

Lê `calcular_estatisticas(origem=...)`, a mesma função de
`GET /validacao/estatisticas`, e desenha o funil em SVG e PNG em
`docs/figuras/funil-<origem>.svg|png`. Os números vêm sempre do banco, nunca de
valores fixos.

Uso (a partir de `backend/`; o matplotlib fica num grupo opcional):

    uv sync --group analise
    uv run python -m scripts.gerar_figura_funil --origem simulacao

Decisões da figura:

- **Unidade explícita.** O funil do pôster do TCC I trocava de unidade no meio
  (alertas → barreiras) sem avisar. Aqui são dois painéis, cada um com o seu eixo:
  o de cima conta ALERTAS, o de baixo conta BARREIRAS. Um eixo só misturaria as
  duas escalas.
- **Parâmetros da execução, não da configuração.** A legenda usa `parametros` e
  `executado_em` das estatísticas, que são os da ÚLTIMA execução do pipeline daquela
  origem (R14). Se a origem nunca foi processada, não há figura: o script para e
  pede para rodar o pipeline antes.
- **Honestidade (G10).** Com `origem=simulacao` o título começa com "SIMULAÇÃO" e o
  subtítulo diz que os dados são sintéticos.
- **Cor = estágio.** Um só tom de azul, do claro (entrada) ao escuro (estágio 4),
  validado como rampa ordinal pelo validador da skill `dataviz`. "Agrupados" e
  "barreiras formadas" são o mesmo estágio 3 contado em duas unidades, e por isso
  têm a mesma cor. Os textos usam tinta neutra, nunca a cor das barras.
"""

import argparse
import sys
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from app.config import obter_configuracoes
from app.validacao.entrada import ORIGENS_VALIDAS
from app.validacao.estatisticas import calcular_estatisticas
from scripts.gerar_dados_sinteticos import formatar_metros

_RAIZ_REPO = Path(__file__).resolve().parent.parent.parent
DIRETORIO_FIGURAS = _RAIZ_REPO / "docs" / "figuras"


class OrigemNaoProcessada(Exception):
    """A origem nunca passou pelo pipeline: não há parâmetros que expliquem o funil."""


@dataclass(frozen=True)
class Estagio:
    """Uma barra do funil. `unidade` é "alertas" ou "barreiras"; `nota` diz o que
    saiu neste estágio; `passo` (0 a 4) é o estágio do pipeline e escolhe a cor."""

    rotulo: str
    detalhe: str
    valor: int
    unidade: str
    nota: str | None
    passo: int


@dataclass(frozen=True)
class Funil:
    origem: str
    titulo: str
    subtitulo: str
    legenda: str
    fonte: str
    estagios: list[Estagio]


def _numero(valor: int) -> str:
    """1234 → "1.234" (separador de milhar do português)."""
    return f"{valor:,}".replace(",", ".")


def _instante(texto_iso: str) -> str:
    """ISO-8601 em UTC → "2026-09-29 03:10 UTC"."""
    return datetime.fromisoformat(texto_iso).strftime("%Y-%m-%d %H:%M UTC")


def montar_funil(estatisticas: dict[str, Any]) -> Funil:
    """Transforma a resposta de `calcular_estatisticas` nos estágios da figura.

    Alertas: recebidos → passaram do schema (estágio 1) → dentro da área
    (estágio 2) → agrupados em clusters (estágio 3). Barreiras: formadas pelos
    clusters (estágio 3) → confirmadas (estágio 4). Cada estágio diz, na `nota`,
    quanto saiu nele e por quê.

    `OrigemNaoProcessada` se `parametros` for `None`: sem execução do pipeline não
    há parâmetros para a legenda, e uma figura assim não poderia ser lida.
    """
    origem = estatisticas["origem"]
    parametros = estatisticas["parametros"]
    if parametros is None:
        como_rodar = (
            "`uv run python -m scripts.gerar_dados_sinteticos --limpar --executar-pipeline`"
            if origem == "simulacao"
            else f"`POST /validacao/executar?origem={origem}`"
        )
        raise OrigemNaoProcessada(
            f"A origem '{origem}' nunca foi processada pelo pipeline: rode o pipeline antes "
            f"({como_rodar}). Sem uma execução não há parâmetros que expliquem os números "
            "da figura."
        )

    alertas = estatisticas["alertas"]
    barreiras = estatisticas["barreiras"]
    descartados = alertas["descartados"]
    passaram_schema = alertas["recebidos"] - alertas["rejeitados_schema"]
    dentro_da_area = passaram_schema - sum(descartados.values())

    saiu_no_geofence = [f"−{_numero(descartados['fora_da_area'])} fora da área"]
    saiu_no_geofence += [
        f"−{_numero(n)} descartados ({motivo})"
        for motivo, n in descartados.items()
        if motivo != "fora_da_area"
    ]
    saiu_no_agrupamento = [f"−{_numero(alertas['ruido_isolado'])} ruído isolado"]
    if alertas["aguardando_pipeline"]:
        saiu_no_agrupamento.append(
            f"−{_numero(alertas['aguardando_pipeline'])} aguardando o pipeline"
        )

    estagios = [
        Estagio("Recebidos", "todos os relatos", alertas["recebidos"], "alertas", None, 0),
        Estagio(
            "Passaram do schema",
            "estágio 1",
            passaram_schema,
            "alertas",
            f"−{_numero(alertas['rejeitados_schema'])} reprovados no schema",
            1,
        ),
        Estagio(
            "Dentro da área",
            "estágio 2 (geofence)",
            dentro_da_area,
            "alertas",
            ", ".join(saiu_no_geofence),
            2,
        ),
        Estagio(
            "Agrupados em clusters",
            "estágio 3 (DBSCAN)",
            alertas["agrupados"],
            "alertas",
            ", ".join(saiu_no_agrupamento),
            3,
        ),
        Estagio(
            "Barreiras formadas",
            "estágio 3 (uma por cluster)",
            barreiras["total"],
            "barreiras",
            f"dos {_numero(alertas['agrupados'])} alertas agrupados",
            3,
        ),
        Estagio(
            "Barreiras confirmadas",
            "estágio 4 (sessões distintas)",
            barreiras["confirmadas"],
            "barreiras",
            f"{_numero(barreiras['pendentes'])} pendentes "
            f"(menos de {parametros['min_confirmacoes']} sessões distintas)",
            4,
        ),
    ]

    if origem == "simulacao":
        titulo = "SIMULAÇÃO — funil de validação dos alertas"
        subtitulo = (
            "Dados sintéticos (origem = simulacao), gerados para testar o pipeline.\n"
            "Não são resultado de coleta real."
        )
    else:
        titulo = "Funil de validação dos alertas — dados reais de campo"
        subtitulo = "Relatos de voluntários (origem = real)."
    legenda = (
        "Parâmetros da última execução do pipeline: "
        f"eps = {formatar_metros(parametros['eps_metros'])} · "
        f"minpoints = {parametros['min_pontos']} · "
        f"min_confirmacoes = {parametros['min_confirmacoes']}\n"
        f"Execução de {_instante(estatisticas['executado_em'])}, a que produziu os números acima."
    )
    fonte = (
        f"Fonte: GET /validacao/estatisticas?origem={origem}, consultado em "
        f"{_instante(estatisticas['gerado_em'])}."
    )
    return Funil(origem, titulo, subtitulo, legenda, fonte, estagios)


# ---------------------------------------------------------------------------
# Desenho (matplotlib, grupo opcional `analise`; não é testado)
# ---------------------------------------------------------------------------

# Rampa ordinal de um tom (paleta de referência da skill `dataviz`, azul 250 → 650),
# validada com `validate_palette.js --ordinal --surface "#ffffff"`: luminosidade
# monotônica, ΔL ≥ 0,06 entre vizinhos, o passo mais claro a 2,11:1 do fundo.
_COR_DO_PASSO = ("#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281")
_FUNDO = "#ffffff"
_TINTA = "#0b0b0b"
_TINTA_SECUNDARIA = "#52514e"
_TINTA_APAGADA = "#898781"
_GRADE = "#e1e0d9"
_LINHA_DE_BASE = "#c3c2b7"

# Medidas em polegadas (a figura é pensada para a largura de texto de uma página A4).
_LARGURA = 6.5
_MARGEM_ESQUERDA = 2.05
_MARGEM_DIREITA = 0.2
_ALTURA_DA_LINHA_PT = 30  # uma linha por estágio
_ESPESSURA_DA_BARRA_PT = 15  # ≤ 18 pt (24 px), como pede a skill
_RAIO_DA_PONTA_PT = 3  # ~4 px: ponta arredondada, base reta


def desenhar_funil(funil: Funil, caminho_base: Path) -> list[Path]:
    """Desenha o funil e grava `<caminho_base>.svg` e `.png`. Devolve os caminhos.

    A página é montada de cima para baixo, em polegadas: título, subtítulo, os dois
    painéis (cabeçalho, barras, eixo x) e o rodapé com os parâmetros e a fonte. Os
    textos longos quebram em linhas, e a altura da figura acompanha.
    """
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "svg.hashsalt": "mackenzie-sem-barreiras",  # SVG reproduzível
            "axes.unicode_minus": True,
        }
    )

    paineis = [
        ("ALERTAS", "cada barra conta alertas", "alertas"),
        (
            "BARREIRAS",
            "cada barra conta barreiras; vários alertas agrupados formam uma barreira",
            "barreiras",
        ),
    ]
    # (texto, tamanho em pt, cor, negrito, caracteres por linha)
    topo = [
        (funil.titulo, 12, _TINTA, True, 80),
        (funil.subtitulo, 8.5, _TINTA_SECUNDARIA, False, 95),
    ]
    rodape = [
        (funil.legenda, 7.5, _TINTA_SECUNDARIA, False, 105),
        (funil.fonte, 7, _TINTA_APAGADA, False, 112),
    ]
    altura_dos_eixos = {
        unidade: sum(1 for e in funil.estagios if e.unidade == unidade) * _ALTURA_DA_LINHA_PT / 72
        for _, _, unidade in paineis
    }
    cabecalho_do_painel, eixo_x, entre_paineis, margem = 0.34, 0.3, 0.22, 0.2
    altura_total = (
        2 * margem
        + _altura_dos_textos(topo)
        + 0.12
        + sum(cabecalho_do_painel + a + eixo_x for a in altura_dos_eixos.values())
        + entre_paineis
        + _altura_dos_textos(rodape)
    )

    figura = Figure(figsize=(_LARGURA, altura_total), facecolor=_FUNDO)
    canvas = FigureCanvasAgg(figura)
    x_texto = 0.18 / _LARGURA

    def y_da_figura(polegadas_do_topo: float) -> float:
        return 1 - polegadas_do_topo / altura_total

    def escrever(blocos: list, cursor: float) -> float:
        for texto, tamanho, cor, negrito, por_linha in blocos:
            linhas = _quebrar(texto, por_linha)
            figura.text(
                x_texto,
                y_da_figura(cursor),
                "\n".join(linhas),
                fontsize=tamanho,
                color=cor,
                fontweight="bold" if negrito else "normal",
                va="top",
                linespacing=1.35,
            )
            cursor += _altura_dos_textos([(texto, tamanho, cor, negrito, por_linha)])
        return cursor

    cursor = escrever(topo, margem) + 0.12
    eixos = []
    for nome, explicacao, unidade in paineis:
        for x_polegadas, texto, tamanho, negrito, cor in (
            (0.18, nome, 9, True, _TINTA),
            (1.13, explicacao, 8, False, _TINTA_SECUNDARIA),
        ):
            figura.text(
                x_polegadas / _LARGURA,
                y_da_figura(cursor + 0.08),
                texto,
                fontsize=tamanho,
                fontweight="bold" if negrito else "normal",
                color=cor,
                va="top",
            )
        cursor += cabecalho_do_painel
        altura_eixo = altura_dos_eixos[unidade]
        eixo = figura.add_axes(
            (
                _MARGEM_ESQUERDA / _LARGURA,
                y_da_figura(cursor + altura_eixo),
                (_LARGURA - _MARGEM_ESQUERDA - _MARGEM_DIREITA) / _LARGURA,
                altura_eixo / altura_total,
            ),
            facecolor=_FUNDO,
        )
        eixos.append((eixo, [e for e in funil.estagios if e.unidade == unidade]))
        cursor += altura_eixo + eixo_x + entre_paineis
    escrever(rodape, cursor - entre_paineis + 0.1)

    for eixo, estagios in eixos:
        _desenhar_painel(eixo, estagios, canvas)

    caminho_base.parent.mkdir(parents=True, exist_ok=True)
    caminhos = [caminho_base.with_suffix(".svg"), caminho_base.with_suffix(".png")]
    figura.savefig(caminhos[0], format="svg", metadata={"Date": None}, facecolor=_FUNDO)
    figura.savefig(caminhos[1], format="png", dpi=200, facecolor=_FUNDO)
    return caminhos


def _quebrar(texto: str, por_linha: int) -> list[str]:
    """Quebra cada parágrafo (separado por "\\n") em linhas de até `por_linha`
    caracteres."""
    return [
        linha for paragrafo in texto.split("\n") for linha in textwrap.wrap(paragrafo, por_linha)
    ]


def _altura_dos_textos(blocos: list) -> float:
    """Altura, em polegadas, dos blocos de texto quebrados em linhas (mais um respiro)."""
    return sum(
        len(_quebrar(texto, por_linha)) * tamanho * 1.35 / 72 + 0.06
        for texto, tamanho, _, _, por_linha in blocos
    )


def _desenhar_painel(eixo: Any, estagios: Sequence[Estagio], canvas: Any) -> None:
    """Um painel: linhas de cima para baixo, rótulos à esquerda, valor na ponta."""
    from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    quantidade = len(estagios)
    eixo.set_ylim(quantidade - 0.5, -0.5)  # primeira linha em cima
    maior_valor = max((e.valor for e in estagios), default=0) or 1
    eixo.set_xlim(0, maior_valor)

    for spine in eixo.spines.values():
        spine.set_visible(False)
    eixo.set_yticks([])
    eixo.tick_params(axis="x", length=0, colors=_TINTA_APAGADA, labelsize=7.5, pad=4)
    eixo.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    eixo.xaxis.set_major_formatter(FuncFormatter(lambda valor, _: _numero(int(valor))))
    eixo.grid(axis="x", color=_GRADE, linewidth=0.75, linestyle="-")
    eixo.set_axisbelow(True)
    eixo.axvline(0, color=_LINHA_DE_BASE, linewidth=0.75, zorder=1)

    anotacoes = []
    for linha, estagio in enumerate(estagios):
        eixo.text(
            -0.03,
            linha - 0.06,
            estagio.rotulo,
            transform=eixo.get_yaxis_transform(),
            ha="right",
            va="bottom",
            fontsize=9,
            color=_TINTA,
        )
        eixo.text(
            -0.03,
            linha + 0.02,
            estagio.detalhe,
            transform=eixo.get_yaxis_transform(),
            ha="right",
            va="top",
            fontsize=7.5,
            color=_TINTA_SECUNDARIA,
        )
        valor = _numero(estagio.valor) + (f" {estagio.unidade}" if linha == 0 else "")
        partes = [TextArea(valor, textprops={"fontsize": 9, "fontweight": "bold", "color": _TINTA})]
        if estagio.nota:
            partes.append(
                TextArea(estagio.nota, textprops={"fontsize": 7.5, "color": _TINTA_SECUNDARIA})
            )
        anotacao = AnnotationBbox(
            HPacker(children=partes, align="baseline", pad=0, sep=6),
            (estagio.valor, linha),
            xybox=(5, 0),
            xycoords="data",
            boxcoords="offset points",
            box_alignment=(0, 0.5),
            frameon=False,
            annotation_clip=False,
        )
        eixo.add_artist(anotacao)
        anotacoes.append((estagio.valor, anotacao))

    # O texto na ponta tem largura fixa (em pontos); o eixo cresce até todo rótulo
    # caber dentro dele, sem cortar nem vazar da figura.
    canvas.draw()
    renderer = canvas.get_renderer()
    largura_px = eixo.bbox.width
    limite = maior_valor
    for valor, anotacao in anotacoes:
        texto_px = anotacao.get_window_extent(renderer).width + 5 * eixo.figure.dpi / 72
        if texto_px < largura_px:
            limite = max(limite, valor * largura_px / (largura_px - texto_px))
    eixo.set_xlim(0, limite * 1.02)

    for linha, estagio in enumerate(estagios):
        if estagio.valor > 0:
            _barra_com_ponta_arredondada(eixo, estagio.valor, linha, _COR_DO_PASSO[estagio.passo])


def _barra_com_ponta_arredondada(eixo: Any, valor: float, linha: int, cor: str) -> None:
    """Barra horizontal com a ponta arredondada (raio ~4 px) e a base reta.

    A curva é desenhada em coordenadas de dados, que têm escalas diferentes em x e
    y; os raios são convertidos de pontos para cada eixo, para que a curva saia
    redonda na tela.
    """
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as Caminho

    dpi = eixo.figure.dpi
    x_min, x_max = eixo.get_xlim()
    y_baixo, y_alto = eixo.get_ylim()
    pixels_por_x = eixo.bbox.width / (x_max - x_min)
    pixels_por_y = eixo.bbox.height / abs(y_alto - y_baixo)
    raio_px = _RAIO_DA_PONTA_PT * dpi / 72
    meia_espessura = _ESPESSURA_DA_BARRA_PT * dpi / 72 / pixels_por_y / 2
    raio_x = min(raio_px / pixels_por_x, valor / 2)
    raio_y = min(raio_px / pixels_por_y, meia_espessura)

    topo, base = linha - meia_espessura, linha + meia_espessura
    vertices = [
        (0, topo),
        (valor - raio_x, topo),
        (valor, topo),
        (valor, topo + raio_y),
        (valor, base - raio_y),
        (valor, base),
        (valor - raio_x, base),
        (0, base),
        (0, topo),
    ]
    codigos = [
        Caminho.MOVETO,
        Caminho.LINETO,
        Caminho.CURVE3,
        Caminho.CURVE3,
        Caminho.LINETO,
        Caminho.CURVE3,
        Caminho.CURVE3,
        Caminho.LINETO,
        Caminho.CLOSEPOLY,
    ]
    eixo.add_patch(PathPatch(Caminho(vertices, codigos), facecolor=cor, edgecolor="none", zorder=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.gerar_figura_funil",
        description=(
            "Desenha o funil de validação a partir das estatísticas do banco, com os "
            "parâmetros da última execução do pipeline daquela origem."
        ),
    )
    parser.add_argument(
        "--origem",
        required=True,
        choices=sorted(ORIGENS_VALIDAS),
        help="de que origem são os dados do funil",
    )
    args = parser.parse_args(argv)

    config = obter_configuracoes()
    with psycopg.connect(config.conninfo) as conexao:
        estatisticas = calcular_estatisticas(conexao, origem=args.origem)
        conexao.rollback()  # só leitura

    try:
        funil = montar_funil(estatisticas)
    except OrigemNaoProcessada as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1

    try:
        caminhos = desenhar_funil(funil, DIRETORIO_FIGURAS / f"funil-{args.origem}")
    except ModuleNotFoundError as erro:
        if erro.name != "matplotlib":
            raise
        print(
            "erro: matplotlib não está instalado; rode `uv sync --group analise`.", file=sys.stderr
        )
        return 1

    print(funil.titulo)
    print(funil.legenda)
    for caminho in caminhos:
        print(f"Figura: {caminho.relative_to(_RAIZ_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
