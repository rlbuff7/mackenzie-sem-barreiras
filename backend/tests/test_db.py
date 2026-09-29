"""Testes da fronteira transacional das rotas: `app/db.py::obter_conexao`.

Os outros testes HTTP trocam `obter_conexao` por uma conexão fixa
(`conftest.py::cliente`), então nunca exercitam o commit de verdade. Estes não
usam o override: a app real roda com um pool de conexões REAIS ao banco de teste
(G8), só que de uma subclasse de `psycopg.Connection` que anota quando o
`commit`/`rollback` acontece. Um invólucro ASGI anota quando o cabeçalho da
resposta sai para o cliente. O que se testa é a ORDEM desses eventos.
"""

from collections.abc import Iterator

import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.config import obter_configuracoes
from app.db import obter_conexao
from app.main import app
from app.routers import alertas, barreiras, referencia, validacao

_EVENTOS_DE_INTERESSE = {"commit", "rollback", "resposta enviada"}


@pytest.fixture
def eventos() -> list[str]:
    return []


@pytest.fixture
def cliente_sem_override(eventos: list[str]) -> Iterator[TestClient]:
    """`TestClient` da app real, com o `obter_conexao` real (sem override).

    O pool é posto em `app.state` à mão, porque o `TestClient` sem `with` não
    roda o `lifespan` (que abriria o pool de verdade). Tamanho 1: a conexão que
    a rota recebe é sempre uma `ConexaoInstrumentada`.
    """

    class ConexaoInstrumentada(psycopg.Connection):
        def commit(self) -> None:
            eventos.append("commit")
            super().commit()

        def rollback(self) -> None:
            eventos.append("rollback")
            super().rollback()

    pool = ConnectionPool(
        conninfo=obter_configuracoes().conninfo,
        connection_class=ConexaoInstrumentada,
        min_size=1,
        max_size=1,
        open=False,
    )
    pool.open(wait=True)

    async def app_que_anota_o_envio(scope, receive, send) -> None:
        async def enviar(mensagem) -> None:
            if mensagem["type"] == "http.response.start":
                eventos.append("resposta enviada")
            await send(mensagem)

        await app(scope, receive, enviar)

    app.state.pool_conexoes = pool
    try:
        yield TestClient(app_que_anota_o_envio)
    finally:
        del app.state.pool_conexoes
        pool.close()


def _ordem(eventos: list[str]) -> list[str]:
    return [evento for evento in eventos if evento in _EVENTOS_DE_INTERESSE]


def test_commit_acontece_antes_de_a_resposta_ser_enviada(
    cliente_sem_override: TestClient, eventos: list[str]
) -> None:
    """Regressão do achado da revisão final: com o escopo padrão ("request") de
    uma dependência com `yield`, o FastAPI 0.141 envia a resposta e SÓ DEPOIS
    sai da dependência. Um 201 "Alerta recebido" podia ser seguido de um commit
    que falha, e o alerta sumia. Com `scope="function"`, o commit vem antes: se
    ele falhar, o cliente recebe 500, não um 201 falso."""
    resposta = cliente_sem_override.get("/saude")

    assert resposta.status_code == 200
    assert _ordem(eventos) == ["commit", "resposta enviada"]


def test_rollback_acontece_antes_de_a_resposta_de_erro_ser_enviada(
    cliente_sem_override: TestClient, eventos: list[str]
) -> None:
    """Rota que levanta erro (bbox malformado → 422): rollback, depois a resposta."""
    resposta = cliente_sem_override.get("/barreiras", params={"bbox": "nao,e,um,bbox"})

    assert resposta.status_code == 422
    assert _ordem(eventos) == ["rollback", "resposta enviada"]


def _dependencias(dependente) -> Iterator:
    for sub in dependente.dependencies:
        yield sub
        yield from _dependencias(sub)


def test_toda_rota_com_banco_usa_obter_conexao_com_escopo_de_funcao() -> None:
    """Os dois testes acima exercitam duas rotas; este garante que TODAS as rotas
    que pedem conexão usam o mesmo escopo, inclusive uma rota nova que alguém
    escreva com `Depends(obter_conexao)` direto em vez do alias `ConexaoDaRequisicao`.

    As rotas são lidas dos routers: no FastAPI 0.141, `app.routes` guarda cada
    router incluído como um invólucro interno, sem os `APIRoute`. O conjunto de
    rotas do OpenAPI da app confere que nenhum router ficou de fora."""
    escopo_por_rota = {
        (rota.path, metodo): dependencia.scope
        for modulo in (referencia, alertas, barreiras, validacao)
        for rota in modulo.router.routes
        if isinstance(rota, APIRoute)
        for metodo in rota.methods
        for dependencia in _dependencias(rota.dependant)
        if dependencia.call is obter_conexao
    }
    rotas_da_app = {
        (caminho, metodo.upper())
        for caminho, operacoes in app.openapi()["paths"].items()
        for metodo in operacoes
    }

    assert set(escopo_por_rota) == rotas_da_app
    assert set(escopo_por_rota.values()) == {"function"}, escopo_por_rota
