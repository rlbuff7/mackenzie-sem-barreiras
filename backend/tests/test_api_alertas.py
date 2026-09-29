"""Testes HTTP de `POST /alertas` (Contrato da API)."""

import json
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

_CORPO_DENTRO_DA_AREA = {
    "latitude": -23.5471938,
    "longitude": -46.6524631,
    "tipo": "degrau",
    "severidade": 2,
    "descricao": "texto opcional",
}

_CORPO_FORA_DA_AREA = {
    "latitude": -23.5614,
    "longitude": -46.6558,
    "tipo": "degrau",
    "severidade": 1,
}


def test_post_alertas_valido_dentro_da_area_devolve_201_bruto(cliente: TestClient) -> None:
    corpo = {**_CORPO_DENTRO_DA_AREA, "sessao_id": str(uuid4())}

    resposta = cliente.post("/alertas", content=json.dumps(corpo))

    assert resposta.status_code == 201
    corpo_resposta = resposta.json()
    assert corpo_resposta["status"] == "bruto"
    assert corpo_resposta["motivo_descarte"] is None
    assert corpo_resposta["mensagem"] == (
        "Alerta recebido. Ele será validado quando outras pessoas confirmarem."
    )
    assert isinstance(corpo_resposta["id"], int)


def test_post_alertas_valido_fora_da_area_devolve_201_descartado(cliente: TestClient) -> None:
    corpo = {**_CORPO_FORA_DA_AREA, "sessao_id": str(uuid4())}

    resposta = cliente.post("/alertas", content=json.dumps(corpo))

    assert resposta.status_code == 201
    corpo_resposta = resposta.json()
    assert corpo_resposta["status"] == "descartado"
    assert corpo_resposta["motivo_descarte"] == "fora_da_area"
    assert corpo_resposta["mensagem"] == "O ponto está fora da área de estudo do projeto."


def test_post_alertas_invalido_devolve_422_e_registra_rejeitado(
    cliente: TestClient, conexao: psycopg.Connection
) -> None:
    corpo = {**_CORPO_DENTRO_DA_AREA, "latitude": 200, "sessao_id": str(uuid4())}

    resposta = cliente.post("/alertas", content=json.dumps(corpo))

    assert resposta.status_code == 422
    corpo_resposta = resposta.json()
    assert corpo_resposta["mensagem"] == "Alerta inválido."
    assert {"campo": "latitude", "erro": "Deve ser menor ou igual a 90.0."} in (
        corpo_resposta["erros"]
    )
    total = conexao.execute("SELECT count(*) FROM alertas_rejeitados").fetchone()[0]
    assert total == 1


