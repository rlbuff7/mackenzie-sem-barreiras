"""Tipos simples compartilhados pelo cálculo de caminho e pelas instruções."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Trecho:
    """Uma aresta percorrida, já na ordem e na direção do caminho."""

    aresta_id: int
    tipo: str
    comprimento_m: float
    acessivel_cadeirante: bool | None
    fonte_verificacao: str
    no_de: int
    no_para: int
    custo: float
    coordenadas: list[list[float]]  # [[lon, lat], ...] no sentido do caminho
    mapeado_por: str | None = None
