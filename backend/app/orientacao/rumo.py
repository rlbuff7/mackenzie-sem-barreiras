"""Rumo do usuário e direção do alvo (RF09, RNF05).

Funções puras: nada é gravado (RNF04). Convenção de ângulos: graus de 0 a 360, 0 = norte,
sentido horário (90 = leste), como a bússola do celular. A diferença entre dois rumos fica
em (-180, 180]: positiva = o alvo está à DIREITA de quem olha para o rumo do usuário.

Silêncio é melhor que palpite: sem bússola, bússola instável ou pessoa parada, a direção é
`None` e nenhuma mensagem de lado sai. O rumo vem só da bússola do aparelho (`rumo_graus`);
se um dia a análise de GPS provar que a bússola é ruim, o rumo derivado do movimento entra
aqui (ver plano, "fica para depois").

Os setores (frente +-30, lados 30 a 150, atrás > 150) e os limites são PROVISÓRIOS, vêm do
`.env` (`ParametrosRumo.de_configuracoes`) e serão decididos com a orientadora.
"""

import math
from dataclasses import dataclass
from typing import Literal

from app.config import Configuracoes
from app.orientacao.posicao import _plano_local

Direcao = Literal["frente", "direita", "esquerda", "atras"]

# Alvo a menos disto da posição: a direção até ele não tem sentido (ruído do GPS manda).
_DISTANCIA_MINIMA_ATE_O_ALVO_M = 1.0


@dataclass(frozen=True)
class ParametrosRumo:
    alvo_a_frente_m: float
    velocidade_parado_ms: float
    oscilacao_maxima_graus: float
    setor_frente_graus: float
    setor_atras_graus: float

    @classmethod
    def de_configuracoes(cls, config: Configuracoes) -> "ParametrosRumo":
        return cls(
            alvo_a_frente_m=config.alvo_a_frente_metros,
            velocidade_parado_ms=config.velocidade_parado_ms,
            oscilacao_maxima_graus=config.rumo_oscilacao_maxima_graus,
            setor_frente_graus=config.setor_frente_graus,
            setor_atras_graus=config.setor_atras_graus,
        )


def diferenca_angular(alvo: float, usuario: float) -> float:
    """Quanto girar, em graus, do rumo do usuário até o rumo do alvo: (-180, 180].

    Positivo = direita. Trata o giro (359 -> 1 = +2, 1 -> 359 = -2)."""
    diferenca = (alvo - usuario) % 360.0
    return diferenca - 360.0 if diferenca > 180.0 else diferenca


def setor_da_diferenca(diferenca_graus: float, parametros: ParametrosRumo) -> Direcao:
    """frente (|d| <= setor_frente), atrás (|d| > setor_atras), senão o lado do sinal."""
    modulo = abs(diferenca_graus)
    if modulo <= parametros.setor_frente_graus:
        return "frente"
    if modulo > parametros.setor_atras_graus:
        return "atras"
    return "direita" if diferenca_graus > 0 else "esquerda"


def rumo_do_usuario(
    rumo_graus: float | None, oscilacao_graus: float | None, parametros: ParametrosRumo
) -> float | None:
    """Rumo da bússola em [0, 360), ou `None` se ausente, inválido ou instável.

    `oscilacao_graus` ausente é aceito (o aparelho nem sempre informa); presente e acima do
    limite, ou inválido, descarta o rumo."""
    if rumo_graus is None or not math.isfinite(rumo_graus) or not 0.0 <= rumo_graus <= 360.0:
        return None
    if oscilacao_graus is not None and (
        not math.isfinite(oscilacao_graus)
        or oscilacao_graus < 0.0
        or oscilacao_graus > parametros.oscilacao_maxima_graus
    ):
        return None
    return rumo_graus % 360.0


def esta_parado(velocidade_ms: float | None, parametros: ParametrosRumo) -> bool:
    """Parado quando a velocidade é menor que o limite, ausente ou inválida (sem dado, sem
    direção): parado a bússola aponta para onde o celular está virado, não para onde se anda."""
    if velocidade_ms is None or not math.isfinite(velocidade_ms):
        return True
    return velocidade_ms < parametros.velocidade_parado_ms


def ponto_na_rota(geometria_rota: list[list[float]], distancia_m: float) -> tuple[float, float]:
    """(lon, lat) do ponto a `distancia_m` do início, medida ao longo da linha da rota.

    Fora do intervalo, prende no primeiro/último vértice. Mesma aproximação plana local de
    `posicao.py`. A rota precisa ter pelo menos 2 vértices (já validada por quem chama)."""
    m_lon, m_lat = _plano_local(geometria_rota[0][1])
    restante = max(0.0, distancia_m)
    for (lon_a, lat_a, *_), (lon_b, lat_b, *_) in zip(
        geometria_rota, geometria_rota[1:], strict=False
    ):
        comprimento = math.hypot((lon_b - lon_a) * m_lon, (lat_b - lat_a) * m_lat)
        if comprimento > 0.0 and restante <= comprimento:
            t = restante / comprimento
            return lon_a + t * (lon_b - lon_a), lat_a + t * (lat_b - lat_a)
        restante -= comprimento
    ultimo = geometria_rota[-1]
    return ultimo[0], ultimo[1]


def rumo_ate_o_alvo(lat: float, lon: float, lat_alvo: float, lon_alvo: float) -> float:
    """Rumo (0 a 360, 0 = norte) da posição até o alvo, em plano local."""
    m_lon, m_lat = _plano_local(lat)
    leste = (lon_alvo - lon) * m_lon
    norte = (lat_alvo - lat) * m_lat
    return math.degrees(math.atan2(leste, norte)) % 360.0


def direcao_relativa(
    geometria_rota: list[list[float]],
    *,
    lat: float,
    lon: float,
    distancia_percorrida_m: float,
    velocidade_ms: float | None,
    rumo_graus: float | None,
    oscilacao_graus: float | None,
    parametros: ParametrosRumo,
) -> Direcao | None:
    """Onde o próximo ponto da rota (`alvo_a_frente_m` adiante) fica em relação a quem olha
    para o rumo da bússola. `None` (silêncio) se parado, sem bússola confiável ou alvo
    colado na posição."""
    if esta_parado(velocidade_ms, parametros):
        return None
    rumo = rumo_do_usuario(rumo_graus, oscilacao_graus, parametros)
    if rumo is None:
        return None
    lon_alvo, lat_alvo = ponto_na_rota(
        geometria_rota, distancia_percorrida_m + parametros.alvo_a_frente_m
    )
    m_lon, m_lat = _plano_local(lat)
    if (
        math.hypot((lon_alvo - lon) * m_lon, (lat_alvo - lat) * m_lat)
        < _DISTANCIA_MINIMA_ATE_O_ALVO_M
    ):
        return None
    diferenca = diferenca_angular(rumo_ate_o_alvo(lat, lon, lat_alvo, lon_alvo), rumo)
    return setor_da_diferenca(diferenca, parametros)
