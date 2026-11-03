"""Testes de `app/orientacao/posicao.py` (RF08, RF12, RNF05).

Funções puras: nenhuma toca banco nem grava posição (RNF04). A rota de teste é em
metros locais convertidos para lat/lon por `_ponto`, para os números do teste serem
legíveis. A trajetória com ruído (`test_trajeto_simulado_...`) é SINTÉTICA, rotulada
assim: o trajeto real do iPhone de 26/10 está só no servidor de produção.
"""

import math
import random

import pytest

from app.orientacao.posicao import (
    ParametrosOrientacao,
    Posicao,
    avaliar_posicao,
    projetar_na_rota,
)

_LAT0 = -23.5470
_LON0 = -46.6520
_M_LAT = 110_600.0
_M_LON = 111_320.0 * math.cos(math.radians(_LAT0))

PARAMETROS = ParametrosOrientacao(
    precisao_minima_m=15.0, distancia_fora_da_rota_m=15.0, raio_chegada_m=10.0
)


def _ponto(leste_m: float, norte_m: float) -> list[float]:
    """[lon, lat] a `leste_m`/`norte_m` metros da origem de teste."""
    return [_LON0 + leste_m / _M_LON, _LAT0 + norte_m / _M_LAT]


def _pos(leste_m: float, norte_m: float, precisao_m: float = 5.0) -> Posicao:
    lon, lat = _ponto(leste_m, norte_m)
    return Posicao(lat=lat, lon=lon, precisao_m=precisao_m)


# Rota reta de 100 m para leste.
RETA = [_ponto(0, 0), _ponto(100, 0)]
# Rota em L: 60 m para leste, depois 40 m para norte (total 100 m).
CURVA = [_ponto(0, 0), _ponto(60, 0), _ponto(60, 40)]


def test_projecao_no_meio_da_reta() -> None:
    p = projetar_na_rota(_pos(30, 4), RETA)

    assert p.distancia_perpendicular_m == pytest.approx(4.0, abs=0.05)
    assert p.distancia_percorrida_m == pytest.approx(30.0, abs=0.05)
    assert p.distancia_restante_m == pytest.approx(70.0, abs=0.05)
    assert p.indice_trecho == 0
    assert p.lon == pytest.approx(_ponto(30, 0)[0], abs=1e-7)
    assert p.lat == pytest.approx(_ponto(30, 0)[1], abs=1e-7)


def test_rota_com_curva_escolhe_o_trecho_mais_proximo() -> None:
    no_segundo_trecho = projetar_na_rota(_pos(63, 25), CURVA)

    assert no_segundo_trecho.indice_trecho == 1
    assert no_segundo_trecho.distancia_perpendicular_m == pytest.approx(3.0, abs=0.05)
    # 60 m do primeiro trecho + 25 m do segundo.
    assert no_segundo_trecho.distancia_percorrida_m == pytest.approx(85.0, abs=0.05)

    no_primeiro = projetar_na_rota(_pos(40, -2), CURVA)
    assert no_primeiro.indice_trecho == 0
    assert no_primeiro.distancia_percorrida_m == pytest.approx(40.0, abs=0.05)


def test_na_quina_da_curva_a_distancia_percorrida_e_a_do_vertice() -> None:
    p = projetar_na_rota(_pos(66, -4), CURVA)

    # Ponto "além" da quina: o mais próximo da rota é o próprio vértice.
    assert p.distancia_percorrida_m == pytest.approx(60.0, abs=0.05)
    assert p.distancia_perpendicular_m == pytest.approx(math.hypot(6, 4), abs=0.05)


def test_posicao_antes_do_inicio_fica_presa_ao_primeiro_vertice() -> None:
    p = projetar_na_rota(_pos(-12, 0), RETA)

    assert p.distancia_percorrida_m == pytest.approx(0.0, abs=0.05)
    assert p.distancia_perpendicular_m == pytest.approx(12.0, abs=0.05)
    assert p.indice_trecho == 0


