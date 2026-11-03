"""Posição do usuário em relação à rota (RF08, RF12, RNF05).

Funções puras: recebem a posição e a rota, devolvem o resultado, e nada é gravado (RNF04:
a posição de quem navega nunca vai a banco, log ou arquivo).

Geometria: a rota chega em lat/lon (SRID 4326, `[lon, lat]`). Distância se mede em metros
numa projeção plana local centrada no primeiro vértice da rota, a mesma aproximação de
`app/rotas/instrucoes.py`. Em escala de campus (centenas de metros) ela difere do
SRID 31983 (CLAUDE.md §5) em bem menos de 0,1%, e dispensa dependência nova (não há pyproj
no projeto). Se um dia a rota passar de alguns quilômetros, reprojetar com 31983.

Princípio de segurança: silêncio é melhor que palpite. Com precisão pior que o mínimo,
`avaliar_posicao` devolve `precisao_insuficiente` SEM projeção, SEM distância restante.

Regras PROVISÓRIAS, a calibrar com a medição de GPS e com a orientadora (pendência #1):
ver `docs/planos/m4-orientacao-ao-vivo.md`.
"""

import math
from dataclasses import dataclass
from typing import Literal

from app.config import Configuracoes

Estado = Literal["na_rota", "fora_da_rota", "precisao_insuficiente", "chegou"]
Confianca = Literal["alta", "media", "baixa"]

_METROS_POR_GRAU_LAT = 110_600.0
_METROS_POR_GRAU_LON_NO_EQUADOR = 111_320.0

# "alta" exige precisão informada no máximo nesta fração do mínimo aceito. Provisório.
_FRACAO_DA_PRECISAO_PARA_CONFIANCA_ALTA = 0.5


@dataclass(frozen=True)
class Posicao:
    """O que o celular informa. A precisão é a do aparelho, em metros (1 sigma ou 68%,
    conforme o sistema): serve de gatilho de silêncio e de margem, não de verdade."""

    lat: float
    lon: float
    precisao_m: float


@dataclass(frozen=True)
class ParametrosOrientacao:
    """Limiares em metros. Vêm do `.env` (`de_configuracoes`); nenhum fica no código."""

    precisao_minima_m: float
    distancia_fora_da_rota_m: float
    raio_chegada_m: float

    @classmethod
    def de_configuracoes(cls, config: Configuracoes) -> "ParametrosOrientacao":
        return cls(
            precisao_minima_m=config.precisao_minima_metros,
            distancia_fora_da_rota_m=config.distancia_fora_da_rota_metros,
            raio_chegada_m=config.raio_chegada_metros,
        )


@dataclass(frozen=True)
class ProjecaoNaRota:
    """Ponto da rota mais próximo da posição (map matching por trecho)."""

    lat: float
    lon: float
    distancia_perpendicular_m: float  # da posição ao ponto projetado
    distancia_percorrida_m: float  # do início da rota até o ponto projetado
    distancia_restante_m: float  # do ponto projetado até o fim da rota
    indice_trecho: int  # 0 = segmento entre o vértice 0 e o 1


@dataclass(frozen=True)
class Avaliacao:
    estado: Estado
    confianca: Confianca
    # None quando o estado é `precisao_insuficiente`: nenhuma orientação sai.
    projecao: ProjecaoNaRota | None


def _plano_local(lat_de_referencia: float) -> tuple[float, float]:
    """(metros por grau de longitude, metros por grau de latitude) perto da referência."""
    return (
        _METROS_POR_GRAU_LON_NO_EQUADOR * math.cos(math.radians(lat_de_referencia)),
        _METROS_POR_GRAU_LAT,
    )


