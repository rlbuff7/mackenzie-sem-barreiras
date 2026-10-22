"""Testes HTTP das fotos dos pontos de controle (contrato de 22/10/2026).

`POST /medicoes/fotos` (corpo bruto image/jpeg, código da equipe),
`GET /medicoes/fotos/resumo` e `GET /medicoes/fotos/{id}` (token de admin).
Batem no PostGIS real, como os testes de `/medicoes`.
"""

import base64
import hashlib
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import obter_configuracoes
from app.main import app

_CODIGO = "codigo-da-equipe-de-teste"
_TOKEN_ADMIN = "token-admin-de-teste"
_CABECALHOS = {"X-Codigo-Equipe": _CODIGO, "Content-Type": "image/jpeg"}
_ADMIN = {"X-Token-Admin": _TOKEN_ADMIN}

# JPEG 1x1 válido, sem metadados (sem APP1/Exif).
_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////"
    "////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)
# Mesmo JPEG com um segmento APP1 "Exif" logo depois do SOI.
_JPEG_COM_EXIF = _JPEG[:2] + b"\xff\xe1\x00\x10Exif\x00\x00MM\x00*\x00\x00\x00\x08" + _JPEG[2:]


@pytest.fixture
def configurar() -> Iterator[Callable[..., None]]:
    def _configurar(**sobrescritas: object) -> None:
        padrao: dict[str, object] = {
            "medicao_codigo_equipe": _CODIGO,
            "token_admin": _TOKEN_ADMIN,
        }
        config = obter_configuracoes().model_copy(update={**padrao, **sobrescritas})
        app.dependency_overrides[obter_configuracoes] = lambda: config

    try:
        yield _configurar
    finally:
        app.dependency_overrides.pop(obter_configuracoes, None)


def _parametros(**sobrescritas: Any) -> dict[str, Any]:
    """Query válida; `None` remove o parâmetro."""
    parametros: dict[str, Any] = {
        "id_cliente": str(uuid4()),
        "ponto": 3,
        "aparelho": "Galaxy A54",
        "tirada_em": "2026-10-22T10:30:00-03:00",
        "largura_px": 1,
        "altura_px": 1,
    }
    parametros.update(sobrescritas)
    return {chave: valor for chave, valor in parametros.items() if valor is not None}


def _enviar(
    cliente: TestClient,
    corpo: bytes = _JPEG,
    parametros: dict[str, Any] | None = None,
    cabecalhos: dict[str, str] | None = None,
) -> Any:
    return cliente.post(
        "/medicoes/fotos",
        params=_parametros() if parametros is None else parametros,
        content=corpo,
        headers=_CABECALHOS if cabecalhos is None else cabecalhos,
    )


def _contar(conexao: psycopg.Connection) -> int:
    return conexao.execute("SELECT count(*) FROM fotos_pontos").fetchone()[0]


