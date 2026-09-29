"""Testes HTTP de `POST /validacao/executar` e `GET /validacao/estatisticas` (Contrato)."""

from collections.abc import Callable, Iterator
from datetime import datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import obter_configuracoes
from app.main import app
from tests.auxiliares import inserir_alerta

_TOKEN = "token-de-teste"

# G8: valores de teste explícitos; o `.env` nunca é editado nem lido para isso.
_PARAMETROS_DE_TESTE = {"dbscan_eps_metros": 8.0, "dbscan_min_points": 2, "min_confirmacoes": 3}

_CHAVES_RESUMO = {
    "origem",
    "rotulo",
    "alertas_processados",
    "agrupados",
    "ruido_isolado",
    "barreiras_pendentes",
    "barreiras_confirmadas",
    "parametros",
    "executado_em",
}


@pytest.fixture
def configurar() -> Iterator[Callable[..., None]]:
    """Sobrescreve a configuração vista pelas rotas (`Depends(obter_configuracoes)`)
    com os parâmetros de teste (ou os `sobrescritas` pedidos) e o `token_admin`."""

    def _configurar(token_admin: str, **sobrescritas: object) -> None:
        config = obter_configuracoes().model_copy(
            update={**_PARAMETROS_DE_TESTE, **sobrescritas, "token_admin": token_admin}
        )
        app.dependency_overrides[obter_configuracoes] = lambda: config

    try:
        yield _configurar
    finally:
        app.dependency_overrides.pop(obter_configuracoes, None)


def _status_do_alerta(conexao: psycopg.Connection, alerta_id: int) -> str:
    return conexao.execute("SELECT status FROM alertas WHERE id = %s", (alerta_id,)).fetchone()[0]


# --- POST /validacao/executar ---


def test_executar_sem_token_quando_token_admin_vazio_devolve_200(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin="")

    resposta = cliente.post("/validacao/executar", params={"origem": "simulacao"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == _CHAVES_RESUMO
    assert corpo["origem"] == "simulacao"
    assert corpo["rotulo"] == "SIMULAÇÃO — dados sintéticos"  # G10: toda saída
    assert corpo["parametros"] == {"eps_metros": 8.0, "min_pontos": 2, "min_confirmacoes": 3}
    assert datetime.fromisoformat(corpo["executado_em"]).tzinfo is not None


def test_executar_com_token_configurado_sem_header_devolve_401(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN)
    alerta = inserir_alerta(conexao)

    resposta = cliente.post("/validacao/executar", params={"origem": "simulacao"})

    assert resposta.status_code == 401
    assert _status_do_alerta(conexao, alerta) == "bruto"  # o pipeline não rodou


def test_executar_com_token_errado_devolve_401(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN)
    alerta = inserir_alerta(conexao)

    resposta = cliente.post(
        "/validacao/executar",
        params={"origem": "simulacao"},
        headers={"X-Token-Admin": "token-errado"},
    )

    assert resposta.status_code == 401
    assert _status_do_alerta(conexao, alerta) == "bruto"


def test_executar_com_token_certo_devolve_200_e_roda_o_pipeline(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN)
    alerta = inserir_alerta(conexao)

    resposta = cliente.post(
        "/validacao/executar",
        params={"origem": "simulacao"},
        headers={"X-Token-Admin": _TOKEN},
    )

    assert resposta.status_code == 200
    assert resposta.json()["ruido_isolado"] == 1
    assert _status_do_alerta(conexao, alerta) == "ruido_isolado"


def test_executar_origem_padrao_e_real(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar(token_admin="")
    inserir_alerta(conexao, origem="simulacao")

    resposta = cliente.post("/validacao/executar")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["origem"] == "real"
    assert corpo["rotulo"] == "Dados reais de campo"
    assert corpo["alertas_processados"] == 0


def test_executar_origem_invalida_devolve_422(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin="")

    resposta = cliente.post("/validacao/executar", params={"origem": "rascunho"})

    assert resposta.status_code == 422


# --- GET /validacao/estatisticas ---


def test_estatisticas_devolve_o_formato_do_contrato(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN)  # estatísticas são públicas: nenhum header é enviado

    resposta = cliente.get("/validacao/estatisticas", params={"origem": "simulacao"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "origem",
        "rotulo",
        "alertas",
        "barreiras",
        "parametros",
        "executado_em",
        "gerado_em",
    }
    assert corpo["rotulo"] == "SIMULAÇÃO — dados sintéticos"
    assert corpo["alertas"]["descartados"] == {"fora_da_area": 0}
    # Origem nunca processada: não há parâmetros que expliquem as contagens (R14).
    assert corpo["parametros"] is None
    assert corpo["executado_em"] is None


def test_estatisticas_mostram_os_parametros_da_ultima_execucao_nao_a_config(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    """R14: o `.env` é recalibrado (aqui, a config sobrescrita) sem rodar o pipeline
    de novo; as estatísticas continuam mostrando os parâmetros que produziram os
    números, não os novos."""
    configurar(token_admin="")
    inserir_alerta(conexao)
    execucao = cliente.post("/validacao/executar", params={"origem": "simulacao"}).json()
    configurar(token_admin="", dbscan_eps_metros=20.0, min_confirmacoes=5)

    resposta = cliente.get("/validacao/estatisticas", params={"origem": "simulacao"})

    corpo = resposta.json()
    assert corpo["parametros"] == {"eps_metros": 8.0, "min_pontos": 2, "min_confirmacoes": 3}
    assert corpo["parametros"] == execucao["parametros"]
    assert corpo["executado_em"] == execucao["executado_em"]


def test_estatisticas_origem_padrao_e_real(cliente: TestClient) -> None:
    resposta = cliente.get("/validacao/estatisticas")

    assert resposta.status_code == 200
    assert resposta.json()["origem"] == "real"
    assert resposta.json()["rotulo"] == "Dados reais de campo"


def test_estatisticas_origem_invalida_devolve_422(cliente: TestClient) -> None:
    resposta = cliente.get("/validacao/estatisticas", params={"origem": "rascunho"})

    assert resposta.status_code == 422
