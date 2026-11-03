"""Corpo de `POST /orientacoes` (M4). Estrito: campo desconhecido é erro.

Rumo híbrido (03/11/2026): andando, pelo movimento da trilha; parado, pela bússola.
A posição de quem navega, e a trilha (posições anteriores, usadas só para calcular o rumo
pelo movimento), chegam aqui e NUNCA são gravadas (RNF04). Sem trilha o servidor não dá
direção (silêncio), mas estado e mensagens continuam.
"""

from pydantic import BaseModel, ConfigDict, Field, StrictFloat

from app.schemas.rota import RotaEntrada

MAXIMO_RECENTES = 20
MAXIMO_TRILHA = 10


class PosicaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: StrictFloat = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: StrictFloat = Field(ge=-180, le=180, allow_inf_nan=False)
    precisao_m: StrictFloat = Field(ge=0, le=100_000, allow_inf_nan=False)
    # Para onde o celular está apontado. Só vale com a pessoa PARADA; andando é ignorado.
    # Se o aparelho não informa, o cliente OMITE o campo.
    rumo_bussola_graus: StrictFloat | None = Field(default=None, ge=0, le=360, allow_inf_nan=False)
    rumo_bussola_oscilacao_graus: StrictFloat | None = Field(
        default=None, ge=0, le=360, allow_inf_nan=False
    )


class PontoTrilhaEntrada(BaseModel):
    """Posição anterior. `ha_segundos` > 0; o teto da janela (JANELA_TRILHA_SEGUNDOS) é
    aplicado no cálculo (pontos mais antigos são ignorados), não aqui."""

    model_config = ConfigDict(extra="forbid")

    lat: StrictFloat = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: StrictFloat = Field(ge=-180, le=180, allow_inf_nan=False)
    precisao_m: StrictFloat = Field(ge=0, le=100_000, allow_inf_nan=False)
    ha_segundos: StrictFloat = Field(gt=0, le=86_400, allow_inf_nan=False)


class RecenteEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chave: str = Field(min_length=1, max_length=64)
    ha_segundos: StrictFloat = Field(ge=0, le=86_400, allow_inf_nan=False)


class OrientacaoEntrada(RotaEntrada):
    """Os campos de `RotaEntrada` (`origem_id`, `destino_id`, `perfil`, com as mesmas
    regras) mais a posição e as mensagens que o cliente já falou."""

    posicao: PosicaoEntrada
    trilha: list[PontoTrilhaEntrada] = Field(default_factory=list, max_length=MAXIMO_TRILHA)
    recentes: list[RecenteEntrada] = Field(default_factory=list, max_length=MAXIMO_RECENTES)
