"""Custo dos trechos de rota (CLAUDE.md §6): comprimento × fator.

O fator vem das penalidades do `.env` (`Configuracoes`), nunca de número solto no
código. Valores PROVISÓRIOS: a calibração é decisão da orientadora (§13.5).

Segurança do perfil `cadeirante`: escada e trecho marcado como inacessível NÃO entram
no grafo da consulta (`trecho_proibido`). Penalidade alta não basta: com ela a rota
ainda poderia passar pela escada quando não há outro caminho. Sem caminho sobrando, a
API responde que não há rota (silêncio é melhor que palpite).

Perfil `deficiencia_visual` (incluído na v0 em 27/10/2026, a validar com a orientadora):
nada é proibido, mas o fator do perfil multiplica por `PENALIDADE_PERFIL_VISUAL`
(PROVISÓRIO, padrão 2.0) quando o trecho é escada, travessia ou NÃO foi conferido a pé.
Assim a rota prefere calçada conferida; escada só entra quando compensa.
"""

from typing import Literal

from app.config import Configuracoes

Perfil = Literal["sem_restricao", "cadeirante", "deficiencia_visual"]


def trecho_proibido(*, tipo: str, acessivel_cadeirante: bool | None, perfil: Perfil) -> bool:
    """`True` se o trecho nunca pode aparecer na rota deste perfil."""
    if perfil == "cadeirante":
        return tipo == "escada" or acessivel_cadeirante is False
    return False


def fator_do_trecho(
    *,
    tipo: str,
    acessivel_cadeirante: bool | None,
    fonte_verificacao: str,
    perfil: Perfil,
    config: Configuracoes,
) -> float:
    """Multiplicador do comprimento do trecho (>= 1).

    `fator = base do tipo × fator de verificação × fator do perfil`.
    Levanta `ValueError` para trecho proibido ao perfil: quem monta o grafo deve tê-lo
    excluído antes (`trecho_proibido`).
    """
    if trecho_proibido(tipo=tipo, acessivel_cadeirante=acessivel_cadeirante, perfil=perfil):
        raise ValueError(f"trecho '{tipo}' não pode ser usado pelo perfil '{perfil}'")

    base = {
        "escada": config.penalidade_escada,
        "travessia": config.penalidade_travessia,
    }.get(tipo, 1.0)
    verificacao = (
        1.0 if fonte_verificacao == "conferido_a_pe" else config.penalidade_trecho_nao_verificado
    )
    # Cadeirante e acessibilidade ainda não verificada: pesa como trecho não verificado.
    perfil_fator = (
        config.penalidade_trecho_nao_verificado
        if perfil == "cadeirante" and acessivel_cadeirante is None
        else 1.0
    )
    if perfil == "deficiencia_visual" and (
        tipo in ("escada", "travessia") or fonte_verificacao != "conferido_a_pe"
    ):
        perfil_fator = config.penalidade_perfil_visual
    return base * verificacao * perfil_fator
