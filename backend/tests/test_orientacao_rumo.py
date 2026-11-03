"""Testes de `app/orientacao/rumo.py` (RF09, RNF05). Funções puras, nada é gravado (RNF04).

Os setores e limites usados aqui são os PROVISÓRIOS do `.env.example`.
"""

import math

import pytest

from app.orientacao.rumo import (
    ParametrosRumo,
    diferenca_angular,
    direcao_relativa,
    esta_parado,
    ponto_na_rota,
    rumo_ate_o_alvo,
    rumo_do_usuario,
    setor_da_diferenca,
)

_LAT0 = -23.5470
_LON0 = -46.6520
_M_LAT = 110_600.0
_M_LON = 111_320.0 * math.cos(math.radians(_LAT0))

P = ParametrosRumo(
    alvo_a_frente_m=8.0,
    velocidade_parado_ms=0.3,
    oscilacao_maxima_graus=30.0,
    setor_frente_graus=30.0,
    setor_atras_graus=150.0,
)


def _ponto(leste_m: float, norte_m: float) -> list[float]:
    return [_LON0 + leste_m / _M_LON, _LAT0 + norte_m / _M_LAT]


def test_diferenca_angular_trata_o_giro_de_359_para_1() -> None:
    assert diferenca_angular(alvo=1.0, usuario=359.0) == pytest.approx(2.0)
    assert diferenca_angular(alvo=359.0, usuario=1.0) == pytest.approx(-2.0)
    assert diferenca_angular(alvo=0.0, usuario=360.0) == pytest.approx(0.0)


def test_diferenca_angular_fica_entre_menos_180_e_180() -> None:
    for usuario in range(0, 360, 15):
        for alvo in range(0, 360, 15):
            d = diferenca_angular(float(alvo), float(usuario))
            assert -180.0 < d <= 180.0


def test_diferenca_de_180_graus_e_atras_sem_lado() -> None:
    assert abs(diferenca_angular(180.0, 0.0)) == pytest.approx(180.0)


@pytest.mark.parametrize(
    ("diferenca", "esperado"),
    [
        (0.0, "frente"),
        (30.0, "frente"),
        (-30.0, "frente"),
        (30.1, "direita"),
        (90.0, "direita"),
        (150.0, "direita"),
        (-90.0, "esquerda"),
        (-150.0, "esquerda"),
        (150.1, "atras"),
        (-150.1, "atras"),
        (180.0, "atras"),
    ],
)
def test_setores(diferenca: float, esperado: str) -> None:
    assert setor_da_diferenca(diferenca, P) == esperado


def test_rumo_do_usuario_normaliza_360_para_0() -> None:
    assert rumo_do_usuario(360.0, None, P) == pytest.approx(0.0)
    assert rumo_do_usuario(312.0, 5.0, P) == pytest.approx(312.0)


@pytest.mark.parametrize("rumo", [None, math.nan, math.inf, -1.0, 361.0])
def test_rumo_ausente_ou_invalido_e_sem_rumo(rumo) -> None:
    assert rumo_do_usuario(rumo, 0.0, P) is None


def test_bussola_instavel_nao_vale() -> None:
    assert rumo_do_usuario(90.0, 30.1, P) is None
    assert rumo_do_usuario(90.0, 30.0, P) == pytest.approx(90.0)


def test_oscilacao_invalida_nao_vale() -> None:
    assert rumo_do_usuario(90.0, math.nan, P) is None
    assert rumo_do_usuario(90.0, -1.0, P) is None


def test_oscilacao_ausente_e_aceita() -> None:
    assert rumo_do_usuario(90.0, None, P) == pytest.approx(90.0)


@pytest.mark.parametrize(
    ("velocidade", "parado"),
    [(None, True), (0.0, True), (0.29, True), (0.3, False), (1.2, False), (math.nan, True)],
)
def test_parado(velocidade, parado: bool) -> None:
    assert esta_parado(velocidade, P) is parado


