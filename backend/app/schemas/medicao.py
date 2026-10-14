"""Schemas Pydantic de `POST /medicoes` (medição de GPS em tempo real, contrato de
14/10/2026).

É dado DA EQUIPE (os celulares dela nos pontos de controle), nunca de quem navega.
As regras espelham as CHECK constraints da tabela `medicoes_gps` (migration 005):
o que o banco recusaria vira 422 aqui, com o campo apontado, e nunca um 500.

O corpo é validado com `model_validate_json`: em modo JSON o `strict` aceita o
que o JSON distingue (`"5"` não é número; `true` não é 1) e continua exigindo
texto para a data (um número não vira data Unix por conversão).
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

# Tipos que carregam posição: `latitude`, `longitude` e `precisao_m` são obrigatórios.
_TIPOS_COM_POSICAO = frozenset({"ponto", "trajeto"})

TAMANHO_MAXIMO_DO_LOTE = 50

# `strict=True`: `true` não vira 1.0 e "5" não vira 5. `allow_inf_nan=False`: `NaN` e
# `1e999` não são medida (o banco aceitaria `Infinity`, e a consulta de resumo
# quebraria). Inteiro JSON continua valendo como coordenada (-23 é um float válido).
_Numero = Annotated[float, Field(strict=True, allow_inf_nan=False)]
_NumeroNaoNegativo = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0)]


def _texto_gravavel(valor: str) -> str:
    """Recusa o que o PostgreSQL não grava em texto: U+0000 e substituto UTF-16
    isolado (`\\ud800`). Sem isso o INSERT falharia e a API devolveria 500."""
    if "\x00" in valor:
        raise ValueError("Não pode ter o caractere U+0000.")
    try:
        valor.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Tem um caractere inválido (substituto UTF-16 isolado).") from None
    return valor


class MedicaoEntrada(BaseModel):
    """Uma medição de `POST /medicoes`.

    `extra="forbid"`: campo desconhecido é erro, não é ignorado em silêncio (assim
    nenhum dado pessoal, como um nome, entra por engano).

    A ORDEM dos campos importa: os validadores de `ponto`, `latitude`, `longitude`
    e `precisao_m` olham os campos anteriores (`info.data`) para aplicar as regras
    de obrigatoriedade por tipo e apontar o erro no campo certo.
    """

    model_config = ConfigDict(extra="forbid", validate_default=True)

    id_cliente: UUID
    tipo: Literal["ponto", "trajeto", "bussola", "vibracao"]
    # Fuso obrigatório: "2026-10-14T10:30:00" sem fuso é ambíguo. `strict` exige texto.
    medido_em: Annotated[AwareDatetime, Field(strict=True)]
    aparelho: str = Field(min_length=1, max_length=80)
    ponto: int | None = Field(default=None, strict=True, ge=1, le=12)
    condicao: Literal["ceu_aberto", "entre_predios", "coberto"] | None = None
    latitude: _Numero | None = Field(default=None, ge=-90, le=90)
    longitude: _Numero | None = Field(default=None, ge=-180, le=180)
    precisao_m: _NumeroNaoNegativo | None = None
    altitude_m: _Numero | None = None
    altitude_precisao_m: _Numero | None = None
    velocidade_ms: _Numero | None = None
    rumo_gps_graus: _Numero | None = None
    bussola_graus: _NumeroNaoNegativo | None = Field(default=None, lt=360)
    bussola_fonte: Literal["webkitCompassHeading", "alpha_absoluto", "alpha_relativo"] | None = None
    bussola_oscilacao_graus: _NumeroNaoNegativo | None = None
    vibracao_suportada: bool | None = Field(default=None, strict=True)
    observacao: str | None = Field(default=None, max_length=500)
    user_agent: str | None = Field(default=None, max_length=300)

    @field_validator("aparelho", "observacao", "user_agent", mode="before")
    @classmethod
    def _limpar_texto(cls, valor: object, info: ValidationInfo) -> object:
        """Espaços nas pontas removidos (aparelho em branco fica vazio e cai no
        tamanho mínimo, como a CHECK `btrim(aparelho) <> ''`); observação ou
        user-agent vazios viram `None`. Texto que o banco não grava é recusado."""
        if not isinstance(valor, str):
            return valor
        texto = _texto_gravavel(valor).strip()
        if info.field_name == "aparelho":
            return texto
        return texto or None

    @field_validator("ponto", mode="after")
    @classmethod
    def _ponto_obrigatorio_no_tipo_ponto(
        cls, valor: int | None, info: ValidationInfo
    ) -> int | None:
        if valor is None and info.data.get("tipo") == "ponto":
            raise ValueError("Obrigatório quando o tipo é 'ponto' (número de 1 a 12).")
        return valor

    @field_validator("latitude", "longitude", mode="after")
    @classmethod
    def _coordenada_obrigatoria_nos_tipos_com_posicao(
        cls, valor: float | None, info: ValidationInfo
    ) -> float | None:
        if valor is None and info.data.get("tipo") in _TIPOS_COM_POSICAO:
            raise ValueError(f"Obrigatória quando o tipo é '{info.data['tipo']}'.")
        return valor

    @field_validator("longitude", mode="after")
    @classmethod
    def _latitude_e_longitude_andam_juntas(
        cls, valor: float | None, info: ValidationInfo
    ) -> float | None:
        # `latitude` fora de `info.data` = ela própria já falhou (erro apontado lá).
        if "latitude" not in info.data:
            return valor
        latitude = info.data["latitude"]
        if valor is not None and latitude is None:
            raise ValueError("Informe a latitude junto com a longitude.")
        if valor is None and latitude is not None:
            raise ValueError("Informe a longitude junto com a latitude.")
        return valor

    @field_validator("precisao_m", mode="after")
    @classmethod
    def _precisao_obrigatoria_com_posicao(
        cls, valor: float | None, info: ValidationInfo
    ) -> float | None:
        """O banco exige `precisao_m` sempre que há `geom`, em qualquer tipo."""
        if valor is not None:
            return valor
        tem_posicao = (
            info.data.get("latitude") is not None and info.data.get("longitude") is not None
        )
        if tem_posicao or info.data.get("tipo") in _TIPOS_COM_POSICAO:
            raise ValueError(
                "Obrigatória nos tipos 'ponto' e 'trajeto' e sempre que há latitude e longitude."
            )
        return valor


class MedicoesEntrada(BaseModel):
    """Corpo de `POST /medicoes`: de 1 a 50 medições (o trajeto vai em lotes)."""

    model_config = ConfigDict(extra="forbid")

    medicoes: list[MedicaoEntrada] = Field(min_length=1, max_length=TAMANHO_MAXIMO_DO_LOTE)


class MedicoesGravadas(BaseModel):
    """Corpo de sucesso (200) de `POST /medicoes`."""

    gravadas: int
    repetidas: int
