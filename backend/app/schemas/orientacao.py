"""Corpo de `POST /orientacoes` (M4). Estrito: campo desconhecido é erro.

A posição de quem navega chega aqui e NUNCA é gravada (RNF04). Campos opcionais do
aparelho (`rumo_graus`, `rumo_oscilacao_graus`, `velocidade_ms`): se o aparelho não
informa o valor (ex.: velocidade -1 do iOS), o cliente OMITE o campo; valor negativo é 422.
"""

from pydantic import BaseModel, ConfigDict, Field, StrictFloat

from app.schemas.rota import RotaEntrada

MAXIMO_RECENTES = 20


class PosicaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: StrictFloat = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: StrictFloat = Field(ge=-180, le=180, allow_inf_nan=False)
    precisao_m: StrictFloat = Field(ge=0, le=100_000, allow_inf_nan=False)
    rumo_graus: StrictFloat | None = Field(default=None, ge=0, le=360, allow_inf_nan=False)
    rumo_oscilacao_graus: StrictFloat | None = Field(
        default=None, ge=0, le=360, allow_inf_nan=False
    )
    velocidade_ms: StrictFloat | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


class RecenteEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chave: str = Field(min_length=1, max_length=64)
    ha_segundos: StrictFloat = Field(ge=0, le=86_400, allow_inf_nan=False)


class OrientacaoEntrada(RotaEntrada):
    """Os campos de `RotaEntrada` (`origem_id`, `destino_id`, `perfil`, com as mesmas
    regras) mais a posição e as mensagens que o cliente já falou."""

    posicao: PosicaoEntrada
    recentes: list[RecenteEntrada] = Field(default_factory=list, max_length=MAXIMO_RECENTES)
