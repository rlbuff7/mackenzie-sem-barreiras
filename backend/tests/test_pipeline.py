"""Testes do estágio 4 (promoção) e da orquestração: `app/validacao/pipeline.py`."""

import psycopg
import pytest

from app.config import obter_configuracoes
from app.validacao.pipeline import (
    CHAVE_LOCK_PIPELINE,
    ResumoExecucao,
    decidir_status_barreira,
    executar_pipeline,
)
from tests.auxiliares import (
    LATITUDE_CAMPUS,
    LONGITUDE_CAMPUS,
    inserir_alerta,
    nova_sessao_hash,
    ponto_deslocado,
)

# G8: valores de teste explícitos, sem passar por Configuracoes.
_EPS_METROS = 8
_MIN_PONTOS = 2
_MIN_CONFIRMACOES = 3
_SRID_CALCULO = 31983
_SRID_ARMAZENAMENTO = 4326

_PARAMETROS = {
    "eps_metros": _EPS_METROS,
    "min_pontos": _MIN_PONTOS,
    "min_confirmacoes": _MIN_CONFIRMACOES,
}


def _executar(conexao: psycopg.Connection, origem: str = "simulacao") -> ResumoExecucao:
    return executar_pipeline(
        conexao,
        origem=origem,
        eps_metros=_EPS_METROS,
        min_pontos=_MIN_PONTOS,
        min_confirmacoes=_MIN_CONFIRMACOES,
        srid_calculo=_SRID_CALCULO,
        srid_armazenamento=_SRID_ARMAZENAMENTO,
    )


def _alerta_em(
    conexao: psycopg.Connection, norte_metros: float, leste_metros: float = 0, **campos: object
) -> int:
    """Insere um alerta deslocado do centro do campus (dentro da área de estudo)."""
    latitude, longitude = ponto_deslocado(
        conexao, LATITUDE_CAMPUS, LONGITUDE_CAMPUS, norte_metros, leste_metros
    )
    return inserir_alerta(conexao, latitude=latitude, longitude=longitude, **campos)


def _estado_alertas(conexao: psycopg.Connection, ids: list[int]) -> list[tuple]:
    return conexao.execute(
        "SELECT id, status, motivo_descarte, barreira_id FROM alertas WHERE id = ANY(%s) "
        "ORDER BY id",
        (ids,),
    ).fetchall()


def _barreiras(conexao: psycopg.Connection, origem: str = "simulacao") -> list[tuple]:
    return conexao.execute(
        """
        SELECT b.id, t.codigo, b.status, b.confirmacoes
        FROM barreiras b JOIN tipos_barreira t ON t.id = b.tipo_id
        WHERE b.origem = %s
        ORDER BY b.id
        """,
        (origem,),
    ).fetchall()


# --- decidir_status_barreira (estágio 4, função pura) ---


@pytest.mark.parametrize(
    ("sessoes_distintas", "min_confirmacoes", "esperado"),
    [(2, 3, "pendente"), (3, 3, "confirmada"), (4, 3, "confirmada"), (1, 1, "confirmada")],
    ids=["abaixo_do_minimo", "no_minimo", "acima_do_minimo", "minimo_1"],
)
def test_decidir_status_barreira_nos_limites(
    sessoes_distintas: int, min_confirmacoes: int, esperado: str
) -> None:
    assert decidir_status_barreira(sessoes_distintas, min_confirmacoes) == esperado


@pytest.mark.parametrize("min_confirmacoes", [0, -1])
def test_decidir_status_barreira_min_confirmacoes_menor_que_1_e_erro(
    min_confirmacoes: int,
) -> None:
    with pytest.raises(ValueError):
        decidir_status_barreira(3, min_confirmacoes)


# --- executar_pipeline ---


def test_tres_sessoes_distintas_proximas_viram_barreira_confirmada(
    conexao: psycopg.Connection,
) -> None:
    alertas = [_alerta_em(conexao, 0), _alerta_em(conexao, 1.5), _alerta_em(conexao, 0, 1.5)]

    resumo = _executar(conexao)

    assert resumo == ResumoExecucao(
        origem="simulacao",
        alertas_processados=3,
        agrupados=3,
        ruido_isolado=0,
        barreiras_pendentes=0,
        barreiras_confirmadas=1,
        parametros=_PARAMETROS,
    )
    [(barreira_id, tipo, status, confirmacoes)] = _barreiras(conexao)
    assert (tipo, status, confirmacoes) == ("degrau", "confirmada", 3)
    assert _estado_alertas(conexao, alertas) == [
        (alerta, "agrupado", None, barreira_id) for alerta in alertas
    ]


