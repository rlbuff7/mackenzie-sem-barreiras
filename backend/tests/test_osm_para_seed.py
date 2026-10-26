"""Testes do gerador de seed do campus a partir do OpenStreetMap (db/scripts/osm_para_seed.py).

Sem rede: usam um JSON de Overpass fabricado à mão (formato `out body geom`).
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parents[2] / "db" / "scripts" / "osm_para_seed.py"
_spec = importlib.util.spec_from_file_location("osm_para_seed", _CAMINHO)
osm = importlib.util.module_from_spec(_spec)
sys.modules["osm_para_seed"] = osm
_spec.loader.exec_module(osm)

DATA = date(2026, 10, 26)
LAT, LON = -23.5470, -46.6520  # dentro do recorte


def _via(osm_id, tags, nos):
    """nos: lista de (id_no, deslocamento_lat_m_aprox, deslocamento_lon_m_aprox)."""
    return {
        "type": "way",
        "id": osm_id,
        "tags": tags,
        "nodes": [n for n, _, _ in nos],
        "geometry": [{"lat": LAT + dy * 9e-6, "lon": LON + dx * 9e-6} for _, dy, dx in nos],
    }


def _dados(*elementos):
    return {"elements": list(elementos)}


def _grafo_t():
    """Três ruas em T + uma escada no fim + uma via isolada (outra componente)."""
    return _dados(
        _via(1, {"highway": "service"}, [(10, 0, 0), (11, 0, 30), (12, 0, 60)]),
        _via(2, {"highway": "footway"}, [(11, 0, 30), (13, 30, 30)]),
        _via(3, {"highway": "steps"}, [(13, 30, 30), (14, 45, 30)]),
        _via(4, {"highway": "footway"}, [(90, 80, 80), (91, 90, 80)]),  # isolada
    )


def test_grafo_tem_nos_nas_intersecoes_e_extremos():
    g = osm.construir_grafo(_grafo_t())
    assert len(g.nos) == 5  # 10, 11, 12, 13, 14
    assert len(g.arestas) == 4  # 10-11, 11-12, 11-13, 13-14


def test_componente_isolada_e_descartada():
    g = osm.construir_grafo(_grafo_t())
    assert g.descartadas == 1
    assert all(a["osm_id"] != 4 for a in g.arestas)


def test_escada_vira_tipo_escada_e_nao_acessivel():
    g = osm.construir_grafo(_grafo_t())
    escada = [a for a in g.arestas if a["osm_id"] == 3][0]
    assert escada["tipo"] == "escada" and escada["acessivel_cadeirante"] is False


def test_classificacao_de_rampa_travessia_e_cadeira():
    assert osm.classificar({"highway": "footway", "incline": "5%"}) == ("rampa", None)
    assert osm.classificar({"highway": "footway", "ramp": "yes", "wheelchair": "yes"}) == (
        "rampa",
        True,
    )
    assert osm.classificar({"highway": "footway", "footway": "crossing"}) == ("travessia", None)
    assert osm.classificar({"highway": "service"}) == ("calcada", None)
    assert osm.classificar({"highway": "footway", "wheelchair": "no"}) == ("calcada", False)


def test_calcada_de_rua_e_travessia_ficam_de_fora_por_padrao():
    dados = _dados(
        _via(1, {"highway": "service"}, [(10, 0, 0), (11, 0, 30)]),
        _via(2, {"highway": "footway", "footway": "sidewalk"}, [(11, 0, 30), (12, 30, 30)]),
    )
    assert len(osm.construir_grafo(dados).arestas) == 1
    assert len(osm.construir_grafo(dados, com_calcadas_de_rua=True).arestas) == 2


def test_via_e_cortada_no_recorte():
    # segundo ponto fora do recorte (muito ao norte): só sobra o trecho de dentro
    dados = _dados(
        _via(1, {"highway": "service"}, [(10, 0, 0), (11, 0, 30), (12, 9000, 30)]),
    )
    g = osm.construir_grafo(dados)
    assert len(g.arestas) == 1 and len(g.nos) == 2


def test_ponto_so_fica_com_no_se_estiver_perto_e_nenhum_no_serve_a_dois_pontos():
    dados = _grafo_t()
    g = osm.construir_grafo(dados, pontos_extra_para_ligar=[(LAT, LON)])
    osm.adicionar_pontos(g, dados)
    com_no = [p for p in g.pontos if p["tipo"] in ("entrada", "portao") and p["no"] is not None]
    assert all(p["distancia_ao_no_m"] <= osm.DISTANCIA_MAXIMA_LIGACAO_M for p in com_no)
    nos_usados = [p["no"] for p in com_no]
    assert len(nos_usados) == len(set(nos_usados))


def test_sql_tem_atribuicao_delete_ids_fixos_e_proveniencia():
    sql, grafo = osm.gerar(_grafo_t(), DATA)
    assert "OpenStreetMap" in sql and "ODbL" in sql
    assert (
        sql.index("DELETE FROM arestas;")
        < sql.index("DELETE FROM nos;")
        < sql.index("DELETE FROM pontos_interesse;")
    )
    assert "'provisorio'" in sql and "'OpenStreetMap (contribuidores)'" in sql
    assert "DATE '2026-10-26'" in sql
    assert "ST_Length(ST_Transform(g.geom, 31983))" in sql  # comprimento calculado no banco
    assert sql.count("setval(") == 3
    assert len(grafo.arestas) == 4


def test_sql_e_deterministico():
    assert osm.gerar(_grafo_t(), DATA)[0] == osm.gerar(_grafo_t(), DATA)[0]


def test_aspas_sao_escapadas():
    assert osm.aspas("D'Água") == "'D''Água'"


def test_sem_caminhos_no_recorte_falha_com_mensagem():
    with pytest.raises(SystemExit):
        osm.gerar(_dados(), DATA)
