"""Testes HTTP de `GET /barreiras` (Contrato da API)."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.routers.barreiras import buscar_barreiras_no_bbox, interpretar_bbox
from app.validacao.estatisticas import ROTULOS_POR_ORIGEM

_BBOX_CAMPUS = "-46.66,-23.55,-46.64,-23.54"


def _inserir_barreira(
    conexao: psycopg.Connection,
    *,
    longitude: float,
    latitude: float,
    tipo: str = "degrau",
    status: str = "pendente",
    confirmacoes: int = 3,
    origem: str = "real",
) -> int:
    tipo_id = conexao.execute(
        "SELECT id FROM tipos_barreira WHERE codigo = %s", (tipo,)
    ).fetchone()[0]
    linha = conexao.execute(
        """
        INSERT INTO barreiras (geom, tipo_id, confirmacoes, status, origem)
        VALUES (ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), %(tipo_id)s,
                %(confirmacoes)s, %(status)s, %(origem)s)
        RETURNING id
        """,
        {
            "lon": longitude,
            "lat": latitude,
            "tipo_id": tipo_id,
            "confirmacoes": confirmacoes,
            "status": status,
            "origem": origem,
        },
    ).fetchone()
    return linha[0]


def test_bbox_ausente_devolve_422_em_portugues(cliente: TestClient) -> None:
    resposta = cliente.get("/barreiras")

    assert resposta.status_code == 422
    assert resposta.json() == {
        "mensagem": "Requisição inválida.",
        "erros": [{"campo": "bbox", "erro": "Campo obrigatório."}],
    }


def test_bbox_malformado_devolve_422_no_mesmo_formato(cliente: TestClient) -> None:
    resposta = cliente.get("/barreiras", params={"bbox": "nao,e,um,bbox"})

    assert resposta.status_code == 422
    assert resposta.json() == {
        "mensagem": "Requisição inválida.",
        "erros": [{"campo": "bbox", "erro": "bbox deve conter apenas números."}],
    }


def test_status_e_origem_invalidos_devolvem_422_em_portugues(cliente: TestClient) -> None:
    resposta = cliente.get(
        "/barreiras", params={"bbox": _BBOX_CAMPUS, "status": "xyz", "origem": "abc"}
    )

    assert resposta.status_code == 422
    assert resposta.json() == {
        "mensagem": "Requisição inválida.",
        "erros": [
            {"campo": "status", "erro": "Deve ser um destes valores: 'pendente' ou 'confirmada'."},
            {"campo": "origem", "erro": "Deve ser um destes valores: 'real' ou 'simulacao'."},
        ],
    }


def test_bbox_invertido_devolve_422(cliente: TestClient) -> None:
    resposta = cliente.get("/barreiras", params={"bbox": "-46.64,-23.54,-46.66,-23.55"})

    assert resposta.status_code == 422


def test_bbox_fora_da_faixa_devolve_422(cliente: TestClient) -> None:
    resposta = cliente.get("/barreiras", params={"bbox": "-200,-23.55,-46.64,-23.54"})

    assert resposta.status_code == 422


def test_apenas_barreiras_dentro_do_bbox(cliente: TestClient, conexao: psycopg.Connection) -> None:
    dentro = _inserir_barreira(conexao, longitude=-46.6524631, latitude=-23.5471938)
    _inserir_barreira(conexao, longitude=-46.50, latitude=-23.40)

    resposta = cliente.get("/barreiras", params={"bbox": _BBOX_CAMPUS})

    assert resposta.status_code == 200
    corpo = resposta.json()
    ids = {feature["properties"]["id"] for feature in corpo["features"]}
    assert ids == {dentro}


def test_filtro_status(cliente: TestClient, conexao: psycopg.Connection) -> None:
    pendente = _inserir_barreira(
        conexao, longitude=-46.6524631, latitude=-23.5471938, status="pendente"
    )
    confirmada = _inserir_barreira(
        conexao, longitude=-46.6520, latitude=-23.5470, status="confirmada"
    )

    resposta = cliente.get("/barreiras", params={"bbox": _BBOX_CAMPUS, "status": "confirmada"})

    ids = {feature["properties"]["id"] for feature in resposta.json()["features"]}
    assert ids == {confirmada}
    assert pendente not in ids


def test_origem_padrao_real_nao_devolve_simulacao(
    cliente: TestClient, conexao: psycopg.Connection
) -> None:
    real = _inserir_barreira(conexao, longitude=-46.6524631, latitude=-23.5471938, origem="real")
    _inserir_barreira(conexao, longitude=-46.6520, latitude=-23.5470, origem="simulacao")

    resposta = cliente.get("/barreiras", params={"bbox": _BBOX_CAMPUS})

    ids = {feature["properties"]["id"] for feature in resposta.json()["features"]}
    assert ids == {real}


def test_formato_geojson_da_feature(cliente: TestClient, conexao: psycopg.Connection) -> None:
    id_barreira = _inserir_barreira(conexao, longitude=-46.6524631, latitude=-23.5471938)

    resposta = cliente.get("/barreiras", params={"bbox": _BBOX_CAMPUS})

    corpo = resposta.json()
    assert corpo["type"] == "FeatureCollection"
    feature = next(f for f in corpo["features"] if f["properties"]["id"] == id_barreira)
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert set(feature["properties"].keys()) == {
        "id",
        "tipo",
        "tipo_nome",
        "confirmacoes",
        "status",
        "atualizado_em",
    }
    assert feature["properties"]["tipo"] == "degrau"


def test_colecao_traz_o_rotulo_da_origem(cliente: TestClient) -> None:
    """G10: a coleção diz de onde vêm as barreiras, com o mesmo texto das
    estatísticas; um GeoJSON pode ter membros extras no topo (RFC 7946 §6.1)."""
    real = cliente.get("/barreiras", params={"bbox": _BBOX_CAMPUS})
    simulacao = cliente.get("/barreiras", params={"bbox": _BBOX_CAMPUS, "origem": "simulacao"})

    assert real.json()["rotulo"] == ROTULOS_POR_ORIGEM["real"]
    assert simulacao.json()["rotulo"] == ROTULOS_POR_ORIGEM["simulacao"]
    assert simulacao.json()["rotulo"].startswith("SIMULAÇÃO")


# --- funções do router, sem HTTP ---


def test_interpretar_bbox_devolve_os_quatro_floats() -> None:
    assert interpretar_bbox("-46.66,-23.55,-46.64,-23.54") == (-46.66, -23.55, -46.64, -23.54)


@pytest.mark.parametrize(
    ("texto", "trecho_da_mensagem"),
    [
        ("1,2,3", "4 valores"),
        ("1,2,3,4,5", "4 valores"),
        ("", "4 valores"),
        ("a,b,c,d", "apenas números"),
        ("-181,0,0,1", "longitude"),
        ("0,0,181,1", "longitude"),
        ("0,-91,1,0", "latitude"),
        ("0,0,1,91", "latitude"),
        ("1,0,0,1", "mínimo deve ser menor"),
        ("0,1,1,1", "mínimo deve ser menor"),
    ],
)
def test_interpretar_bbox_rejeita_com_mensagem_em_portugues(
    texto: str, trecho_da_mensagem: str
) -> None:
    with pytest.raises(ValueError, match=trecho_da_mensagem):
        interpretar_bbox(texto)


def _buscar(conexao: psycopg.Connection, bbox: tuple[float, float, float, float], **filtros):
    parametros = {"status": None, "origem": "real", "limite": 100, "srid_armazenamento": 4326}
    return buscar_barreiras_no_bbox(conexao, bbox, **{**parametros, **filtros})


def test_buscar_barreiras_no_bbox_filtra_por_bbox_origem_e_status(
    conexao: psycopg.Connection,
) -> None:
    dentro = _inserir_barreira(conexao, longitude=-46.652, latitude=-23.547, status="confirmada")
    pendente = _inserir_barreira(conexao, longitude=-46.653, latitude=-23.547, status="pendente")
    _inserir_barreira(conexao, longitude=-46.50, latitude=-23.547)  # fora do bbox
    _inserir_barreira(conexao, longitude=-46.652, latitude=-23.547, origem="simulacao")
    bbox = (-46.66, -23.55, -46.64, -23.54)

    todas = _buscar(conexao, bbox)
    confirmadas = _buscar(conexao, bbox, status="confirmada")
    simuladas = _buscar(conexao, bbox, origem="simulacao")

    assert [f["properties"]["id"] for f in todas["features"]] == [dentro, pendente]
    assert [f["properties"]["id"] for f in confirmadas["features"]] == [dentro]
    assert len(simuladas["features"]) == 1
    assert todas["rotulo"] == ROTULOS_POR_ORIGEM["real"]
    assert simuladas["rotulo"] == ROTULOS_POR_ORIGEM["simulacao"]
    assert todas["features"][0]["geometry"]["type"] == "Point"


def test_buscar_barreiras_no_bbox_respeita_o_limite(conexao: psycopg.Connection) -> None:
    for deslocamento in range(3):
        _inserir_barreira(conexao, longitude=-46.652 + deslocamento / 1000, latitude=-23.547)

    resultado = _buscar(conexao, (-46.66, -23.55, -46.64, -23.54), limite=2)

    assert len(resultado["features"]) == 2
