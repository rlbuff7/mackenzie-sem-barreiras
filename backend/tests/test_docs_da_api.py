"""`EXPOR_DOCS`: a documentação interativa some (404) quando desligada (Task 8)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Configuracoes
from app.main import criar_app

_CAMINHOS_DE_DOCUMENTACAO = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("caminho", _CAMINHOS_DE_DOCUMENTACAO)
def test_documentacao_existe_com_expor_docs_ligado(caminho: str) -> None:
    resposta = TestClient(criar_app(expor_docs=True)).get(caminho)

    assert resposta.status_code == 200


@pytest.mark.parametrize("caminho", _CAMINHOS_DE_DOCUMENTACAO)
def test_documentacao_nao_existe_com_expor_docs_desligado(caminho: str) -> None:
    resposta = TestClient(criar_app(expor_docs=False)).get(caminho)

    assert resposta.status_code == 404


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("1", True),
    ],
)
def test_expor_docs_do_ambiente_aceita_booleano_sem_diferenciar_maiusculas(
    monkeypatch: pytest.MonkeyPatch, valor: str, esperado: bool
) -> None:
    monkeypatch.setenv("EXPOR_DOCS", valor)

    assert Configuracoes(_env_file=None, **_ambiente_minimo()).expor_docs is esperado


def test_expor_docs_liga_por_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXPOR_DOCS", raising=False)

    assert Configuracoes(_env_file=None, **_ambiente_minimo()).expor_docs is True


def test_expor_docs_invalido_falha_ao_ler_a_configuracao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPOR_DOCS", "talvez")

    with pytest.raises(ValidationError) as erro:
        Configuracoes(_env_file=None, **_ambiente_minimo())

    assert [e["loc"] for e in erro.value.errors()] == [("expor_docs",)]


def _ambiente_minimo() -> dict:
    return {
        "postgres_db": "x",
        "postgres_user": "x",
        "postgres_password": "x",
        "dbscan_eps_metros": 8,
        "dbscan_min_points": 2,
        "min_confirmacoes": 3,
        "srid_armazenamento": 4326,
        "srid_calculo": 31983,
    }