def test_cinco_alertas_da_mesma_sessao_ficam_pendentes(conexao: psycopg.Connection) -> None:
    """Anti-Sybil (CLAUDE.md §6): uma pessoa reportando cinco vezes no mesmo lugar
    é UMA confirmação, não cinco."""
    sessao = nova_sessao_hash()
    alertas = [_alerta_em(conexao, norte, sessao_hash=sessao) for norte in (0, 0.5, 1, 1.5, 2)]

    resumo = _executar(conexao)

    assert (resumo.agrupados, resumo.barreiras_pendentes, resumo.barreiras_confirmadas) == (
        5,
        1,
        0,
    )
    [(barreira_id, _, status, confirmacoes)] = _barreiras(conexao)
    assert (status, confirmacoes) == ("pendente", 1)
    assert {estado[3] for estado in _estado_alertas(conexao, alertas)} == {barreira_id}


def test_ponto_isolado_vira_ruido_isolado(conexao: psycopg.Connection) -> None:
    alerta = _alerta_em(conexao, 0)

    resumo = _executar(conexao)

    assert (resumo.alertas_processados, resumo.ruido_isolado, resumo.agrupados) == (1, 1, 0)
    assert _estado_alertas(conexao, [alerta]) == [(alerta, "ruido_isolado", None, None)]
    assert _barreiras(conexao) == []


def test_ruido_que_ganha_vizinho_vira_agrupado_na_execucao_seguinte(
    conexao: psycopg.Connection,
) -> None:
    """T4 (resolvido por D6): ruído não é final; quando chega um vizinho, os dois
    formam cluster na execução seguinte."""
    antigo = _alerta_em(conexao, 0)
    _executar(conexao)
    novo = _alerta_em(conexao, 4)

    resumo = _executar(conexao)

    assert (resumo.agrupados, resumo.ruido_isolado, resumo.barreiras_pendentes) == (2, 0, 1)
    [(barreira_id, _, status, confirmacoes)] = _barreiras(conexao)
    assert (status, confirmacoes) == ("pendente", 2)
    assert _estado_alertas(conexao, [antigo, novo]) == [
        (antigo, "agrupado", None, barreira_id),
        (novo, "agrupado", None, barreira_id),
    ]


def test_alerta_novo_perto_de_barreira_entra_no_cluster_dela(
    conexao: psycopg.Connection,
) -> None:
    """D6: a reconstrução completa junta o alerta novo à barreira que já existia
    (continua uma barreira só, agora com uma confirmação a mais)."""
    alertas = [_alerta_em(conexao, 0), _alerta_em(conexao, 1), _alerta_em(conexao, 2)]
    _executar(conexao)
    alertas.append(_alerta_em(conexao, 3))

    _executar(conexao)

    [(barreira_id, _, status, confirmacoes)] = _barreiras(conexao)
    assert (status, confirmacoes) == ("confirmada", 4)
    assert {estado[3] for estado in _estado_alertas(conexao, alertas)} == {barreira_id}


def test_executar_duas_vezes_seguidas_da_o_mesmo_resultado(conexao: psycopg.Connection) -> None:
    """Idempotência (D6): a segunda execução reconstrói a mesma coisa, sem
    duplicar barreiras. Os ids das barreiras mudam (custo aceito em D6); o
    resto não."""
    for norte in (0, 1, 2):
        _alerta_em(conexao, norte)
    sessao = nova_sessao_hash()
    for norte in (100, 101):
        _alerta_em(conexao, norte, sessao_hash=sessao)
    _alerta_em(conexao, 0, tipo="obstaculo")
    _alerta_em(conexao, 0.5, tipo="obstaculo")
    _alerta_em(conexao, 200)
    _alerta_em(conexao, 0, status="descartado", motivo_descarte="fora_da_area")

    def fotografia() -> tuple:
        alertas = conexao.execute(
            "SELECT id, status, barreira_id IS NULL FROM alertas ORDER BY id"
        ).fetchall()
        barreiras = sorted((tipo, status, conf) for _, tipo, status, conf in _barreiras(conexao))
        return alertas, barreiras

    primeiro = _executar(conexao)
    fotografia_1 = fotografia()
    segundo = _executar(conexao)
    fotografia_2 = fotografia()

    assert primeiro == segundo
    assert fotografia_1 == fotografia_2
    assert primeiro.alertas_processados == 8
    assert (primeiro.barreiras_confirmadas, primeiro.barreiras_pendentes) == (1, 2)
    assert len(fotografia_2[1]) == 3