def test_post_alertas_json_malformado_devolve_422_e_registra_rejeitado(
    cliente: TestClient, conexao: psycopg.Connection
) -> None:
    resposta = cliente.post("/alertas", content=b"{isso nao e json valido")

    assert resposta.status_code == 422
    corpo_resposta = resposta.json()
    assert corpo_resposta["mensagem"] == "Alerta inválido."
    assert corpo_resposta["erros"] == [{"campo": "corpo", "erro": "JSON malformado."}]

    linha = conexao.execute(
        "SELECT payload, erros FROM alertas_rejeitados ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert "corpo_invalido" in linha[0]


def test_post_alertas_corpo_bem_formado_com_chave_corpo_invalido_e_validado_normalmente(
    cliente: TestClient,
) -> None:
    """`{"corpo_invalido": "x"}` é JSON bem formado — não é o corpo malformado do
    teste acima. Precisa ser validado normalmente contra `AlertaEntrada` (rejeitado
    por campos obrigatórios ausentes e por campo extra), nunca tratado como o atalho
    de "JSON malformado" (`campo="corpo"`). Prova que o atalho não colide com um
    payload de cliente que só coincida, por acaso ou de propósito, com o formato
    interno usado para JSON realmente inválido."""
    resposta = cliente.post("/alertas", content=json.dumps({"corpo_invalido": "x"}))

    assert resposta.status_code == 422
    corpo_resposta = resposta.json()
    campos = {erro["campo"] for erro in corpo_resposta["erros"]}
    assert "corpo" not in campos
    assert "corpo_invalido" in campos
    assert "latitude" in campos


# --- Estágio 1 com corpos-limite: sempre 422 + uma linha em alertas_rejeitados ---

_ERRO_JSON_MALFORMADO = {"campo": "corpo", "erro": "JSON malformado."}
_ERRO_CARACTERE_NAO_GRAVAVEL = {
    "campo": "corpo",
    "erro": (
        "O corpo tem um caractere que não pode ser gravado "
        "(U+0000 ou um substituto UTF-16 isolado)."
    ),
}
_ERRO_NAO_E_OBJETO = {"campo": "corpo", "erro": "Deve ser um objeto JSON (chave-valor)."}


def _corpo_valido_com_descricao(descricao_em_json: str) -> bytes:
    """Corpo válido em tudo, com a descrição escrita direto no texto JSON (para
    poder usar escapes como `\\u0000`, que `json.dumps` nunca produziria cru)."""
    return (
        '{"latitude": -23.5471938, "longitude": -46.6524631, "tipo": "degrau", '
        f'"sessao_id": "{uuid4()}", "descricao": "{descricao_em_json}"}}'
    ).encode()


@pytest.mark.parametrize(
    ("corpo", "erro_esperado"),
    [
        (b'{"a":"\xff"}', _ERRO_JSON_MALFORMADO),
        (b"NaN", _ERRO_JSON_MALFORMADO),
        (b'{"latitude": Infinity}', _ERRO_JSON_MALFORMADO),
        (b'{"latitude": -Infinity}', _ERRO_JSON_MALFORMADO),
        (b'{"latitude": 1e999}', _ERRO_JSON_MALFORMADO),
        (b'{"descricao": "a\x00b"}', _ERRO_JSON_MALFORMADO),
        (b"[" * 100_000 + b"]" * 100_000, _ERRO_JSON_MALFORMADO),
        (_corpo_valido_com_descricao("a\\u0000b"), _ERRO_CARACTERE_NAO_GRAVAVEL),
        (_corpo_valido_com_descricao("a\\ud800b"), _ERRO_CARACTERE_NAO_GRAVAVEL),
        (b'{"a\\u0000": 1}', _ERRO_CARACTERE_NAO_GRAVAVEL),
        (b"42", _ERRO_NAO_E_OBJETO),
        (b'"texto"', _ERRO_NAO_E_OBJETO),
        (b"[]", _ERRO_NAO_E_OBJETO),
        (b"null", _ERRO_NAO_E_OBJETO),
    ],
    ids=[
        "utf8_invalido",
        "nan",
        "infinity",
        "menos_infinity",
        "numero_que_estoura_o_float",
        "byte_nul_cru_numa_string",
        "aninhamento_profundo",
        "escape_nul_na_descricao",
        "substituto_isolado_na_descricao",
        "escape_nul_numa_chave",
        "numero",
        "texto",
        "lista_vazia",
        "null",
    ],
)
def test_post_alertas_corpo_limite_devolve_422_e_conta_o_rejeitado(
    cliente: TestClient, conexao: psycopg.Connection, corpo: bytes, erro_esperado: dict
) -> None:
    """Achado da revisão final: estes corpos davam 500 (ou 422 com `campo` vazio)
    e a rejeição não era contada no funil. Todos são reprovados no estágio 1."""
    rejeitados_antes = conexao.execute("SELECT count(*) FROM alertas_rejeitados").fetchone()[0]
    alertas_antes = conexao.execute("SELECT count(*) FROM alertas").fetchone()[0]

    resposta = cliente.post("/alertas", content=corpo)

    assert resposta.status_code == 422
    assert resposta.json() == {"mensagem": "Alerta inválido.", "erros": [erro_esperado]}
    rejeitados = conexao.execute("SELECT count(*) FROM alertas_rejeitados").fetchone()[0]
    assert rejeitados == rejeitados_antes + 1
    assert conexao.execute("SELECT count(*) FROM alertas").fetchone()[0] == alertas_antes
