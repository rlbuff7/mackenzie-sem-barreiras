"""Endpoints de apoio ao frontend (D5): `/saude`, `/tipos-barreira`, `/area-estudo`.

Nenhuma lógica de validação aqui — isso é o M3, em `app/validacao/`. Respostas
geográficas em GeoJSON (D5), sempre com dados reais do banco (CLAUDE.md §7).
"""

import json
from typing import Any

from fastapi import APIRouter, Depends
from psycopg import Connection

from app.db import obter_conexao

router = APIRouter()


@router.get("/saude")
def saude(conexao: Connection = Depends(obter_conexao)) -> dict[str, str]:
    """Confirma que a API está de pé e que o banco responde a uma consulta trivial.

    Se o banco não responder, `obter_conexao` já devolve 503 antes de chegar
    aqui (pool sem conexões disponíveis); veja `app/db.py`.
    """
    conexao.execute("SELECT 1")
    return {"status": "ok", "banco": "ok"}


@router.get("/tipos-barreira")
def tipos_barreira(conexao: Connection = Depends(obter_conexao)) -> list[dict[str, Any]]:
    """Taxonomia ativa de barreiras (CLAUDE.md §4), para o formulário do frontend."""
    linhas = conexao.execute(
        """
        SELECT codigo, nome, descricao
        FROM tipos_barreira
        WHERE ativo
        ORDER BY nome
        """
    ).fetchall()
    return [
        {"codigo": codigo, "nome": nome, "descricao": descricao}
        for codigo, nome, descricao in linhas
    ]


@router.get("/area-estudo")
def area_estudo(conexao: Connection = Depends(obter_conexao)) -> dict[str, Any]:
    """Polígono(s) da área de estudo (CLAUDE.md §4), contra o qual o geofence roda."""
    linhas = conexao.execute(
        """
        SELECT nome, descricao, ST_AsGeoJSON(geom) AS geometria_geojson
        FROM area_estudo
        ORDER BY nome
        """
    ).fetchall()
    features = [
        {
            "type": "Feature",
            "properties": {"nome": nome, "descricao": descricao},
            "geometry": json.loads(geometria_geojson),
        }
        for nome, descricao, geometria_geojson in linhas
    ]
    return {"type": "FeatureCollection", "features": features}
