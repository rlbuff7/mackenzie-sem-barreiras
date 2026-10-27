"""POST /rotas: desvio por rampa, cadeirante nunca recebe escada, mão única, sem rota,
422, 404, 413, rótulo provisório e ordem da geometria.

Os grafos de teste entram DENTRO da transação da fixture `conexao` (desfeita no fim),
com ids a partir de 900000 e longe do campus (lon -40, lat -10), então não se misturam
com o seed real: o Dijkstra nunca encontra um nó do outro grafo.
"""

import itertools

import pytest

from app.config import Configuracoes, obter_configuracoes
from app.main import app

LON0, LAT0 = -40.0, -10.0
_ids = itertools.count(900001)


class Grafo:
    """Montador de grafo de teste. Cada nó fica numa posição própria (em grau)."""

    def __init__(self, conexao, deslocamento=0.0):
        self.c = conexao
        self.dx = deslocamento  # separa grafos do mesmo teste
        self.nos = {}

    def no(self, nome, x, y=0.0, ponto=None, tipo="entrada", fonte="conferido_a_pe"):
        id_ = next(_ids)
        lon, lat = LON0 + self.dx + x * 1e-4, LAT0 + y * 1e-4
        ponto_id = None
        if ponto:
            ponto_id = next(_ids)
            self.c.execute(
                """INSERT INTO pontos_interesse (id, geom, tipo, nome, fonte_verificacao)
                   VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s)""",
                (ponto_id, lon, lat, tipo, ponto, fonte),
            )
        self.c.execute(
            "INSERT INTO nos (id, geom, ponto_interesse_id) "
            "VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)",
            (id_, lon, lat, ponto_id),
        )
        self.nos[nome] = (id_, ponto_id, lon, lat)
        return id_

    def aresta(
        self,
        de,
        para,
        metros,
        tipo="calcada",
        acessivel=True,
        fonte="conferido_a_pe",
        mao_unica=False,
        guardar_invertida=False,
        por=None,
    ):
        o, d = self.nos[de], self.nos[para]
        (o, d) = (d, o) if guardar_invertida else (o, d)
        id_ = next(_ids)
        self.c.execute(
            """INSERT INTO arestas (id, geom, origem_id, destino_id, comprimento_m, tipo,
                   acessivel_cadeirante, custo, custo_inverso, fonte_verificacao, mapeado_por)
               VALUES (%s, ST_SetSRID(ST_MakeLine(
                           ST_MakePoint(%s, %s), ST_MakePoint(%s, %s)), 4326),
                       %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                id_,
                o[2],
                o[3],
                d[2],
                d[3],
                o[0],
                d[0],
                metros,
                tipo,
                acessivel,
                metros,
                -1 if mao_unica else metros,
                fonte,
                por,
            ),
        )
        return id_

    def ponto(self, nome):
        return self.nos[nome][1]


def _rota(cliente, g, de, para, perfil=None):
    corpo = {"origem_id": g.ponto(de), "destino_id": g.ponto(para)}
    if perfil:
        corpo["perfil"] = perfil
    return cliente.post("/rotas", json=corpo)


@pytest.fixture
def losango(conexao):
    """A -> D por dois caminhos: curto com escada (A-B-D) e longo com rampa (A-C-D)."""
    g = Grafo(conexao)
    for nome, x, y in (("A", 0, 0), ("B", 10, 10), ("C", 10, -10), ("D", 20, 0)):
        g.no(nome, x, y, ponto=f"Entrada {nome}")
    g.ab = g.aresta("A", "B", 20)
    g.bd = g.aresta("B", "D", 20, tipo="escada", acessivel=False)
    g.ac = g.aresta("A", "C", 30)
    g.cd = g.aresta("C", "D", 30, tipo="rampa", acessivel=True)
    return g


def _ids_trechos(corpo):
    return [t["aresta_id"] for t in corpo["trechos"]]


def test_sem_restricao_pega_o_desvio_quando_a_escada_custa_mais(cliente, losango):
    r = _rota(cliente, losango, "A", "D")
    assert r.status_code == 200
    corpo = r.json()
    assert _ids_trechos(corpo) == [losango.ac, losango.cd]
    assert corpo["distancia_m"] == 60.0 and corpo["distancia_m"] > 40.0  # 40 m seria pela escada
    assert corpo["acessivel_cadeirante"] is True


def test_sem_restricao_pega_a_escada_quando_ela_compensa(cliente, conexao):
    g = Grafo(conexao)
    for nome, x in (("A", 0), ("B", 10), ("C", 20)):
        g.no(nome, x, ponto=f"Entrada {nome}")
    g.no("L", 10, 50)
    ab = g.aresta("A", "B", 10)
    bc = g.aresta("B", "C", 5, tipo="escada", acessivel=False)
    g.aresta("A", "L", 100)
    g.aresta("L", "C", 100)
    corpo = _rota(cliente, g, "A", "C").json()
    assert _ids_trechos(corpo) == [ab, bc]
    assert any("escada" in a for a in corpo["avisos"])
    assert corpo["acessivel_cadeirante"] is False


def test_cadeirante_nunca_recebe_escada_se_ha_alternativa(cliente, losango):
    corpo = _rota(cliente, losango, "A", "D", "cadeirante").json()
    assert _ids_trechos(corpo) == [losango.ac, losango.cd]
    assert all(t["tipo"] != "escada" for t in corpo["trechos"])


def test_cadeirante_com_escada_curtissima_ainda_evita_a_escada(cliente, conexao):
    """Mesmo com a escada MUITO mais curta, o cadeirante não a recebe (não é só penalidade)."""
    g = Grafo(conexao)
    for nome, x in (("A", 0), ("B", 10), ("C", 20)):
        g.no(nome, x, ponto=f"Entrada {nome}")
    g.aresta("A", "B", 1, tipo="escada", acessivel=False)
    g.aresta("B", "C", 1)
    g.aresta("A", "C", 5000)
    corpo = _rota(cliente, g, "A", "C", "cadeirante").json()
    assert [t["tipo"] for t in corpo["trechos"]] == ["calcada"]
    assert corpo["distancia_m"] == 5000.0


def test_so_escada_sem_restricao_200_com_aviso_e_cadeirante_404_sem_rota(cliente, conexao):
    g = Grafo(conexao)
    g.no("E", 0, ponto="Entrada E")
    g.no("F", 10)
    g.no("G", 20, ponto="Entrada G")
    g.aresta("E", "F", 30)
    g.aresta("F", "G", 12, tipo="escada", acessivel=False)
    livre = _rota(cliente, g, "E", "G")
    assert livre.status_code == 200
    assert any("escada" in a for a in livre.json()["avisos"])
    assert any(t["tipo"] == "escada" for t in livre.json()["trechos"])
    cad = _rota(cliente, g, "E", "G", "cadeirante")
    assert cad.status_code == 404
    assert cad.json()["codigo"] == "sem_rota"
    assert "trechos" not in cad.json()


def test_cadeirante_nao_usa_trecho_marcado_como_inacessivel(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A")
    g.no("B", 10, ponto="Entrada B")
    g.aresta("A", "B", 10, tipo="calcada", acessivel=False)
    assert _rota(cliente, g, "A", "B").status_code == 200
    assert _rota(cliente, g, "A", "B", "cadeirante").status_code == 404


def test_geometria_vem_em_ordem_mesmo_atravessando_aresta_guardada_ao_contrario(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A")
    g.no("B", 10)
    g.no("C", 20, ponto="Entrada C")
    g.aresta("A", "B", 10, guardar_invertida=True)  # gravada de B para A
    g.aresta("B", "C", 10)
    corpo = _rota(cliente, g, "A", "C").json()
    coords = corpo["geometria"]["coordinates"]
    assert coords[0] == [g.nos["A"][2], g.nos["A"][3]]
    assert coords[-1] == [g.nos["C"][2], g.nos["C"][3]]
    assert [c[0] for c in coords] == sorted(
        c[0] for c in coords
    )  # lon crescente: sem pedaço invertido
    assert len(coords) == 3  # o vértice de junção não se repete


def test_geometria_e_lon_lat(cliente, losango):
    primeiro = _rota(cliente, losango, "A", "D").json()["geometria"]["coordinates"][0]
    assert primeiro == [LON0, LAT0]


def test_mao_unica_nao_volta(cliente, conexao):
    g = Grafo(conexao)
    g.no("H", 0, ponto="Entrada H")
    g.no("I", 10, ponto="Entrada I")
    g.aresta("H", "I", 10, mao_unica=True)
    assert _rota(cliente, g, "H", "I").status_code == 200
    volta = _rota(cliente, g, "I", "H")
    assert volta.status_code == 404 and volta.json()["codigo"] == "sem_rota"


def test_sem_caminho_devolve_404_sem_rota(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A")
    g.no("B", 10, ponto="Entrada B")
    r = _rota(cliente, g, "A", "B")
    assert r.status_code == 404
    assert r.json() == {
        "mensagem": "Não há caminho mapeado entre esses dois pontos.",
        "codigo": "sem_rota",
    }


def test_destino_que_nao_e_entrada_da_422(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A")
    g.no("P", 10, ponto="Portão P", tipo="portao")
    g.aresta("A", "P", 10)
    r = _rota(cliente, g, "A", "P")
    assert r.status_code == 422
    assert r.json()["erros"][0] == {"campo": "destino_id", "erro": "Escolha uma entrada de prédio."}
    assert _rota(cliente, g, "P", "A").status_code == 200  # portão pode ser origem


def test_ponto_sem_no_da_422_no_campo_certo(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A")
    solto = next(_ids)
    conexao.execute(
        "INSERT INTO pontos_interesse (id, geom, tipo, nome) "
        "VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), 'entrada', 'Solto')",
        (solto, LON0, LAT0),
    )
    r = cliente.post("/rotas", json={"origem_id": g.ponto("A"), "destino_id": solto})
    assert r.status_code == 422 and r.json()["erros"][0]["campo"] == "destino_id"
    r = cliente.post("/rotas", json={"origem_id": solto, "destino_id": g.ponto("A")})
    assert r.status_code == 422 and r.json()["erros"][0]["campo"] == "origem_id"


def test_ponto_inexistente_da_404(cliente, losango):
    r = cliente.post("/rotas", json={"origem_id": losango.ponto("A"), "destino_id": 999999999})
    assert r.status_code == 404 and r.json()["campo"] == "destino_id"
    r = cliente.post("/rotas", json={"origem_id": 999999999, "destino_id": losango.ponto("A")})
    assert r.status_code == 404 and r.json()["campo"] == "origem_id"


def test_origem_igual_destino_da_422(cliente, losango):
    r = cliente.post(
        "/rotas", json={"origem_id": losango.ponto("A"), "destino_id": losango.ponto("A")}
    )
    assert r.status_code == 422
    assert r.json()["mensagem"] == "Pedido de rota inválido."


def test_perfil_deficiencia_visual_ainda_nao_existe(cliente, losango):
    r = _rota(cliente, losango, "A", "D", "deficiencia_visual")
    assert r.status_code == 422
    assert r.json()["erros"][0] == {"campo": "perfil", "erro": "Perfil ainda não disponível."}


@pytest.mark.parametrize(
    "corpo",
    [
        b"nao e json",
        b"{}",
        b'{"origem_id": "1", "destino_id": 2}',
        b'{"origem_id": 1, "destino_id": 2, "extra": 1}',
        b'{"origem_id": 1, "destino_id": 2, "perfil": "voador"}',
        b'{"origem_id": 1.5, "destino_id": 2}',
    ],
)
def test_corpo_invalido_da_422_em_portugues(cliente, corpo):
    r = cliente.post("/rotas", content=corpo, headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["mensagem"] == "Pedido de rota inválido."
    assert r.json()["erros"]


def test_corpo_grande_da_413(cliente):
    r = cliente.post("/rotas", content=b" " * 20000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_trecho_provisorio_marca_rotulo_flag_e_atribuicao(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A", fonte="provisorio")
    g.no("B", 10, ponto="Entrada B", fonte="provisorio")
    g.aresta("A", "B", 10, fonte="provisorio", acessivel=None, por="OpenStreetMap (contribuidores)")
    corpo = _rota(cliente, g, "A", "B").json()
    assert corpo["provisorio"] is True
    assert corpo["rotulo"].startswith("PROVISÓRIO")
    assert "não conferidos a pé" in corpo["rotulo"]
    assert "OpenStreetMap" in corpo["atribuicao"]
    assert corpo["acessivel_cadeirante"] is None


def test_rota_conferida_a_pe_nao_e_provisoria(cliente, losango):
    corpo = _rota(cliente, losango, "A", "D").json()
    assert corpo["provisorio"] is False
    assert "provisório" not in corpo["rotulo"].lower()
    assert "atribuicao" not in corpo


def test_resposta_traz_contrato_completo(cliente, losango):
    corpo = _rota(cliente, losango, "A", "D").json()
    assert set(corpo) >= {
        "rotulo",
        "provisorio",
        "perfil",
        "origem",
        "destino",
        "distancia_m",
        "custo",
        "acessivel_cadeirante",
        "avisos",
        "aviso_seguranca",
        "trechos",
        "instrucoes",
        "geometria",
    }
    assert corpo["perfil"] == "sem_restricao"
    assert corpo["aviso_seguranca"].startswith("Apoio à orientação.")
    assert corpo["origem"]["nome"] == "Entrada A"
    assert corpo["instrucoes"][-1]["texto"] == "Você chegou à entrada D."
    assert [i["ordem"] for i in corpo["instrucoes"]] == [1, 2, 3]
    assert corpo["geometria"]["type"] == "LineString"


def test_penalidade_do_env_vale_sem_refazer_seed(cliente, losango):
    """Com escada barata (penalidade pequena) o sem_restricao passa a pegar a escada."""
    app.dependency_overrides[obter_configuracoes] = lambda: Configuracoes(penalidade_escada=1.01)
    try:
        corpo = _rota(cliente, losango, "A", "D").json()
    finally:
        del app.dependency_overrides[obter_configuracoes]
    assert _ids_trechos(corpo) == [losango.ab, losango.bd]


def test_instrucoes_anunciam_escada_antes_do_trecho(cliente, conexao):
    g = Grafo(conexao)
    g.no("A", 0, ponto="Entrada A")
    g.no("B", 10)
    g.no("C", 20, ponto="Entrada C")
    g.aresta("A", "B", 20)
    g.aresta("B", "C", 12, tipo="escada", acessivel=False)
    textos = [i["texto"] for i in _rota(cliente, g, "A", "C").json()["instrucoes"]]
    assert textos[1].startswith("Atenção: há uma escada")


def test_seed_do_campus_escada_so_para_sem_restricao(cliente):
    """Seed provisório do OpenStreetMap: a passagem no alto do escadão só se alcança por escada."""
    pontos = {
        f["properties"]["nome"]: f["properties"]["id"]
        for f in cliente.get(
            "/pontos-interesse", params={"bbox": "-46.6622,-23.5575,-46.6422,-23.5375"}
        ).json()["features"]
    }
    if "Passagem entre os Prédios 6 e 24" not in pontos:
        pytest.skip("seed provisório do OSM não está carregado")
    corpo = {
        "origem_id": pontos["Passagem entre os Prédios 6 e 24"],
        "destino_id": pontos["Entrada do Prédio 31"],
    }
    livre = cliente.post("/rotas", json=corpo)
    assert livre.status_code == 200 and livre.json()["provisorio"] is True
    assert any(t["tipo"] == "escada" for t in livre.json()["trechos"])
    cad = cliente.post("/rotas", json={**corpo, "perfil": "cadeirante"})
    assert cad.status_code == 404 and cad.json()["codigo"] == "sem_rota"
