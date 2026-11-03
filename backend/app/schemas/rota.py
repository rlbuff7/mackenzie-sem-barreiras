"""Corpo de `POST /rotas` (E6). Estrito: campo desconhecido é erro, não é ignorado."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator


class RotaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origem_id: StrictInt
    destino_id: StrictInt
    # "deficiencia_visual" e sinonimo antigo de "cegueira" (compatibilidade): vira "cegueira".
    perfil: Literal[
        "sem_restricao", "cadeirante", "cegueira", "baixa_visao", "deficiencia_visual"
    ] = "sem_restricao"

    @model_validator(mode="after")
    def _origem_diferente_de_destino(self) -> "RotaEntrada":
        if self.origem_id == self.destino_id:
            raise ValueError("Origem e destino devem ser pontos diferentes.")
        if self.perfil == "deficiencia_visual":
            self.perfil = "cegueira"
        return self
