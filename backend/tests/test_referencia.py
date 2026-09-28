"""Testes dos endpoints de referência (D5): /saude, /tipos-barreira, /area-estudo."""

import psycopg
from fastapi.testclient import TestClient


def test_saude_responde_200(cliente: TestClient) -> None:
    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "banco": "ok"}


def test_tipos_barreira_devolve_os_quatro_codigos_do_seed(cliente: TestClient) -> None:
    resposta = cliente.get("/tipos-barreira")

    assert resposta.status_code == 200
    corpo = resposta.json()
    codigos = {item["codigo"] for item in corpo}
    assert codigos == {
        "calcada_irregular",
        "ausencia_rampa",
        "degrau",
        "obstaculo",
    }
    # Contrato: {"codigo", "nome", "descricao"}, ordenado por nome.
    assert all(set(item.keys()) == {"codigo", "nome", "descricao"} for item in corpo)
    nomes = [item["nome"] for item in corpo]
    assert nomes == sorted(nomes)


def test_tipo_inativo_some_da_lista(cliente: TestClient, conexao: psycopg.Connection) -> None:
    conexao.execute("UPDATE tipos_barreira SET ativo = false WHERE codigo = 'degrau'")

    resposta = cliente.get("/tipos-barreira")

    assert resposta.status_code == 200
    codigos = {item["codigo"] for item in resposta.json()}
    assert "degrau" not in codigos
    assert len(codigos) == 3


def test_area_estudo_devolve_feature_collection_com_um_polygon(cliente: TestClient) -> None:
    resposta = cliente.get("/area-estudo")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["type"] == "FeatureCollection"
    assert len(corpo["features"]) == 1

    feature = corpo["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Polygon"
    assert "nome" in feature["properties"]
