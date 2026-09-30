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
# Diferentes dos do `.env` de propósito: provam que as estatísticas mostram os
# parâmetros da execução, não os da configuração.
_PARAMETROS_FORA_DA_CONFIG = {"eps_metros": 4.5, "min_pontos": 3, "min_confirmacoes": 2}


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


def _executar_pipeline(
    conexao: psycopg.Connection, origem: str = "simulacao", parametros: dict = _PARAMETROS
) -> None:
    executar_pipeline(
        conexao,
        origem=origem,
        eps_metros=parametros["eps_metros"],
        min_pontos=parametros["min_pontos"],
        min_confirmacoes=parametros["min_confirmacoes"],
        srid_calculo=31983,
        srid_armazenamento=4326,
    )


def _agora(conexao: psycopg.Connection) -> datetime:
    """`now()` da transação do teste: é o `executado_em` de qualquer execução nela."""
    return conexao.execute("SELECT now()").fetchone()[0]


def _sem_instantes(estatisticas: dict) -> dict:
    return {
        chave: valor
        for chave, valor in estatisticas.items()
        if chave not in {"gerado_em", "executado_em"}
    }


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

    estatisticas = calcular_estatisticas(conexao, origem="simulacao")

    assert _sem_instantes(estatisticas) == {
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
    assert datetime.fromisoformat(estatisticas["executado_em"]) == _agora(conexao)


def test_recebidos_e_a_soma_de_todos_os_estagios(conexao: psycopg.Connection) -> None:
    """Invariante do funil: todo alerta recebido termina em exatamente um estágio."""
    _inserir_rejeitado(conexao, "simulacao")
    _alerta_em(conexao, 600, status="descartado", motivo_descarte="fora_da_area")
    for norte in (0, 1, 50):
        _alerta_em(conexao, norte)
    _executar_pipeline(conexao)
    _alerta_em(conexao, 300)

    alertas = calcular_estatisticas(conexao, origem="simulacao")["alertas"]

    # Contagens independentes (`count(*)` direto nas tabelas), não a soma dos
    # próprios campos da resposta: assim o teste falha se um estágio deixar de
    # ser contado, em vez de comparar a função com ela mesma.
    def contar(tabela: str, filtro: str = "TRUE") -> int:
        return conexao.execute(
            f"SELECT count(*) FROM {tabela} WHERE origem = 'simulacao' AND {filtro}"
        ).fetchone()[0]

    assert alertas["recebidos"] == contar("alertas") + contar("alertas_rejeitados") == 6
    assert alertas["rejeitados_schema"] == contar("alertas_rejeitados")
    assert sum(alertas["descartados"].values()) == contar("alertas", "status = 'descartado'")
    assert alertas["aguardando_pipeline"] == contar("alertas", "status = 'bruto'")
    assert alertas["ruido_isolado"] == contar("alertas", "status = 'ruido_isolado'")
    assert alertas["agrupados"] == contar("alertas", "status = 'agrupado'")
    assert alertas["recebidos"] == (
        alertas["rejeitados_schema"]
        + sum(alertas["descartados"].values())
        + alertas["aguardando_pipeline"]
        + alertas["ruido_isolado"]
        + alertas["agrupados"]
    )


# --- parametros e executado_em: os da ÚLTIMA EXECUÇÃO (R14), não a configuração ---


def test_parametros_sao_os_da_execucao_com_valores_fora_da_config(
    conexao: psycopg.Connection,
) -> None:
    _executar_pipeline(conexao, parametros=_PARAMETROS_FORA_DA_CONFIG)

    estatisticas = calcular_estatisticas(conexao, origem="simulacao")

    assert estatisticas["parametros"] == _PARAMETROS_FORA_DA_CONFIG
    assert datetime.fromisoformat(estatisticas["executado_em"]) == _agora(conexao)


def test_origem_nunca_processada_tem_parametros_e_executado_em_nulos(
    conexao: psycopg.Connection,
) -> None:
    estatisticas = calcular_estatisticas(conexao, origem="simulacao")

    assert estatisticas["parametros"] is None
    assert estatisticas["executado_em"] is None


def test_segunda_execucao_atualiza_os_parametros(conexao: psycopg.Connection) -> None:
    _executar_pipeline(conexao, parametros=_PARAMETROS)
    _executar_pipeline(conexao, parametros=_PARAMETROS_FORA_DA_CONFIG)

    estatisticas = calcular_estatisticas(conexao, origem="simulacao")

    assert estatisticas["parametros"] == _PARAMETROS_FORA_DA_CONFIG


def test_execucao_de_uma_origem_nao_aparece_na_outra(conexao: psycopg.Connection) -> None:
    _executar_pipeline(conexao, origem="simulacao", parametros=_PARAMETROS_FORA_DA_CONFIG)

    real = calcular_estatisticas(conexao, origem="real")
    simulacao = calcular_estatisticas(conexao, origem="simulacao")

    assert (real["parametros"], real["executado_em"]) == (None, None)
    assert simulacao["parametros"] == _PARAMETROS_FORA_DA_CONFIG


# --- rótulo, formato e validação ---


@pytest.mark.parametrize(
    ("origem", "rotulo"),
    [("real", "Dados reais de campo"), ("simulacao", "SIMULAÇÃO — dados sintéticos")],
)
def test_rotulo_por_origem(conexao: psycopg.Connection, origem: str, rotulo: str) -> None:
    estatisticas = calcular_estatisticas(conexao, origem=origem)

    assert estatisticas["origem"] == origem
    assert estatisticas["rotulo"] == rotulo


def test_toda_origem_valida_tem_rotulo() -> None:
    assert set(ROTULOS_POR_ORIGEM) == set(ORIGENS_VALIDAS)


def test_banco_vazio_tem_fora_da_area_com_zero(conexao: psycopg.Connection) -> None:
    estatisticas = calcular_estatisticas(conexao, origem="real")

    assert _sem_instantes(estatisticas) == {
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
        "parametros": None,
    }
    assert list(estatisticas) == [
        "origem",
        "rotulo",
        "alertas",
        "barreiras",
        "parametros",
        "executado_em",
        "gerado_em",
    ]


def test_gerado_em_e_iso_8601_com_fuso(conexao: psycopg.Connection) -> None:
    estatisticas = calcular_estatisticas(conexao, origem="real")

    gerado_em = datetime.fromisoformat(estatisticas["gerado_em"])
    assert gerado_em.tzinfo is not None


def test_origem_invalida_levanta_value_error(conexao: psycopg.Connection) -> None:
    with pytest.raises(ValueError):
        calcular_estatisticas(conexao, origem="simulação")
