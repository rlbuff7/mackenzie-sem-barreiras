"""Pool de conexões psycopg: aberto/fechado no lifespan da aplicação FastAPI.

Só `obter_conexao` decide commit/rollback. Rotas e, a partir do M3, as funções
de `app/validacao/`, nunca chamam `commit()`/`rollback()` por conta própria —
isso mantém a fronteira transacional num único lugar.
"""

from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from psycopg import Connection
from psycopg_pool import ConnectionPool, PoolTimeout

from app.config import Configuracoes, obter_configuracoes


def criar_pool(configuracoes: Configuracoes) -> ConnectionPool:
    """Monta o pool fechado (`open=False`): quem abre é o `lifespan`, que pode
    fazer isso de forma assíncrona sem bloquear a inicialização da app."""
    return ConnectionPool(conninfo=configuracoes.conninfo, open=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Abre o pool na subida da API e fecha no encerramento (`app.state`)."""
    pool = criar_pool(obter_configuracoes())
    pool.open(wait=True)
    app.state.pool_conexoes = pool
    try:
        yield
    finally:
        pool.close()


def obter_conexao(request: Request) -> Iterator[Connection]:
    """Empresta uma conexão do pool para a duração de uma requisição.

    Faz `commit` se a rota terminar sem erro, `rollback` se levantar exceção —
    e sempre devolve a conexão ao pool ao final.

    Em testes, esta dependência é substituída por completo via
    `app.dependency_overrides` (backend/tests/conftest.py), que devolve uma
    conexão fixa dentro de uma transação de teste; este código real não roda
    nesse caso.
    """
    pool: ConnectionPool = request.app.state.pool_conexoes
    try:
        conexao = pool.getconn()
    except PoolTimeout as erro:
        raise HTTPException(status_code=503, detail="banco indisponível") from erro

    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        pool.putconn(conexao)
