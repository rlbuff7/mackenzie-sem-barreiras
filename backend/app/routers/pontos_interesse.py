"""`GET /pontos-interesse` (Contrato §9): pontos citáveis do campus dentro do bbox visível.

`bbox` é obrigatório (nunca o banco inteiro; a consulta usa o índice GiST). `tem_no`
diz se o ponto está ligado ao grafo, isto é, se pode ser origem ou destino de rota.
"""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.rotas.rotulos import ATRIBUICAO_OSM, rotulo_das_fontes
from app.routers.barreiras import interpretar_bbox

router = APIRouter()

TIPOS_DE_PONTO = ("predio", "entrada", "escada", "rampa", "quadra", "portao")


@router.get("/pontos-interesse")
def listar_pontos_de_interesse(
    bbox: str,
    conexao: ConexaoDaRequisicao,
    tipo: str | None = None,
    config: Configuracoes = Depends(obter_configuracoes),
) -> Any:
    try:
        min_lon, min_lat, max_lon, max_lat = interpretar_bbox(bbox)
    except ValueError as erro:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "bbox"),
                    "input": bbox,
                    "ctx": {"error": erro},
                }
            ]
        ) from erro

    tipos: list[str] | None = None
    if tipo is not None:
        tipos = [t.strip() for t in tipo.split(",")]
        invalidos = [t for t in tipos if t not in TIPOS_DE_PONTO]
        if invalidos:
            return JSONResponse(
                status_code=422,
                content={
                    "mensagem": "Requisição inválida.",
                    "erros": [
                        {
                            "campo": "tipo",
                            "erro": f"Tipo desconhecido: {', '.join(invalidos)}. "
                            f"Use: {', '.join(TIPOS_DE_PONTO)}.",
                        }
                    ],
                },
            )

    linhas = conexao.execute(
        """
        SELECT p.id, p.tipo, p.nome, p.descricao, p.acessivel, p.fonte_verificacao,
               p.mapeado_por, ST_AsGeoJSON(p.geom)::json,
               EXISTS (SELECT 1 FROM nos n WHERE n.ponto_interesse_id = p.id) AS tem_no
        FROM pontos_interesse p
        WHERE p.geom && ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, 4326)
          AND (%(tipos)s::text[] IS NULL OR p.tipo = ANY(%(tipos)s::text[]))
        ORDER BY p.nome, p.id
        LIMIT %(limite)s
        """,
        {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "tipos": tipos,
            "limite": config.limite_pontos_interesse_por_consulta,
        },
    ).fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": geometria,
            "properties": {
                "id": id_,
                "tipo": tipo_ponto,
                "nome": nome,
                "descricao": descricao,
                "acessivel": acessivel,
                "fonte_verificacao": fonte,
                "tem_no": tem_no,
            },
        }
        for id_, tipo_ponto, nome, descricao, acessivel, fonte, _por, geometria, tem_no in linhas
    ]
    colecao: dict[str, Any] = {
        "type": "FeatureCollection",
        "rotulo": rotulo_das_fontes({linha[5] for linha in linhas}) if linhas else "",
        "features": features,
    }
    if any(linha[6] and "OpenStreetMap" in linha[6] for linha in linhas):
        colecao["atribuicao"] = ATRIBUICAO_OSM
    return colecao
