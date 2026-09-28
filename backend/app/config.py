"""Configurações do backend, lidas do `.env` da raiz do repositório.

Nenhum parâmetro de validação (DBSCAN_EPS_METROS, DBSCAN_MIN_POINTS,
MIN_CONFIRMACOES, SRID_ARMAZENAMENTO, SRID_CALCULO) pode aparecer como número
literal no código de `app/`: tudo passa por `Configuracoes` (CLAUDE.md §6, G7).
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from psycopg.conninfo import make_conninfo
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> raiz do repositório, onde
# mora o .env compartilhado com docker compose e db/banco.sh.
_RAIZ_REPO = Path(__file__).resolve().parent.parent.parent


class Configuracoes(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_RAIZ_REPO / ".env",
        env_file_encoding="utf-8",
        # O .env também guarda chaves usadas só pelo docker compose
        # (POSTGRES_PORTA_HOST vira alias abaixo; as demais não interessam aqui).
        extra="ignore",
    )

    # --- Banco ---
    postgres_host: str = "localhost"
    # POSTGRES_PORTA é a variável "correta"; POSTGRES_PORTA_HOST é a que o
    # docker compose já usa para mapear a porta no host (mesmo valor, nome
    # emprestado do compose). Aceitamos as duas para não duplicar a chave no .env.
    postgres_porta: int = Field(
        default=5434,
        validation_alias=AliasChoices("POSTGRES_PORTA", "POSTGRES_PORTA_HOST"),
    )
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # --- Validação (CLAUDE.md §6) — provisórios, calibrados só com dados reais ---
    dbscan_eps_metros: float
    dbscan_min_points: int
    min_confirmacoes: int
    srid_armazenamento: int
    srid_calculo: int

    # --- API ---
    # NoDecode: sem isso, pydantic-settings tentaria decodificar CORS_ORIGENS
    # como JSON antes do validador abaixo rodar, e uma string separada por
    # vírgula não é JSON válido.
    cors_origens: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://localhost:8080"]
    )
    # Header X-Token-Admin exigido por POST /validacao/executar (D7). Vazio =
    # sem proteção, só em desenvolvimento.
    token_admin: str = ""
    limite_barreiras_por_consulta: int = 1000

    @field_validator("cors_origens", mode="before")
    @classmethod
    def _dividir_lista_separada_por_virgula(cls, valor: object) -> object:
        if isinstance(valor, str):
            return [origem.strip() for origem in valor.split(",") if origem.strip()]
        return valor

    @property
    def conninfo(self) -> str:
        """String de conexão psycopg montada a partir dos campos acima."""
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_porta,
            dbname=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password,
        )


@lru_cache
def obter_configuracoes() -> Configuracoes:
    """Ponto único de leitura da configuração (cacheado).

    Rotas dependem dela via `Depends(obter_configuracoes)`, nunca chamando esta
    função diretamente no corpo do módulo — é o que permite aos testes
    substituir a configuração com `app.dependency_overrides` (ou, no caso do
    banco de teste, limpar este cache com `obter_configuracoes.cache_clear()`
    depois de trocar a variável de ambiente, como faz conftest.py).
    """
    return Configuracoes()