def test_ponto_na_rota_anda_ao_longo_da_linha_em_curva() -> None:
    rota = [_ponto(0, 0), _ponto(60, 0), _ponto(60, 40)]
    lon, lat = ponto_na_rota(rota, 70.0)  # 60 m leste + 10 m norte
    assert (lon - _LON0) * _M_LON == pytest.approx(60.0, abs=0.1)
    assert (lat - _LAT0) * _M_LAT == pytest.approx(10.0, abs=0.1)


def test_ponto_na_rota_prende_no_fim() -> None:
    rota = [_ponto(0, 0), _ponto(60, 0)]
    lon, lat = ponto_na_rota(rota, 500.0)
    assert (lon - _LON0) * _M_LON == pytest.approx(60.0, abs=0.1)


@pytest.mark.parametrize(
    ("leste", "norte", "esperado"),
    [(10, 0, 90.0), (0, 10, 0.0), (-10, 0, 270.0), (0, -10, 180.0), (10, 10, 45.0)],
)
def test_rumo_ate_o_alvo_em_graus_de_0_a_360(leste, norte, esperado) -> None:
    lon, lat = _ponto(leste, norte)
    assert rumo_ate_o_alvo(_LAT0, _LON0, lat, lon) == pytest.approx(esperado, abs=0.5)


def test_direcao_relativa_frente_direita_esquerda_atras() -> None:
    # Rota reta para leste; usuário na origem. Alvo a 8 m ao leste (rumo 90).
    rota = [_ponto(0, 0), _ponto(100, 0)]
    kw = {"lat": _LAT0, "lon": _LON0, "distancia_percorrida_m": 0.0, "velocidade_ms": 1.0}
    assert (
        direcao_relativa(rota, rumo_graus=90.0, oscilacao_graus=3.0, parametros=P, **kw) == "frente"
    )
    assert (
        direcao_relativa(rota, rumo_graus=0.0, oscilacao_graus=3.0, parametros=P, **kw) == "direita"
    )
    assert (
        direcao_relativa(rota, rumo_graus=180.0, oscilacao_graus=3.0, parametros=P, **kw)
        == "esquerda"
    )
    assert (
        direcao_relativa(rota, rumo_graus=270.0, oscilacao_graus=3.0, parametros=P, **kw) == "atras"
    )


def test_direcao_relativa_giro_0_360() -> None:
    # Rota para o norte (rumo 0); usuário apontando 355: alvo 5 graus à direita = frente.
    rota = [_ponto(0, 0), _ponto(0, 100)]
    kw = {"lat": _LAT0, "lon": _LON0, "distancia_percorrida_m": 0.0, "velocidade_ms": 1.0}
    assert (
        direcao_relativa(rota, rumo_graus=355.0, oscilacao_graus=None, parametros=P, **kw)
        == "frente"
    )
    assert (
        direcao_relativa(rota, rumo_graus=5.0, oscilacao_graus=None, parametros=P, **kw) == "frente"
    )
    assert (
        direcao_relativa(rota, rumo_graus=300.0, oscilacao_graus=None, parametros=P, **kw)
        == "direita"
    )


def test_parado_nao_da_direcao() -> None:
    rota = [_ponto(0, 0), _ponto(100, 0)]
    for v in (None, 0.0, 0.1):
        assert (
            direcao_relativa(
                rota,
                lat=_LAT0,
                lon=_LON0,
                distancia_percorrida_m=0.0,
                velocidade_ms=v,
                rumo_graus=90.0,
                oscilacao_graus=1.0,
                parametros=P,
            )
            is None
        )


def test_bussola_ausente_ou_instavel_nao_da_direcao() -> None:
    rota = [_ponto(0, 0), _ponto(100, 0)]
    for rumo, osc in ((None, None), (90.0, 45.0)):
        assert (
            direcao_relativa(
                rota,
                lat=_LAT0,
                lon=_LON0,
                distancia_percorrida_m=0.0,
                velocidade_ms=1.0,
                rumo_graus=rumo,
                oscilacao_graus=osc,
                parametros=P,
            )
            is None
        )
