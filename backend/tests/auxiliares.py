"""Auxiliares dos testes dos estágios 3 e 4 (agrupamento e promoção).

Os testes do pipeline precisam montar cenários geométricos exatos ("dois alertas
a 5 m um do outro"). Converter metros em graus à mão (1° de latitude ≈ 111 km)
traria um erro de aproximação para dentro do próprio teste; `ponto_deslocado`
pede ao PostGIS o deslocamento geodésico exato, em `geography` (metros).

`inserir_alerta` grava direto por SQL, sem passar por `registrar_alerta`: estes
testes precisam de estados que a entrada nunca produz sozinha (`ruido_isolado`,
um `descartado` dentro da área, uma sessão repetida escolhida pelo teste).
"""

import math
from uuid import uuid4

import psycopg

from app.validacao.entrada import calcular_sessao_hash

# Centroide do campus Higienópolis (o mesmo centro do polígono provisório da área
# de estudo, db/seeds/002_area_estudo.sql): ponto de partida dos cenários.
LATITUDE_CAMPUS = -23.5471938
LONGITUDE_CAMPUS = -46.6524631


def ponto_deslocado(
    conexao: psycopg.Connection,
    latitude: float,
    longitude: float,
    norte_metros: float,
    leste_metros: float,
) -> tuple[float, float]:
    """(latitude, longitude) do ponto a `norte_metros` ao norte e `leste_metros` a
    leste do ponto dado (valores negativos: sul e oeste).

    Um único `ST_Project` em `geography`, com distância = hipotenusa e azimute
    medido a partir do norte no sentido horário (`atan2(leste, norte)`): a
    distância geodésica entre os dois pontos é exatamente a pedida, em metros.
    """
    distancia_metros = math.hypot(norte_metros, leste_metros)
    azimute_radianos = math.atan2(leste_metros, norte_metros)
    linha = conexao.execute(
        """
        SELECT ST_Y(p::geometry), ST_X(p::geometry)
        FROM ST_Project(
            ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography,
            %(distancia_metros)s,
            %(azimute_radianos)s
        ) AS p
        """,
        {
            "longitude": longitude,
            "latitude": latitude,
            "distancia_metros": distancia_metros,
            "azimute_radianos": azimute_radianos,
        },
    ).fetchone()
    return linha[0], linha[1]


def nova_sessao_hash() -> str:
    """Hash de uma sessão nova (D1), como a entrada gravaria."""
    return calcular_sessao_hash(uuid4())


def inserir_alerta(
    conexao: psycopg.Connection,
    *,
    latitude: float = LATITUDE_CAMPUS,
    longitude: float = LONGITUDE_CAMPUS,
    tipo: str = "degrau",
    sessao_hash: str | None = None,
    status: str = "bruto",
    motivo_descarte: str | None = None,
    barreira_id: int | None = None,
    origem: str = "simulacao",
) -> int:
    """Insere um alerta direto por SQL e devolve o `id`.

    Padrões: tipo `degrau`, status `bruto`, uma sessão NOVA a cada chamada
    (alertas de pessoas diferentes) e `origem='simulacao'` — dado de teste é
    sintético (G10); os testes que precisam de `real` pedem explicitamente.
    """
    linha = conexao.execute(
        """
        INSERT INTO alertas
            (geom, tipo_id, sessao_hash, status, motivo_descarte, barreira_id, origem)
        SELECT ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326), t.id,
               %(sessao_hash)s, %(status)s, %(motivo_descarte)s, %(barreira_id)s, %(origem)s
        FROM tipos_barreira t
        WHERE t.codigo = %(tipo)s
        RETURNING id
        """,
        {
            "longitude": longitude,
            "latitude": latitude,
            "tipo": tipo,
            "sessao_hash": sessao_hash if sessao_hash is not None else nova_sessao_hash(),
            "status": status,
            "motivo_descarte": motivo_descarte,
            "barreira_id": barreira_id,
            "origem": origem,
        },
    ).fetchone()
    if linha is None:
        raise ValueError(f"tipo de barreira inexistente no seed: {tipo!r}")
    return linha[0]
