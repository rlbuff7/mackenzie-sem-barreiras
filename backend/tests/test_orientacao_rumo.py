"""Testes de `app/orientacao/rumo.py` (RF09, RNF05). Funções puras, nada é gravado (RNF04).

Os setores e limites usados aqui são os PROVISÓRIOS do `.env.example`.
"""

import math

import pytest

from app.orientacao.rumo import (
    ParametrosRumo,
    PontoTrilha,
    diferenca_angular,
    direcao_relativa,
    ponto_na_rota,
    rumo_ate_o_alvo,
    rumo_da_bussola,
    rumo_do_movimento,
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
    deslocamento_minimo_m=8.0,
    janela_trilha_s=15.0,
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


def _t(leste_m: float, norte_m: float, ha: float, prec: float = 3.0) -> PontoTrilha:
    lon, lat = _ponto(leste_m, norte_m)
    return PontoTrilha(lat=lat, lon=lon, precisao_m=prec, ha_segundos=ha)


def _rumo(trilha, leste=0.0, norte=0.0, prec=3.0):
    lon, lat = _ponto(leste, norte)
    return rumo_do_movimento(lat, lon, prec, trilha, P)


def test_caminhando_reto_para_o_norte_rumo_zero() -> None:
    trilha = [_t(0, -12, 10), _t(0, -6, 5), _t(0, -1.2, 1)]
    assert _rumo(trilha) == pytest.approx(0.0, abs=0.5)


def test_rumo_para_leste_sul_oeste() -> None:
    assert _rumo([_t(-12, 0, 10)]) == pytest.approx(90.0, abs=0.5)
    assert _rumo([_t(0, 12, 10)]) == pytest.approx(180.0, abs=0.5)
    assert _rumo([_t(12, 0, 10)]) == pytest.approx(270.0, abs=0.5)


def test_usa_o_ponto_mais_antigo_dentro_da_janela_acima_do_minimo() -> None:
    # 14 s atras (para sudoeste, 20 m) vale mais que o de 10 s (para o sul, 12 m).
    trilha = [_t(0, -12, 10), _t(-20, -20, 14)]
    assert _rumo(trilha) == pytest.approx(45.0, abs=0.5)


def test_ponto_da_trilha_fora_da_janela_e_ignorado() -> None:
    trilha = [_t(-30, 0, 16), _t(0, -12, 10)]  # o de 16 s (leste) fica de fora
    assert _rumo(trilha) == pytest.approx(0.0, abs=0.5)
    assert _rumo([_t(-30, 0, 16)]) is None


def test_ponto_na_borda_da_janela_vale() -> None:
    assert _rumo([_t(0, -12, 15)]) == pytest.approx(0.0, abs=0.5)


def test_trilha_vazia_e_sem_rumo() -> None:
    assert _rumo([]) is None


def test_deslocamento_menor_que_o_minimo_e_sem_rumo() -> None:
    assert _rumo([_t(0, -7.9, 10, prec=0.0)], prec=0.0) is None
    assert _rumo([_t(0, -8.1, 10, prec=0.0)], prec=0.0) == pytest.approx(0.0, abs=0.5)


def test_deslocamento_menor_que_a_soma_das_precisoes_e_sem_rumo() -> None:
    # 10 m de deslocamento, precisoes 6 + 5 = 11 m: dentro do ruido.
    assert _rumo([_t(0, -10, 10, prec=5.0)], prec=6.0) is None
    assert _rumo([_t(0, -10, 10, prec=4.0)], prec=5.0) == pytest.approx(0.0, abs=0.5)


def test_pessoa_parada_pela_velocidade_media_e_sem_rumo() -> None:
    # 9 m em 14 s = 0,64 m/s anda; com limite maior que isso, vira parado.
    lento = ParametrosRumo(**{**P.__dict__, "velocidade_parado_ms": 1.0})
    lon, lat = _ponto(0, 0)
    assert rumo_do_movimento(lat, lon, 3.0, [_t(0, -9, 14)], lento) is None
    assert rumo_do_movimento(lat, lon, 3.0, [_t(0, -9, 14)], P) is not None


def test_giro_359_para_1_nao_quebra_a_media_de_rumos() -> None:
    # Andando quase ao norte (rumo 359) com a rota rumo 1: diferenca +2, frente.
    rota = [_ponto(0, 0), _ponto(2, 100)]
    trilha = [_t(0.2, -12, 10)]  # rumo ~ 359
    d = _dir(rota, trilha)
    assert _rumo(trilha) == pytest.approx(359.0, abs=0.5)
    assert d == "frente"


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


def _dir(rota, trilha, bussola=None, osc=None, com_fonte=False):
    r = direcao_relativa(
        rota,
        lat=_LAT0,
        lon=_LON0,
        precisao_m=3.0,
        trilha=trilha,
        bussola_graus=bussola,
        bussola_oscilacao_graus=osc,
        distancia_percorrida_m=0.0,
        parametros=P,
    )
    if com_fonte:
        return r
    return None if r is None else r[0]


def test_direcao_relativa_frente_direita_esquerda_atras() -> None:
    # Rota reta para leste; usuário na origem. Alvo a 8 m ao leste (rumo 90).
    rota = [_ponto(0, 0), _ponto(100, 0)]
    assert _dir(rota, [_t(-12, 0, 10)]) == "frente"  # andando para leste
    assert _dir(rota, [_t(0, -12, 10)]) == "direita"  # andando para norte
    assert _dir(rota, [_t(0, 12, 10)]) == "esquerda"  # andando para sul
    assert _dir(rota, [_t(12, 0, 10)]) == "atras"  # andando para oeste


def test_caminhando_ao_norte_em_rota_ao_norte_e_frente() -> None:
    rota = [_ponto(0, 0), _ponto(0, 100)]
    assert _dir(rota, [_t(0, -12, 10)]) == "frente"


def _usuario(trilha, bussola=None, osc=None, prec=3.0):
    return rumo_do_usuario(_LAT0, _LON0, prec, trilha, bussola, osc, P)


def test_bussola_normaliza_360_e_rejeita_invalido_ou_instavel() -> None:
    assert rumo_da_bussola(360.0, None, P) == pytest.approx(0.0)
    assert rumo_da_bussola(312.0, 30.0, P) == pytest.approx(312.0)
    assert rumo_da_bussola(90.0, 30.1, P) is None
    assert rumo_da_bussola(90.0, math.nan, P) is None
    assert rumo_da_bussola(90.0, -1.0, P) is None
    for ruim in (None, math.nan, math.inf, -1.0, 361.0):
        assert rumo_da_bussola(ruim, 0.0, P) is None


def test_parado_com_bussola_estavel_usa_a_bussola() -> None:
    parada = [_t(0, -2, 10)]  # 2 m em 10 s: parado
    assert _usuario(parada, bussola=312.0, osc=5.0) == (pytest.approx(312.0), "bussola")


def test_parado_com_bussola_instavel_ou_ausente_e_sem_rumo() -> None:
    parada = [_t(0, -2, 10)]
    assert _usuario(parada, bussola=312.0, osc=45.0) is None
    assert _usuario(parada, bussola=None) is None


def test_andando_com_bussola_discordante_vale_o_movimento() -> None:
    andando = [_t(0, -12, 10)]  # rumo 0
    rumo, fonte = _usuario(andando, bussola=180.0, osc=2.0)
    assert fonte == "movimento" and rumo == pytest.approx(0.0, abs=0.5)


def test_trilha_vazia_ou_fora_da_janela_nao_vira_bussola() -> None:
    # Sem trilha não se sabe se anda: silêncio, não bússola.
    assert _usuario([], bussola=90.0, osc=1.0) is None
    assert _usuario([_t(0, -1, 40)], bussola=90.0, osc=1.0) is None


def test_gps_ruidoso_andando_nao_vira_bussola() -> None:
    # 10 m de deslocamento, precisoes 6 + 5: nao confiavel, e NAO parado.
    assert _usuario([_t(0, -10, 10, prec=5.0)], bussola=90.0, osc=1.0, prec=6.0) is None


def test_direcao_parado_pela_bussola_devolve_a_fonte() -> None:
    rota = [_ponto(0, 0), _ponto(100, 0)]  # alvo ao leste (90)
    parada = [_t(-2, 0, 10)]
    assert _dir(rota, parada, bussola=90.0, osc=3.0, com_fonte=True) == ("frente", "bussola")
    assert _dir(rota, parada, bussola=0.0, osc=3.0) == "direita"
    assert _dir(rota, parada, bussola=90.0, osc=80.0) is None
    assert _dir(rota, [_t(-12, 0, 10)], com_fonte=True) == ("frente", "movimento")
    # andando para o norte, bussola dizendo leste: vale o movimento (direita)
    assert _dir(rota, [_t(0, -12, 10)], bussola=90.0, osc=1.0) == "direita"


def test_sem_rumo_nao_da_direcao() -> None:
    rota = [_ponto(0, 0), _ponto(100, 0)]
    assert _dir(rota, []) is None
    assert _dir(rota, [_t(-3, 0, 10)]) is None
