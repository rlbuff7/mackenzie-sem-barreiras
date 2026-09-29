"""`GET /barreiras` (Contrato da API): barreiras validadas dentro do bbox visível."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.validacao.estatisticas import ROTULOS_POR_ORIGEM

router = APIRouter()


def interpretar_bbox(texto: str) -> tuple[float, float, float, float]:
    """Converte `minLon,minLat,maxLon,maxLat` (Contrato) em floats.

    Levanta `ValueError` com mensagem clara se o texto não tiver 4 números,
    se algum estiver fora da faixa de coordenadas geográficas, ou se o
    mínimo não for estritamente menor que o máximo — o router converte esse
    erro em HTTP 422.
    """
    partes = texto.split(",")
    if len(partes) != 4:
        raise ValueError(
            "bbox deve ter 4 valores separados por vírgula: minLon,minLat,maxLon,maxLat."
        )

    try:
        min_lon, min_lat, max_lon, max_lat = (float(parte) for parte in partes)
    except ValueError as erro:
        raise ValueError("bbox deve conter apenas números.") from erro

    if not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
        raise ValueError("longitude do bbox fora da faixa [-180, 180].")
    if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
        raise ValueError("latitude do bbox fora da faixa [-90, 90].")
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox inválido: o mínimo deve ser menor que o máximo.")

    return min_lon, min_lat, max_lon, max_lat


def buscar_barreiras_no_bbox(
    conexao: Connection,
    bbox: tuple[float, float, float, float],
    *,
    status: str | None,
    origem: str,
    limite: int,
    srid_armazenamento: int,
) -> dict[str, Any]:
    """Barreiras dentro do bbox, como GeoJSON `FeatureCollection` (Contrato).

    `rotulo`, no topo da coleção, é o mesmo texto das estatísticas para a origem
    ("SIMULAÇÃO — dados sintéticos" ou "Dados reais de campo", G10). O GeoJSON
    aceita membros extras no topo (RFC 7946, §6.1); quem não conhece o campo o
    ignora.

    `geom && ST_MakeEnvelope(...)` é o operador de sobreposição de bounding
    box: usa o índice GiST (`idx_barreiras_geom`), mais barato que
    `ST_Within`/`ST_Contains` para "o que está visível no mapa agora"
    (CLAUDE.md §4, §7).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    condicoes = [
        "b.geom && ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, %(srid)s)",
        "b.origem = %(origem)s",
    ]
    parametros: dict[str, Any] = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "srid": srid_armazenamento,
        "origem": origem,
        "limite": limite,
    }
    if status is not None:
        condicoes.append("b.status = %(status)s")
        parametros["status"] = status

    linhas = conexao.execute(
        f"""
        SELECT b.id, t.codigo AS tipo, t.nome AS tipo_nome, b.confirmacoes,
               b.status, b.atualizado_em, ST_AsGeoJSON(b.geom)::json AS geometria
        FROM barreiras b
        JOIN tipos_barreira t ON t.id = b.tipo_id
        WHERE {" AND ".join(condicoes)}
        ORDER BY b.id
        LIMIT %(limite)s
        """,
        parametros,
    ).fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": geometria,
            "properties": {
                "id": id_,
                "tipo": tipo,
                "tipo_nome": tipo_nome,
                "confirmacoes": confirmacoes,
                "status": status_barreira,
                "atualizado_em": atualizado_em.isoformat(),
            },
        }
        for id_, tipo, tipo_nome, confirmacoes, status_barreira, atualizado_em, geometria in linhas
    ]
    return {"type": "FeatureCollection", "rotulo": ROTULOS_POR_ORIGEM[origem], "features": features}


@router.get("/barreiras")
def listar_barreiras(
    bbox: str,
    conexao: ConexaoDaRequisicao,
    status: Literal["pendente", "confirmada"] | None = None,
    origem: Literal["real", "simulacao"] = "real",
    config: Configuracoes = Depends(obter_configuracoes),
) -> dict[str, Any]:
    try:
        bbox_interpretado = interpretar_bbox(bbox)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro

    return buscar_barreiras_no_bbox(
        conexao,
        bbox_interpretado,
        status=status,
        origem=origem,
        limite=config.limite_barreiras_por_consulta,
        srid_armazenamento=config.srid_armazenamento,
    )