def test_posicao_depois_do_fim_fica_presa_ao_ultimo_vertice() -> None:
    p = projetar_na_rota(_pos(108, 0), RETA)

    assert p.distancia_percorrida_m == pytest.approx(100.0, abs=0.05)
    assert p.distancia_restante_m == pytest.approx(0.0, abs=0.05)


def test_rota_com_vertice_repetido_nao_quebra() -> None:
    rota = [_ponto(0, 0), _ponto(0, 0), _ponto(50, 0)]

    p = projetar_na_rota(_pos(20, 1), rota)

    assert p.distancia_percorrida_m == pytest.approx(20.0, abs=0.05)


@pytest.mark.parametrize("rota", [[], [_ponto(0, 0)], [_ponto(0, 0), _ponto(0, 0)]])
def test_rota_sem_extensao_e_recusada(rota: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        projetar_na_rota(_pos(0, 0), rota)


def test_na_rota_com_boa_precisao_tem_confianca_alta() -> None:
    a = avaliar_posicao(_pos(30, 2, precisao_m=5), RETA, PARAMETROS)

    assert a.estado == "na_rota"
    assert a.confianca == "alta"
    assert a.projecao is not None


def test_precisao_pior_que_o_minimo_nao_da_nenhuma_orientacao() -> None:
    a = avaliar_posicao(_pos(30, 2, precisao_m=15.1), RETA, PARAMETROS)

    assert a.estado == "precisao_insuficiente"
    assert a.confianca == "baixa"
    # Silêncio: nem projeção nem distância restante saem.
    assert a.projecao is None


def test_precisao_exatamente_no_limite_ainda_vale() -> None:
    a = avaliar_posicao(_pos(30, 2, precisao_m=15.0), RETA, PARAMETROS)

    assert a.estado == "na_rota"


@pytest.mark.parametrize("precisao", [0.0, -1.0, math.nan, math.inf])
def test_precisao_sem_sentido_e_tratada_como_insuficiente(precisao: float) -> None:
    a = avaliar_posicao(_pos(30, 2, precisao_m=precisao), RETA, PARAMETROS)

    assert a.estado == "precisao_insuficiente"
    assert a.projecao is None


def test_fora_da_rota_com_margem_pela_precisao() -> None:
    # Limite = 15 m + precisão de 5 m = 20 m.
    dentro = avaliar_posicao(_pos(30, 19.5, precisao_m=5), RETA, PARAMETROS)
    fora = avaliar_posicao(_pos(30, 21, precisao_m=5), RETA, PARAMETROS)

    assert dentro.estado == "na_rota"
    assert fora.estado == "fora_da_rota"
    assert fora.confianca == "baixa"
    assert fora.projecao is not None  # a distância à rota pode ser dita


def test_precisao_pior_alarga_a_margem_de_fora_da_rota() -> None:
    # A 25 m: fora com precisão 5 (limite 20), dentro com precisão 12 (limite 27).
    assert avaliar_posicao(_pos(30, 25, precisao_m=5), RETA, PARAMETROS).estado == "fora_da_rota"
    assert avaliar_posicao(_pos(30, 25, precisao_m=12), RETA, PARAMETROS).estado == "na_rota"


def test_chegada_dentro_do_raio_do_fim_da_rota() -> None:
    a = avaliar_posicao(_pos(92, 1, precisao_m=5), RETA, PARAMETROS)

    assert a.estado == "chegou"
    assert a.projecao is not None
    assert a.projecao.distancia_restante_m == pytest.approx(8.0, abs=0.05)


def test_fora_do_raio_de_chegada_segue_na_rota() -> None:
    assert avaliar_posicao(_pos(88, 0), RETA, PARAMETROS).estado == "na_rota"


def test_longe_da_rota_nao_anuncia_chegada_mesmo_com_restante_pequeno() -> None:
    # Projeta perto do fim, mas está 30 m ao lado: fora da rota vem antes de chegou.
    a = avaliar_posicao(_pos(97, 30, precisao_m=5), RETA, PARAMETROS)

    assert a.estado == "fora_da_rota"


def test_chegada_em_rota_com_curva_usa_distancia_ao_longo_da_rota() -> None:
    # Perto do fim em linha reta do ponto de partida não conta: o restante é pela rota.
    a = avaliar_posicao(_pos(60, 35, precisao_m=5), CURVA, PARAMETROS)

    assert a.estado == "chegou"
    assert a.projecao is not None
    assert a.projecao.distancia_restante_m == pytest.approx(5.0, abs=0.05)


def test_confianca_media_quando_precisao_passa_da_metade_do_limite() -> None:
    a = avaliar_posicao(_pos(30, 2, precisao_m=14.25), RETA, PARAMETROS)

    # Precisão de 14,25 m (o valor fixo do iPhone na medição) nunca dá "alta".
    assert a.estado == "na_rota"
    assert a.confianca == "media"


def test_confianca_baixa_na_faixa_de_margem_do_fora_da_rota() -> None:
    # 18 m de desvio, precisão 5: ainda na rota (limite 20), mas além dos 15 m.
    a = avaliar_posicao(_pos(30, 18, precisao_m=5), RETA, PARAMETROS)

    assert a.estado == "na_rota"
    assert a.confianca == "baixa"


def test_confianca_nao_e_alta_quando_o_desvio_passa_da_precisao_informada() -> None:
    # A precisão diz 3 m, mas a posição está 10 m fora da linha: o celular "mente".
    a = avaliar_posicao(_pos(30, 10, precisao_m=3), RETA, PARAMETROS)

    assert a.estado == "na_rota"
    assert a.confianca == "media"


def test_trajeto_simulado_sintetico_percorre_a_rota_sem_falso_fora_da_rota() -> None:
    """SINTÉTICO. Rota em L ~ entrada do Prédio 31 -> Biblioteca (coordenadas reais do
    seed, 4 -> 6) com um vértice de curva inventado; caminhante simulado com ruído
    gaussiano de 3 m e precisão informada de 8 m. Só mostra que a regra é coerente: a
    validação com o trajeto REAL do iPhone (26/10) fica para depois."""
    rota = [
        [-46.6514681, -23.5474426],
        [-46.6514681, -23.5466000],  # vértice inventado
        [-46.6520217, -23.5460134],
    ]
    rng = random.Random(42)
    parametros = PARAMETROS
    estados = []
    anterior = -1.0
    for i in range(41):
        # Anda sobre a própria rota, de 0 a 100% do comprimento.
        total = projetar_na_rota(Posicao(lat=rota[-1][1], lon=rota[-1][0], precisao_m=5), rota)
        alvo = total.distancia_percorrida_m * i / 40
        ponto = _ponto_na_rota(rota, alvo)
        ruido_lon = rng.gauss(0, 3) / (111_320.0 * math.cos(math.radians(-23.547)))
        ruido_lat = rng.gauss(0, 3) / 110_600.0
        pos = Posicao(lat=ponto[1] + ruido_lat, lon=ponto[0] + ruido_lon, precisao_m=8.0)
        a = avaliar_posicao(pos, rota, parametros)
        estados.append(a.estado)
        if a.projecao is not None:
            # O progresso nunca anda para trás mais que o ruído (3 sigma ~ 9 m).
            assert a.projecao.distancia_percorrida_m >= anterior - 12.0
            anterior = a.projecao.distancia_percorrida_m

    assert "fora_da_rota" not in estados
    assert "precisao_insuficiente" not in estados
    assert estados[0] == "na_rota"
    assert estados[-1] == "chegou"


def _ponto_na_rota(rota: list[list[float]], distancia_m: float) -> list[float]:
    """Ponto a `distancia_m` do início, andando pelos vértices (apoio do teste)."""
    lat0 = rota[0][1]
    m_lon = 111_320.0 * math.cos(math.radians(lat0))
    restante = distancia_m
    for (lon_a, lat_a), (lon_b, lat_b) in zip(rota, rota[1:], strict=False):
        dx = (lon_b - lon_a) * m_lon
        dy = (lat_b - lat_a) * 110_600.0
        comprimento = math.hypot(dx, dy)
        if restante <= comprimento:
            f = restante / comprimento
            return [lon_a + (lon_b - lon_a) * f, lat_a + (lat_b - lat_a) * f]
        restante -= comprimento
    return rota[-1]
