"""Corpo de `POST /rotas` (E6). Estrito: campo desconhecido é erro, não é ignorado."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator, model_validator


class RotaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origem_id: StrictInt
    destino_id: StrictInt
    perfil: Literal["sem_restricao", "cadeirante"] = "sem_restricao"

    @field_validator("perfil", mode="before")
    @classmethod
    def _perfil_ainda_nao_existe(cls, valor: object) -> object:
        # Decisão pendente com a orientadora (§13.5 e §13.6): fora do E6.
        if valor == "deficiencia_visual":
            raise ValueError("Perfil ainda não disponível.")
        return valor

    @model_validator(mode="after")
    def _origem_diferente_de_destino(self) -> "RotaEntrada":
        if self.origem_id == self.destino_id:
            raise ValueError("Origem e destino devem ser pontos diferentes.")
        return self
