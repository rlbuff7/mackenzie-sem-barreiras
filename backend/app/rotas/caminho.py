"""Caminho mais barato entre dois nós, com `pgr_dijkstra` (pgRouting).

O custo é calculado AQUI, na hora da consulta (comprimento × fator de `custo.py`), e
entregue ao pgRouting como uma lista de arestas em `VALUES`. Assim há uma só fórmula
(a de Python, testada) e mudar uma penalidade no `.env` vale sem refazer seed. O grafo
do campus tem dezenas ou centenas de arestas: carregá-lo inteiro é barato.

Segurança: para o perfil `cadeirante`, escada e trecho inacessível nem entram na lista
de arestas (`trecho_proibido`). Não há penalidade alta que "talvez" permita a escada.

Os valores que entram no texto SQL do pgRouting vêm do banco (inteiros e floats), nunca
do cliente; mesmo assim passam por `int()` e `float()` antes de virar texto.
"""

from psycopg import Connection

from app.config import Configuracoes
from app.rotas.custo import Perfil, fator_do_trecho, trecho_proibido
from app.rotas.modelos import Trecho


def _sql_das_arestas(conexao: Connection, perfil: Perfil, config: Configuracoes) -> str | None:
    """Texto SQL da lista de arestas do perfil, ou `None` se não sobrou nenhuma."""
    linhas = []
    for id_, origem, destino, comprimento, tipo, acessivel, fonte, custo_inverso in conexao.execute(
        """SELECT id, origem_id, destino_id, comprimento_m, tipo, acessivel_cadeirante,
                      fonte_verificacao, custo_inverso FROM arestas ORDER BY id"""
    ).fetchall():
        if trecho_proibido(tipo=tipo, acessivel_cadeirante=acessivel, perfil=perfil):
            continue
        fator = fator_do_trecho(
            tipo=tipo,
            acessivel_cadeirante=acessivel,
            fonte_verificacao=fonte,
            perfil=perfil,
            config=config,
        )
        custo = float(comprimento) * fator
        inverso = -1.0 if custo_inverso == -1 else custo
        linhas.append(f"({int(id_)}, {int(origem)}, {int(destino)}, {custo!r}, {inverso!r})")
    if not linhas:
        return None
    return (
        "SELECT id, source, target, cost, reverse_cost FROM (VALUES "
        + ", ".join(linhas)
        + ") AS t(id, source, target, cost, reverse_cost)"
    )


def calcular_caminho(
    conexao: Connection,
    *,
    no_origem: int,
    no_destino: int,
    perfil: Perfil,
    config: Configuracoes,
) -> list[Trecho] | None:
    """Trechos em ordem, já orientados no sentido do caminho; `None` se não há caminho."""
    sql_arestas = _sql_das_arestas(conexao, perfil, config)
    if sql_arestas is None:
        return None
    passos = conexao.execute(
        "SELECT edge, node, cost FROM pgr_dijkstra(%s, %s::bigint, %s::bigint, directed := true) "
        "WHERE edge <> -1 ORDER BY seq",
        (sql_arestas, no_origem, no_destino),
    ).fetchall()
    if not passos:
        return None

    linhas = conexao.execute(
        """
        SELECT p.ord, a.id, a.tipo, a.comprimento_m, a.acessivel_cadeirante,
               a.fonte_verificacao, p.de,
               CASE WHEN p.de = a.origem_id THEN a.destino_id ELSE a.origem_id END,
               ST_AsGeoJSON(
                   CASE WHEN p.de = a.origem_id THEN a.geom ELSE ST_Reverse(a.geom) END
               )::json,
               a.mapeado_por, p.custo
        FROM unnest(%s::bigint[], %s::bigint[], %s::float8[])
             WITH ORDINALITY AS p(aresta, de, custo, ord)
        JOIN arestas a ON a.id = p.aresta
        ORDER BY p.ord
        """,
        ([p[0] for p in passos], [p[1] for p in passos], [p[2] for p in passos]),
    ).fetchall()
    return [
        Trecho(
            aresta_id=id_,
            tipo=tipo,
            comprimento_m=float(comprimento),
            acessivel_cadeirante=acessivel,
            fonte_verificacao=fonte,
            no_de=de,
            no_para=para,
            custo=float(custo),
            coordenadas=geojson["coordinates"],
            mapeado_por=por,
        )
        for _ord, id_, tipo, comprimento, acessivel, fonte, de, para, geojson, por, custo in linhas
    ]


def concatenar_geometria(trechos: list[Trecho]) -> list[list[float]]:
    """Uma linha só, sem repetir o vértice de junção entre trechos."""
    linha: list[list[float]] = []
    for trecho in trechos:
        coords = trecho.coordenadas
        linha.extend(coords[1:] if linha else coords)
    return linha
