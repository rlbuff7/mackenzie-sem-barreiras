"""Testes das estatísticas do funil de validação: `app/validacao/estatisticas.py`."""

from datetime import datetime

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.validacao.entrada import ORIGENS_VALIDAS
from app.validacao.estatisticas import ROTULOS_POR_ORIGEM, calcular_estatisticas
from app.validacao.pipeline import executar_pipeline
from tests.auxiliares import (
    LATITUDE_CAMPUS,
    LONGITUDE_CAMPUS,
    inserir_alerta,
    nova_sessao_hash,
    ponto_deslocado,
)

# G8: valores de teste explícitos, sem passar por Configuracoes.
_PARAMETROS = {"eps_metros": 8, "min_pontos": 2, "min_confirmacoes": 3}


def _alerta_em(conexao: psycopg.Connection, norte_metros: float, **campos: object) -> int:
    latitude, longitude = ponto_deslocado(
        conexao, LATITUDE_CAMPUS, LONGITUDE_CAMPUS, norte_metros, 0
    )
    return inserir_alerta(conexao, latitude=latitude, longitude=longitude, **campos)


def _inserir_rejeitado(conexao: psycopg.Connection, origem: str) -> None:
    conexao.execute(
        "INSERT INTO alertas_rejeitados (payload, erros, origem) VALUES (%s, %s, %s)",
        (Jsonb({"latitude": 200}), Jsonb([{"campo": "latitude", "erro": "..."}]), origem),
    )


def _executar_pipeline(conexao: psycopg.Connection) -> None:
    executar_pipeline(
        conexao,
        origem="simulacao",
        eps_metros=_PARAMETROS["eps_metros"],
        min_pontos=_PARAMETROS["min_pontos"],
        min_confirmacoes=_PARAMETROS["min_confirmacoes"],
        srid_calculo=31983,
        srid_armazenamento=4326,
    )


def _sem_gerado_em(estatisticas: dict) -> dict:
    return {chave: valor for chave, valor in estatisticas.items() if chave != "gerado_em"}


def test_contagens_batem_com_o_cenario_montado(conexao: psycopg.Connection) -> None:
    for _ in range(2):
        _inserir_rejeitado(conexao, "simulacao")
    for norte in (600, 700):
        _alerta_em(conexao, norte, status="descartado", motivo_descarte="fora_da_area")
    _alerta_em(conexao, 800, status="descartado", motivo_descarte="motivo_de_teste")
    for norte in (0, 1, 2):  # 3 sessões distintas: barreira confirmada
        _alerta_em(conexao, norte)
    sessao = nova_sessao_hash()
    for norte in (100, 101):  # 1 sessão só: barreira pendente
        _alerta_em(conexao, norte, sessao_hash=sessao)
    _alerta_em(conexao, 200)  # isolado: ruído
    _executar_pipeline(conexao)
    _alerta_em(conexao, 300)  # chegou depois da execução: aguardando o pipeline
    # Dados da outra origem não podem aparecer nas contagens de `simulacao`.
    _inserir_rejeitado(conexao, "real")
    _alerta_em(conexao, 0, origem="real")

    estatisticas = calcular_estatisticas(conexao, origem="simulacao", parametros=_PARAMETROS)

    assert _sem_gerado_em(estatisticas) == {
        "origem": "simulacao",
        "rotulo": "SIMULAÇÃO — dados sintéticos",
        "alertas": {
            "recebidos": 12,
            "rejeitados_schema": 2,
            "descartados": {"fora_da_area": 2, "motivo_de_teste": 1},
            "aguardando_pipeline": 1,
            "ruido_isolado": 1,
            "agrupados": 5,
        },
        "barreiras": {"total": 2, "pendentes": 1, "confirmadas": 1},
        "parametros": _PARAMETROS,
    }


def test_recebidos_e_a_soma_de_todos_os_estagios(conexao: psycopg.Connection) -> None:
    """Invariante do funil: todo alerta recebido termina em exatamente um estágio."""
    _inserir_rejeitado(conexao, "simulacao")
    _alerta_em(conexao, 600, status="descartado", motivo_descarte="fora_da_area")
    for norte in (0, 1, 50):
        _alerta_em(conexao, norte)
    _executar_pipeline(conexao)
    _alerta_em(conexao, 300)

    estatisticas = calcular_estatisticas(conexao, origem="simulacao", parametros=_PARAMETROS)

    alertas = estatisticas["alertas"]

    assert alertas["recebidos"] == (
        alertas["rejeitados_schema"]
        + sum(alertas["descartados"].values())
        + alertas["aguardando_pipeline"]
        + alertas["ruido_isolado"]
        + alertas["agrupados"]
    )


@pytest.mark.parametrize(
    ("origem", "rotulo"),
    [("real", "Dados reais de campo"), ("simulacao", "SIMULAÇÃO — dados sintéticos")],
)
def test_rotulo_por_origem(conexao: psycopg.Connection, origem: str, rotulo: str) -> None:
    estatisticas = calcular_estatisticas(conexao, origem=origem, parametros=_PARAMETROS)

    assert estatisticas["origem"] == origem
    assert estatisticas["rotulo"] == rotulo


def test_toda_origem_valida_tem_rotulo() -> None:
    assert set(ROTULOS_POR_ORIGEM) == set(ORIGENS_VALIDAS)


def test_banco_vazio_tem_fora_da_area_com_zero(conexao: psycopg.Connection) -> None:
    estatisticas = calcular_estatisticas(conexao, origem="real", parametros=_PARAMETROS)

    assert _sem_gerado_em(estatisticas) == {
        "origem": "real",
        "rotulo": "Dados reais de campo",
        "alertas": {
            "recebidos": 0,
            "rejeitados_schema": 0,
            "descartados": {"fora_da_area": 0},
            "aguardando_pipeline": 0,
            "ruido_isolado": 0,
            "agrupados": 0,
        },
        "barreiras": {"total": 0, "pendentes": 0, "confirmadas": 0},
        "parametros": _PARAMETROS,
    }


def test_gerado_em_e_iso_8601_com_fuso(conexao: psycopg.Connection) -> None:
    estatisticas = calcular_estatisticas(conexao, origem="real", parametros=_PARAMETROS)

    gerado_em = datetime.fromisoformat(estatisticas["gerado_em"])
    assert gerado_em.tzinfo is not None


def test_origem_invalida_levanta_value_error(conexao: psycopg.Connection) -> None:
    with pytest.raises(ValueError):
        calcular_estatisticas(conexao, origem="simulação", parametros=_PARAMETROS)
