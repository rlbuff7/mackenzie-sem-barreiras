"""Rumo do usuário e direção do alvo (RF09, RNF05).

Funções puras: nada é gravado (RNF04). Convenção de ângulos: graus de 0 a 360, 0 = norte,
sentido horário (90 = leste), como a bússola do celular. A diferença entre dois rumos fica
em (-180, 180]: positiva = o alvo está à DIREITA de quem olha para o rumo do usuário.

Silêncio é melhor que palpite: sem deslocamento suficiente, com deslocamento menor que a
imprecisão do GPS ou pessoa parada, a direção é `None` e nenhuma mensagem de lado sai.

DECISÃO do Rodrigo (03/11/2026, a validar com a orientadora): fonte do rumo HÍBRIDA.
ANDANDO -> rumo pelo MOVIMENTO (azimute do deslocamento entre um ponto anterior da trilha e
a posição atual); PARADO -> rumo pela BÚSSOLA (para onde o celular está apontado). Andando
a bússola é ignorada (ela aponta para onde o aparelho está virado, não para onde se anda).
A trilha chega no corpo do pedido, só serve a este cálculo e NUNCA é gravada (RNF04).

Método do movimento: ponto de referência = o MAIS ANTIGO da trilha, dentro da janela, a pelo
menos `deslocamento_minimo_m` da posição atual. Escolhido em vez da média antigas-vs-recentes
porque dá a maior base de medida (menos erro angular por ruído de GPS), é simples de explicar
e de testar, e o teste de precisão já barra o ruído; a média mistura pontos de antes e depois
de uma curva e, com no máximo 10 pontos, fica instável. Contra: numa curva fechada recente o
rumo atrasa; aceito, pois silêncio e atraso são mais seguros que palpite.

Quem é "parado": a trilha tem pontos dentro da janela e NENHUM está a `deslocamento_minimo_m`
da posição atual (ou a velocidade média é menor que `velocidade_parado_ms`). Trilha vazia ou
toda fora da janela = não se sabe se anda: sem rumo (silêncio), não bússola. Deslocamento
suficiente mas menor que a soma das precisões = GPS ruidoso, também sem rumo.

Os setores (frente +-30, lados 30 a 150, atrás > 150) e os limites são PROVISÓRIOS, vêm do
`.env` (`ParametrosRumo.de_configuracoes`) e serão decididos com a orientadora.
"""

import math
from dataclasses import dataclass
from typing import Literal

from app.config import Configuracoes
from app.orientacao.posicao import _plano_local

Direcao = Literal["frente", "direita", "esquerda", "atras"]
FonteRumo = Literal["movimento", "bussola"]

# Alvo a menos disto da posição: a direção até ele não tem sentido (ruído do GPS manda).
_DISTANCIA_MINIMA_ATE_O_ALVO_M = 1.0