def test_descartado_fica_intacto(conexao: psycopg.Connection) -> None:
    """`descartado` é final: nem o reset nem o agrupamento tocam nele, mesmo com
    um cluster a 1 m (e a sessão dele não conta como confirmação)."""
    for norte in (0, 1, 2):
        _alerta_em(conexao, norte)
    descartado = _alerta_em(conexao, 1, status="descartado", motivo_descarte="fora_da_area")

    resumo = _executar(conexao)

    assert resumo.alertas_processados == 3
    assert _estado_alertas(conexao, [descartado]) == [
        (descartado, "descartado", "fora_da_area", None)
    ]
    [(_, _, _, confirmacoes)] = _barreiras(conexao)
    assert confirmacoes == 3


def test_origens_nao_se_misturam(conexao: psycopg.Connection) -> None:
    """G10: a execução de `real` não enxerga nem apaga o que é `simulacao`, e um
    alerta real ao lado de um cluster sintético continua sozinho."""
    alertas_simulacao = [_alerta_em(conexao, norte, origem="simulacao") for norte in (0, 1, 2)]
    alerta_real = _alerta_em(conexao, 0.5, origem="real")
    _executar(conexao, origem="simulacao")

    resumo_real = _executar(conexao, origem="real")

    assert resumo_real == ResumoExecucao(
        origem="real",
        alertas_processados=1,
        agrupados=0,
        ruido_isolado=1,
        barreiras_pendentes=0,
        barreiras_confirmadas=0,
        parametros=_PARAMETROS,
    )
    assert _barreiras(conexao, origem="real") == []
    [(barreira_simulacao, _, status, _)] = _barreiras(conexao, origem="simulacao")
    assert status == "confirmada"
    assert {estado[3] for estado in _estado_alertas(conexao, alertas_simulacao)} == {
        barreira_simulacao
    }
    assert _estado_alertas(conexao, [alerta_real]) == [(alerta_real, "ruido_isolado", None, None)]


def test_centroide_fica_a_menos_de_1_metro_da_media_dos_pontos(
    conexao: psycopg.Connection,
) -> None:
    alertas = [_alerta_em(conexao, 0), _alerta_em(conexao, 6), _alerta_em(conexao, 0, 6)]

    _executar(conexao)

    distancia_metros = conexao.execute(
        """
        SELECT ST_Distance(
            b.geom::geography,
            ST_SetSRID(ST_MakePoint(media.longitude, media.latitude), 4326)::geography
        )
        FROM barreiras b,
             (SELECT avg(ST_X(geom)) AS longitude, avg(ST_Y(geom)) AS latitude
              FROM alertas WHERE id = ANY(%s)) AS media
        WHERE b.origem = 'simulacao'
        """,
        (alertas,),
    ).fetchone()[0]
    assert distancia_metros < 1


def test_sem_alertas_nada_acontece(conexao: psycopg.Connection) -> None:
    resumo = _executar(conexao)

    assert resumo == ResumoExecucao(
        origem="simulacao",
        alertas_processados=0,
        agrupados=0,
        ruido_isolado=0,
        barreiras_pendentes=0,
        barreiras_confirmadas=0,
        parametros=_PARAMETROS,
    )


def test_origem_invalida_levanta_value_error(conexao: psycopg.Connection) -> None:
    with pytest.raises(ValueError):
        _executar(conexao, origem="simulação")


def test_nao_faz_commit_e_segura_o_lock_ate_o_fim_da_transacao(
    conexao: psycopg.Connection,
) -> None:
    """D6: enquanto a transação de quem chamou não termina, outra conexão não
    consegue o advisory lock (uma segunda execução simultânea esperaria) e não
    enxerga a barreira criada (o pipeline não faz commit; `obter_conexao` faz)."""
    for norte in (0, 1, 2):
        _alerta_em(conexao, norte)
    _executar(conexao)

    with psycopg.connect(obter_configuracoes().conninfo) as outra_conexao:
        conseguiu_lock = outra_conexao.execute(
            "SELECT pg_try_advisory_xact_lock(%s)", (CHAVE_LOCK_PIPELINE,)
        ).fetchone()[0]
        barreiras_visiveis = outra_conexao.execute(
            "SELECT count(*) FROM barreiras WHERE origem = 'simulacao'"
        ).fetchone()[0]
        outra_conexao.rollback()

    assert conseguiu_lock is False
    assert barreiras_visiveis == 0