def test_foto_valida_e_gravada(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    parametros = _parametros(observacao="  marca no chão  ")

    resposta = _enviar(cliente, parametros=parametros)

    assert resposta.status_code == 200
    assert resposta.json() == {"gravada": True}
    linha = conexao.execute(
        """SELECT ponto, aparelho, tamanho_bytes, largura_px, altura_px, sha256, observacao,
                  bytes_conteudo.c = %s
           FROM fotos_pontos, LATERAL (SELECT conteudo AS c) bytes_conteudo
           WHERE id_cliente = %s""",
        (_JPEG, parametros["id_cliente"]),
    ).fetchone()
    assert linha == (
        3,
        "Galaxy A54",
        len(_JPEG),
        1,
        1,
        hashlib.sha256(_JPEG).hexdigest(),
        "marca no chão",
        True,
    )


def test_reenvio_nao_duplica(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    parametros = _parametros()

    primeira = _enviar(cliente, parametros=parametros)
    segunda = _enviar(cliente, parametros=parametros)

    assert primeira.json() == {"gravada": True}
    assert segunda.status_code == 200
    assert segunda.json() == {"gravada": False}
    assert _contar(conexao) == 1


def test_sem_codigo_da_equipe_e_401(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    assert _enviar(cliente, cabecalhos={"Content-Type": "image/jpeg"}).status_code == 401
    errado = {**_CABECALHOS, "X-Codigo-Equipe": "errado"}
    assert _enviar(cliente, cabecalhos=errado).status_code == 401
    assert _contar(conexao) == 0


def test_codigo_nao_configurado_e_503(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar(medicao_codigo_equipe="")
    assert _enviar(cliente).status_code == 503
    assert _contar(conexao) == 0


def test_corpo_maior_que_1_mib_e_413(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    grande = b"\xff\xd8\xff" + b"\x00" * 1_048_576
    resposta = _enviar(cliente, corpo=grande)
    assert resposta.status_code == 413
    assert _contar(conexao) == 0


def test_corpo_de_exatamente_1_mib_passa(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    limite = b"\xff\xd8\xff" + b"\x00" * (1_048_576 - 3)
    assert _enviar(cliente, corpo=limite).status_code == 200


def test_corpo_vazio_e_413(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    assert _enviar(cliente, corpo=b"").status_code == 413
    assert _contar(conexao) == 0


def test_outro_content_type_e_415(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    cabecalhos = {**_CABECALHOS, "Content-Type": "image/png"}
    assert _enviar(cliente, cabecalhos=cabecalhos).status_code == 415
    assert _contar(conexao) == 0


def test_bytes_que_nao_sao_jpeg_e_415(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    assert _enviar(cliente, corpo=b"\x89PNG\r\n\x1a\n" + b"0" * 20).status_code == 415
    assert _contar(conexao) == 0


def test_foto_com_exif_e_422(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    resposta = _enviar(cliente, corpo=_JPEG_COM_EXIF)
    assert resposta.status_code == 422
    assert "EXIF" in resposta.json()["mensagem"]
    assert _contar(conexao) == 0


@pytest.mark.parametrize(
    ("alteracao", "campo"),
    [
        ({"ponto": 13}, "ponto"),
        ({"ponto": 0}, "ponto"),
        ({"ponto": "abc"}, "ponto"),
        ({"aparelho": ""}, "aparelho"),
        ({"aparelho": "x" * 81}, "aparelho"),
        ({"id_cliente": "nao-e-uuid"}, "id_cliente"),
        ({"tirada_em": "ontem"}, "tirada_em"),
        ({"tirada_em": "2026-10-22T10:30:00"}, "tirada_em"),
        ({"largura_px": 2049}, "largura_px"),
        ({"altura_px": 0}, "altura_px"),
        ({"observacao": "x" * 501}, "observacao"),
        ({"inventado": "1"}, "inventado"),
        ({"ponto": None}, "ponto"),
        ({"id_cliente": None}, "id_cliente"),
    ],
)
def test_parametros_invalidos_sao_422(
    cliente: TestClient,
    conexao: psycopg.Connection,
    configurar: Callable[..., None],
    alteracao: dict[str, Any],
    campo: str,
) -> None:
    configurar()
    resposta = _enviar(cliente, parametros=_parametros(**alteracao))
    assert resposta.status_code == 422
    assert campo in {erro["campo"] for erro in resposta.json()["erros"]}
    assert _contar(conexao) == 0


def test_resumo_agrupa_por_ponto_e_aparelho_sem_bytes(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()
    _enviar(cliente, parametros=_parametros(ponto=3, aparelho="Galaxy A54"))
    _enviar(cliente, parametros=_parametros(ponto=3, aparelho="Galaxy A54"))
    _enviar(cliente, parametros=_parametros(ponto=11, aparelho="Moto G"))

    resposta = cliente.get("/medicoes/fotos/resumo", headers=_ADMIN)

    assert resposta.status_code == 200
    itens = {(i["ponto"], i["aparelho"]): i for i in resposta.json()}
    assert itens[(3, "Galaxy A54")]["fotos"] == 2
    assert itens[(3, "Galaxy A54")]["ponto_codigo"] == "P03"
    assert itens[(11, "Moto G")]["ponto_codigo"] == "P11"
    assert set(itens[(3, "Galaxy A54")]) == {
        "ponto_codigo",
        "ponto",
        "aparelho",
        "fotos",
        "ultima_em",
    }


def test_resumo_e_download_exigem_token_admin(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()
    assert cliente.get("/medicoes/fotos/resumo").status_code == 401
    assert cliente.get("/medicoes/fotos/1").status_code == 401
    errado = {"X-Token-Admin": "errado"}
    assert cliente.get("/medicoes/fotos/resumo", headers=errado).status_code == 401


def test_download_devolve_o_jpeg(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    parametros = _parametros()
    _enviar(cliente, parametros=parametros)
    foto_id = conexao.execute(
        "SELECT id FROM fotos_pontos WHERE id_cliente = %s", (parametros["id_cliente"],)
    ).fetchone()[0]

    resposta = cliente.get(f"/medicoes/fotos/{foto_id}", headers=_ADMIN)

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "image/jpeg"
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.content == _JPEG


def test_download_de_foto_inexistente_e_404(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()
    assert cliente.get("/medicoes/fotos/999999999", headers=_ADMIN).status_code == 404