@dataclass(frozen=True)
class ParametrosRumo:
    alvo_a_frente_m: float
    velocidade_parado_ms: float
    oscilacao_maxima_graus: float
    deslocamento_minimo_m: float
    janela_trilha_s: float
    setor_frente_graus: float
    setor_atras_graus: float

    @classmethod
    def de_configuracoes(cls, config: Configuracoes) -> "ParametrosRumo":
        return cls(
            alvo_a_frente_m=config.alvo_a_frente_metros,
            velocidade_parado_ms=config.velocidade_parado_ms,
            oscilacao_maxima_graus=config.rumo_oscilacao_maxima_graus,
            deslocamento_minimo_m=config.deslocamento_minimo_rumo_metros,
            janela_trilha_s=config.janela_trilha_segundos,
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


@dataclass(frozen=True)
class PontoTrilha:
    """Posição anterior informada pelo cliente, `ha_segundos` atrás da atual. Só em memória."""

    lat: float
    lon: float
    precisao_m: float
    ha_segundos: float


def _rumo_do_movimento(
    lat: float,
    lon: float,
    precisao_m: float,
    trilha: list[PontoTrilha],
    parametros: ParametrosRumo,
) -> tuple[float | None, bool]:
    """(rumo, parado). `parado` só é True com trilha dentro da janela mostrando que a pessoa
    não se deslocou o mínimo; rumo `None` com parado False = sem informação confiável."""
    m_lon, m_lat = _plano_local(lat)
    na_janela = [
        p
        for p in trilha
        if math.isfinite(p.ha_segundos) and 0.0 < p.ha_segundos <= parametros.janela_trilha_s
    ]
    if not na_janela:
        return None, False
    candidatos = []
    for ponto in na_janela:
        leste = (lon - ponto.lon) * m_lon
        norte = (lat - ponto.lat) * m_lat
        distancia = math.hypot(leste, norte)
        if distancia >= parametros.deslocamento_minimo_m:
            candidatos.append((ponto, leste, norte, distancia))
    if not candidatos:
        return None, True  # sem deslocamento suficiente: parado
    ponto, leste, norte, distancia = max(candidatos, key=lambda c: c[0].ha_segundos)
    if distancia / ponto.ha_segundos < parametros.velocidade_parado_ms:
        return None, True
    if distancia < precisao_m + ponto.precisao_m:
        return None, False  # dentro do ruído do GPS: não confiável
    return math.degrees(math.atan2(leste, norte)) % 360.0, False


def rumo_do_movimento(
    lat: float,
    lon: float,
    precisao_m: float,
    trilha: list[PontoTrilha],
    parametros: ParametrosRumo,
) -> float | None:
    """Rumo (0 a 360, 0 = norte) pelo deslocamento, ou `None` (ver o módulo)."""
    return _rumo_do_movimento(lat, lon, precisao_m, trilha, parametros)[0]


def rumo_da_bussola(
    graus: float | None, oscilacao_graus: float | None, parametros: ParametrosRumo
) -> float | None:
    """Rumo da bússola em [0, 360), ou `None` se ausente, inválido ou instável.
    `oscilacao_graus` ausente é aceito; presente e acima do limite (ou inválido) descarta."""
    if graus is None or not math.isfinite(graus) or not 0.0 <= graus <= 360.0:
        return None
    if oscilacao_graus is not None and (
        not math.isfinite(oscilacao_graus)
        or oscilacao_graus < 0.0
        or oscilacao_graus > parametros.oscilacao_maxima_graus
    ):
        return None
    return graus % 360.0


def rumo_do_usuario(
    lat: float,
    lon: float,
    precisao_m: float,
    trilha: list[PontoTrilha],
    bussola_graus: float | None,
    bussola_oscilacao_graus: float | None,
    parametros: ParametrosRumo,
) -> tuple[float, FonteRumo] | None:
    """Fonte híbrida: andando, o movimento (bússola ignorada); parado, a bússola. `None` =
    sem rumo."""
    rumo, parado = _rumo_do_movimento(lat, lon, precisao_m, trilha, parametros)
    if rumo is not None:
        return rumo, "movimento"
    if parado:
        bussola = rumo_da_bussola(bussola_graus, bussola_oscilacao_graus, parametros)
        if bussola is not None:
            return bussola, "bussola"
    return None


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
    precisao_m: float,
    trilha: list[PontoTrilha],
    bussola_graus: float | None = None,
    bussola_oscilacao_graus: float | None = None,
    distancia_percorrida_m: float,
    parametros: ParametrosRumo,
) -> tuple[Direcao, FonteRumo] | None:
    """Onde o próximo ponto da rota (`alvo_a_frente_m` adiante) fica em relação ao rumo do
    usuário, e de que fonte veio o rumo. `None` (silêncio) se sem rumo ou alvo colado na
    posição."""
    achado = rumo_do_usuario(
        lat, lon, precisao_m, trilha, bussola_graus, bussola_oscilacao_graus, parametros
    )
    if achado is None:
        return None
    rumo, fonte = achado
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
    return setor_da_diferenca(diferenca, parametros), fonte
