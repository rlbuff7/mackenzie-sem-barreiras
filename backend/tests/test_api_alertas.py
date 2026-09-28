"""Testes HTTP de `POST /alertas` (Contrato da API)."""

import json
from uuid import uuid4

import psycopg
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
    assert any(erro["campo"] == "latitude" for erro in corpo_resposta["erros"])
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
