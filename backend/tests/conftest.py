"""Fixtures compartilhadas pelos testes do backend.

Os testes batem no PostGIS real, num banco de teste separado
(`<POSTGRES_DB>_teste`) — nunca em mock de banco (G8).
"""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import obter_configuracoes
from app.db import obter_conexao
from app.main import app

_RAIZ_REPO = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session", autouse=True)
def banco_de_teste() -> None:
    """Recria `<POSTGRES_DB>_teste` do zero e aponta a configuração para ele.

    Roda ANTES de qualquer leitura "de verdade" da configuração (o `lifespan`
    da app só cria o pool quando o `TestClient` é usado, na fixture `cliente`,
    que depende desta): sobrescreve `POSTGRES_DB` no ambiente e limpa o cache
    de `obter_configuracoes`, para que a primeira chamada real já enxergue o
    banco de teste — nunca o banco de desenvolvimento.
    """
    resultado = subprocess.run(
        [str(_RAIZ_REPO / "db" / "banco.sh"), "preparar-teste"],
        cwd=_RAIZ_REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        # A saída do banco.sh (psql, docker compose) é o que explica a falha;
        # com `check=True` ela ficaria escondida no CalledProcessError.
        pytest.fail(
            f"./db/banco.sh preparar-teste saiu com código {resultado.returncode}. "
            "O banco do docker compose está de pé (`docker compose ps`)?\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}",
            pytrace=False,
        )

    configuracoes = obter_configuracoes()
    # Não usa a fixture `monkeypatch` porque ela é de escopo de função; aqui o
    # valor precisa valer para a sessão inteira (todo teste usa o banco de teste).
    os.environ["POSTGRES_DB"] = f"{configuracoes.postgres_db}_teste"
    obter_configuracoes.cache_clear()


@pytest.fixture
def conexao() -> Iterator[psycopg.Connection]:
    """Conexão ao banco de teste, dentro de uma transação sempre desfeita
    (`rollback`) ao final: cada teste começa limpo, sem recriar o banco."""
    configuracoes = obter_configuracoes()
    conexao_teste = psycopg.connect(configuracoes.conninfo)
    try:
        yield conexao_teste
    finally:
        conexao_teste.rollback()
        conexao_teste.close()


@pytest.fixture
def cliente(conexao: psycopg.Connection) -> Iterator[TestClient]:
    """`TestClient` cuja `obter_conexao` devolve sempre a mesma conexão de teste
    (mesma transação), em vez de pedir uma conexão nova do pool real."""

    def _obter_conexao_de_teste() -> Iterator[psycopg.Connection]:
        yield conexao

    app.dependency_overrides[obter_conexao] = _obter_conexao_de_teste
    try:
        with TestClient(app) as client:
            yield client
    finally:
        del app.dependency_overrides[obter_conexao]
