"""Schemas Pydantic do estágio 1 (schema) do pipeline de validação (CLAUDE.md §6).

`AlertaEntrada` é a única porta de entrada de um alerta: tanto `POST /alertas`
quanto o gerador de dados sintéticos (M3) validam o payload através dela, via
`app/validacao/entrada.py::registrar_alerta`.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertaEntrada(BaseModel):
    """Corpo de `POST /alertas` (Contrato da API).

    `extra="forbid"`: campo desconhecido é erro de schema, não é ignorado em
    silêncio — o funil precisa contar esse descarte (CLAUDE.md §6, estágio 1).
    """

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Código da taxonomia (D3), não o id: `tipo_que_nao_existe` também é erro
    # de schema aqui; "existe mas está inativo" só é sabido depois, contra o
    # banco (app/validacao/entrada.py::buscar_tipo_ativo).
    tipo: str = Field(min_length=1, max_length=40, pattern=r"^[a-z_]+$")
    severidade: int | None = Field(default=None, ge=1, le=3)
    descricao: str | None = Field(default=None, max_length=500)
    sessao_id: UUID

    @field_validator("descricao", mode="before")
    @classmethod
    def _remover_espacos_e_virar_none_se_vazio(cls, valor: object) -> object:
        """Espaços nas pontas removidos; descrição vazia vira `None` (Contrato)."""
        if isinstance(valor, str):
            texto = valor.strip()
            return texto or None
        return valor


class ErroCampo(BaseModel):
    """Um erro de validação apontando o campo do payload que falhou."""

    campo: str
    erro: str


class AlertaRegistrado(BaseModel):
    """Corpo de sucesso (201) de `POST /alertas` (Contrato da API)."""

    id: int
    status: str
    motivo_descarte: str | None
    mensagem: str
