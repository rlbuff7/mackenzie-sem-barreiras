"""Parâmetros de `POST /medicoes/fotos` (foto do ponto de controle, contrato de 22/10/2026).

A foto vai no corpo bruto (`image/jpeg`); o resto vem na query string. É dado DA
EQUIPE. As regras espelham as CHECK constraints de `fotos_pontos` (migration 008):
o que o banco recusaria vira 422 aqui, com o campo apontado, e nunca um 500.
"""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.medicao import _texto_gravavel


class FotoParametros(BaseModel):
    """Query string da foto. `extra="forbid"`: parâmetro desconhecido é erro."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_cliente: UUID
    ponto: Annotated[int, Field(ge=1, le=12)]
    aparelho: Annotated[str, Field(min_length=1, max_length=80)]
    tirada_em: AwareDatetime
    largura_px: Annotated[int, Field(ge=1, le=2048)] | None = None
    altura_px: Annotated[int, Field(ge=1, le=2048)] | None = None
    observacao: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("aparelho", "observacao")
    @classmethod
    def _gravavel(cls, valor: str | None) -> str | None:
        return None if valor is None else _texto_gravavel(valor)

    @field_validator("observacao")
    @classmethod
    def _vazia_vira_nula(cls, valor: str | None) -> str | None:
        return valor or None