def projetar_na_rota(posicao: Posicao, geometria_rota: list[list[float]]) -> ProjecaoNaRota:
    """Projeta a posição no segmento da rota mais próximo.

    `geometria_rota` é `[[lon, lat], ...]` na ordem do percurso. Antes do início ou depois
    do fim a projeção fica presa ao primeiro/último vértice (a distância perpendicular
    então mede a distância até a ponta). Em empate, vale o primeiro trecho; rotas que
    voltam sobre si mesmas podem ser ambíguas (ver plano, "o que fica para depois").

    Levanta `ValueError` se a rota tem menos de 2 vértices, extensão zero ou números não
    finitos: rota inválida é erro de quem chama, não motivo para chutar.
    """
    if len(geometria_rota) < 2:
        raise ValueError("a rota precisa de pelo menos 2 vértices")
    if not all(math.isfinite(v) for ponto in geometria_rota for v in ponto[:2]):
        raise ValueError("a rota tem coordenada não finita")
    if not (math.isfinite(posicao.lat) and math.isfinite(posicao.lon)):
        raise ValueError("a posição tem coordenada não finita")

    m_lon, m_lat = _plano_local(geometria_rota[0][1])
    lon0, lat0 = geometria_rota[0][0], geometria_rota[0][1]
    pontos = [((lon - lon0) * m_lon, (lat - lat0) * m_lat) for lon, lat, *_ in geometria_rota]
    px = (posicao.lon - lon0) * m_lon
    py = (posicao.lat - lat0) * m_lat

    comprimentos = [
        math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(pontos, pontos[1:], strict=False)
    ]
    total = sum(comprimentos)
    if total == 0.0:
        raise ValueError("a rota tem extensão zero")

    melhor: tuple[float, int, float, float, float] | None = None  # dist, trecho, x, y, ao longo
    acumulado = 0.0
    for indice, ((ax, ay), (bx, by)) in enumerate(zip(pontos, pontos[1:], strict=False)):
        comprimento = comprimentos[indice]
        if comprimento > 0.0:
            # Fração do segmento sob a posição, presa a [0, 1].
            t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / comprimento**2
            t = min(1.0, max(0.0, t))
        else:
            t = 0.0
        x = ax + t * (bx - ax)
        y = ay + t * (by - ay)
        distancia = math.hypot(px - x, py - y)
        if melhor is None or distancia < melhor[0]:
            melhor = (distancia, indice, x, y, acumulado + t * comprimento)
        acumulado += comprimento

    assert melhor is not None  # há pelo menos 1 segmento
    distancia, indice, x, y, percorrida = melhor
    return ProjecaoNaRota(
        lat=lat0 + y / m_lat,
        lon=lon0 + x / m_lon,
        distancia_perpendicular_m=distancia,
        distancia_percorrida_m=percorrida,
        distancia_restante_m=max(0.0, total - percorrida),
        indice_trecho=indice,
    )


def _confianca(
    estado: Estado, projecao: ProjecaoNaRota, precisao_m: float, parametros: ParametrosOrientacao
) -> Confianca:
    """Regra de confiança (PROVISÓRIA), do mais seguro para o menos.

    - baixa: fora da rota, ou desvio além de `distancia_fora_da_rota_m` (só ainda "na
      rota" por causa da margem da precisão).
    - alta: precisão informada <= metade do mínimo E desvio <= precisão informada. O
      segundo critério existe porque a precisão do celular não acompanhou o erro real na
      medição (P01: dizia 3 m, errou 19 m; iPhone fixo em 14,25 m): a posição precisa
      "bater" com a rota para ganhar confiança alta.
    - media: o resto.
    """
    if estado == "fora_da_rota" or projecao.distancia_perpendicular_m > (
        parametros.distancia_fora_da_rota_m
    ):
        return "baixa"
    precisao_boa = (
        precisao_m <= parametros.precisao_minima_m * _FRACAO_DA_PRECISAO_PARA_CONFIANCA_ALTA
    )
    if precisao_boa and projecao.distancia_perpendicular_m <= precisao_m:
        return "alta"
    return "media"


def avaliar_posicao(
    posicao: Posicao, geometria_rota: list[list[float]], parametros: ParametrosOrientacao
) -> Avaliacao:
    """Estado e confiança da posição em relação à rota.

    Ordem das regras (a primeira que vale decide):
    1. `precisao_insuficiente`: precisão > mínimo, ou ausente/inválida (<= 0, NaN, inf).
       Sem projeção: silêncio.
    2. `fora_da_rota`: desvio > `distancia_fora_da_rota_m` + `precisao_m` (a margem cresce
       com a imprecisão, para não acusar saída da rota por ruído).
    3. `chegou`: distância restante ao longo da rota <= `raio_chegada_m`.
    4. `na_rota`.
    """
    precisao = posicao.precisao_m
    if not math.isfinite(precisao) or precisao <= 0 or precisao > parametros.precisao_minima_m:
        return Avaliacao(estado="precisao_insuficiente", confianca="baixa", projecao=None)

    projecao = projetar_na_rota(posicao, geometria_rota)
    estado: Estado
    if projecao.distancia_perpendicular_m > parametros.distancia_fora_da_rota_m + precisao:
        estado = "fora_da_rota"
    elif projecao.distancia_restante_m <= parametros.raio_chegada_m:
        estado = "chegou"
    else:
        estado = "na_rota"
    return Avaliacao(
        estado=estado,
        confianca=_confianca(estado, projecao, precisao, parametros),
        projecao=projecao,
    )
