"""Testes do estágio 2 (geofence): `app/validacao/geofence.py`."""

import psycopg

from app.validacao.geofence import ponto_dentro_da_area

# G8: valor de teste explícito, sem passar por Configuracoes.
_SRID_ARMAZENAMENTO = 4326


def test_centro_do_campus_esta_dentro_da_area(conexao: psycopg.Connection) -> None:
    dentro = ponto_dentro_da_area(conexao, -23.5471938, -46.6524631, _SRID_ARMAZENAMENTO)

    assert dentro is True


def test_masp_esta_fora_da_area(conexao: psycopg.Connection) -> None:
    dentro = ponto_dentro_da_area(conexao, -23.5614, -46.6558, _SRID_ARMAZENAMENTO)

    assert dentro is False


def test_sem_area_cadastrada_devolve_falso(conexao: psycopg.Connection) -> None:
    conexao.execute("DELETE FROM area_estudo")

    dentro = ponto_dentro_da_area(conexao, -23.5471938, -46.6524631, _SRID_ARMAZENAMENTO)

    assert dentro is False
