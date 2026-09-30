"""Pool de conexões psycopg: aberto/fechado no lifespan da aplicação FastAPI.

Só `obter_conexao` decide commit/rollback. Rotas e, a partir do M3, as funções
de `app/validacao/`, nunca chamam `commit()`/`rollback()` por conta própria —
isso mantém a fronteira transacional num único lugar.

Toda rota pede a conexão pelo alias `ConexaoDaRequisicao`, nunca por
`Depends(obter_conexao)` direto: o alias fixa `scope="function"`, que faz o
commit acontecer ANTES de a resposta ser enviada (ver `obter_conexao`).
"""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
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


def _emprestar_conexao(request: Request, timeout_segundos: float | None) -> Iterator[Connection]:
    """Empresta uma conexão do pool para a duração de uma rota.

    `timeout_segundos=None` usa o timeout padrão do pool (30 s); um número espera
    só esse tempo antes de devolver 503 "banco indisponível".
    """
    pool: ConnectionPool = request.app.state.pool_conexoes
    try:
        conexao = pool.getconn(timeout=timeout_segundos)
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


def obter_conexao(request: Request) -> Iterator[Connection]:
    """Empresta uma conexão do pool para a duração de uma rota.

    Faz `commit` se a rota terminar sem erro, `rollback` se levantar exceção —
    e sempre devolve a conexão ao pool ao final.

    Só é correta com `scope="function"` (use `ConexaoDaRequisicao`). No escopo
    padrão ("request"), o FastAPI 0.141 só sai de uma dependência com `yield`
    DEPOIS de enviar o corpo da resposta: `POST /alertas` podia responder 201
    "Alerta recebido" e só então tentar o commit, que, se falhasse, apagaria o
    alerta sem o cliente saber (e uma leitura logo depois da resposta podia
    ainda não ver a linha). Com `scope="function"`, o FastAPI sai da dependência
    assim que a rota termina e ANTES de enviar a resposta: se o commit falhar, o
    cliente recebe 500, nunca um 201 falso. `backend/tests/test_db.py` confere
    essa ordem.

    Na maioria dos testes HTTP, esta dependência é substituída via
    `app.dependency_overrides` (backend/tests/conftest.py) por uma conexão fixa
    dentro de uma transação de teste, e este código não roda. `test_db.py` é a
    exceção: roda o código real, com um pool de conexões reais ao banco de teste.
    """
    yield from _emprestar_conexao(request, None)


# `/saude` é a sonda de "o banco responde?": esperar 30 s por uma conexão faria a
# sonda (healthcheck, monitor) pendurar. Lido a cada chamada, para o teste poder
# encurtar.
TIMEOUT_SAUDE_SEGUNDOS = 2.0


def obter_conexao_da_saude(request: Request) -> Iterator[Connection]:
    """Como `obter_conexao`, mas espera no máximo `TIMEOUT_SAUDE_SEGUNDOS`."""
    yield from _emprestar_conexao(request, TIMEOUT_SAUDE_SEGUNDOS)


# Tipo do parâmetro de toda rota que usa o banco (ver `obter_conexao`).
ConexaoDaRequisicao = Annotated[Connection, Depends(obter_conexao, scope="function")]
ConexaoDaSaude = Annotated[Connection, Depends(obter_conexao_da_saude, scope="function")]
