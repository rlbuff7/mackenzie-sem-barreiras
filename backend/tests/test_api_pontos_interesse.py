"""GET /pontos-interesse: bbox obrigatório, filtro por tipo, limite, rótulo e tem_no."""

import pytest

from app.config import Configuracoes, obter_configuracoes
from app.main import app

# Região longe do campus (o banco de teste já tem o seed do campus): só os pontos
# inseridos aqui aparecem. Ids altos para nunca colidir com o seed.
LON, LAT = -40.0, -10.0
BBOX = f"{LON - 0.01},{LAT - 0.01},{LON + 0.01},{LAT + 0.01}"


def _ponto(conexao, id_, tipo, nome, dx=0.0, fonte="imagem", por=None, com_no=False):
    conexao.execute(
        """INSERT INTO pontos_interesse
               (id, geom, tipo, nome, descricao, fonte_verificacao, mapeado_por)
           VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, 'desc', %s, %s)""",
        (id_, LON + dx, LAT, tipo, nome, fonte, por),
    )
    if com_no:
        conexao.execute(
            "INSERT INTO nos (id, geom, ponto_interesse_id) "
            "VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)",
            (id_, LON + dx, LAT, id_),
        )


@pytest.fixture
def pontos(conexao):
    _ponto(conexao, 900001, "entrada", "Entrada B", com_no=True)
    _ponto(
        conexao,
        900002,
        "entrada",
        "Entrada A",
        dx=0.001,
        fonte="provisorio",
        por="OpenStreetMap (contribuidores)",
    )
    _ponto(conexao, 900003, "escada", "Escada X", dx=0.002)
    _ponto(conexao, 900004, "predio", "Longe", dx=5.0)  # fora do bbox


def test_sucesso_devolve_featurecollection_ordenada_por_nome(cliente, pontos):
    r = cliente.get("/pontos-interesse", params={"bbox": BBOX})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection"
    assert [f["properties"]["nome"] for f in corpo["features"]] == [
        "Entrada A",
        "Entrada B",
        "Escada X",
    ]
    assert "Longe" not in str(corpo)


def test_propriedades_e_geometria_lon_lat(cliente, pontos):
    f = cliente.get("/pontos-interesse", params={"bbox": BBOX}).json()["features"][1]
    assert set(f["properties"]) == {
        "id",
        "tipo",
        "nome",
        "descricao",
        "acessivel",
        "fonte_verificacao",
        "tem_no",
    }
    assert f["properties"]["id"] == 900001 and f["properties"]["tem_no"] is True
    assert f["geometry"] == {"type": "Point", "coordinates": [LON, LAT]}


def test_tem_no_falso_para_ponto_sem_no(cliente, pontos):
    por_nome = {
        f["properties"]["nome"]: f["properties"]
        for f in cliente.get("/pontos-interesse", params={"bbox": BBOX}).json()["features"]
    }
    assert por_nome["Escada X"]["tem_no"] is False


def test_rotulo_provisorio_e_atribuicao_osm(cliente, pontos):
    corpo = cliente.get("/pontos-interesse", params={"bbox": BBOX}).json()
    assert corpo["rotulo"].startswith("PROVISÓRIO")
    assert "OpenStreetMap" in corpo["atribuicao"]


def test_filtro_por_tipo(cliente, pontos):
    corpo = cliente.get("/pontos-interesse", params={"bbox": BBOX, "tipo": "escada,predio"}).json()
    assert [f["properties"]["nome"] for f in corpo["features"]] == ["Escada X"]


def test_tipo_invalido_da_422_com_campo_tipo(cliente, pontos):
    r = cliente.get("/pontos-interesse", params={"bbox": BBOX, "tipo": "castelo"})
    assert r.status_code == 422
    assert r.json()["erros"][0]["campo"] == "tipo"


@pytest.mark.parametrize("bbox", ["1,2,3", "a,b,c,d", "5,5,1,1", "-200,0,0,1"])
def test_bbox_malformado_da_422(cliente, bbox):
    r = cliente.get("/pontos-interesse", params={"bbox": bbox})
    assert r.status_code == 422
    assert r.json()["erros"][0]["campo"] == "bbox"


def test_bbox_ausente_da_422(cliente):
    r = cliente.get("/pontos-interesse")
    assert r.status_code == 422
    assert r.json()["erros"][0]["campo"] == "bbox"


def test_limite_de_pontos_por_consulta(cliente, pontos):
    app.dependency_overrides[obter_configuracoes] = lambda: Configuracoes(
        limite_pontos_interesse_por_consulta=2
    )
    try:
        corpo = cliente.get("/pontos-interesse", params={"bbox": BBOX}).json()
    finally:
        del app.dependency_overrides[obter_configuracoes]
    assert len(corpo["features"]) == 2


def test_bbox_do_frontend_cobre_todos_os_pontos_do_seed(cliente):
    """O frontend pede um bbox amplo em torno do campus: todo ponto do seed tem de aparecer."""
    total = cliente.get("/pontos-interesse", params={"bbox": "-46.6622,-23.5575,-46.6422,-23.5375"})
    assert total.status_code == 200
    ids_amplo = {f["properties"]["id"] for f in total.json()["features"]}
    todos = {
        f["properties"]["id"]
        for f in cliente.get("/pontos-interesse", params={"bbox": "-180,-90,180,90"}).json()[
            "features"
        ]
        if f["properties"]["id"] < 900000
    }
    assert todos and todos <= ids_amplo
