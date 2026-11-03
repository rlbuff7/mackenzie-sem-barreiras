"""POST /orientacoes: estado, mensagem, direção, privacidade, 404/422/413.

Contra o seed REAL do campus (rota 4 -> 6, OSM provisório); pula se o seed não estiver
carregado. As posições são SINTÉTICAS (pontos calculados sobre a geometria da rota,
com deslocamentos conhecidos), não medições. Nada disto é dado de coleta.
"""

import logging
import math

import pytest

from app.orientacao.rumo import ponto_na_rota

_M_LAT = 110_600.0
_BBOX = "-46.6622,-23.5575,-46.6422,-23.5375"


@pytest.fixture
def rota_4_6(cliente):
    r = cliente.post("/rotas", json={"origem_id": 4, "destino_id": 6})
    if r.status_code != 200:
        pytest.skip("seed do campus (rota 4 -> 6) não está carregado")
    return r.json()


def _posicao_na_rota(rota, metros, deslocamento_lateral_m=0.0, **extra):
    """Ponto a `metros` do início da rota, deslocado `deslocamento_lateral_m` para o lado
    (perpendicular ao sentido local da rota)."""
    coords = rota["geometria"]["coordinates"]
    lon, lat = ponto_na_rota(coords, metros)
    lon_b, lat_b = ponto_na_rota(coords, metros + 1.0)
    m_lon = 111_320.0 * math.cos(math.radians(lat))
    leste, norte = (lon_b - lon) * m_lon, (lat_b - lat) * _M_LAT
    norma = math.hypot(leste, norte) or 1.0
    return {
        "lat": lat + deslocamento_lateral_m * (leste / norma) / _M_LAT,
        "lon": lon - deslocamento_lateral_m * (norte / norma) / m_lon,
        "precisao_m": 5.0,
        **extra,
    }


def _orientar(cliente, posicao, **extra):
    corpo = {"origem_id": 4, "destino_id": 6, "posicao": posicao, **extra}
    return cliente.post("/orientacoes", json=corpo)


def test_perto_do_inicio_na_rota(cliente, rota_4_6):
    r = _orientar(cliente, _posicao_na_rota(rota_4_6, 3.0))
    assert r.status_code == 200
    c = r.json()
    assert c["estado"] == "na_rota"
    assert c["progresso_m"] == pytest.approx(3.0, abs=1.0)
    assert c["distancia_restante_m"] == pytest.approx(rota_4_6["distancia_m"] - 3.0, abs=1.5)
    assert c["direcao"] is None  # sem bússola nem velocidade: silêncio
    assert set(c) == {
        "estado",
        "confianca",
        "mensagem",
        "distancia_restante_m",
        "progresso_m",
        "direcao",
    }


def test_longe_da_rota_manda_parar_sem_direcao(cliente, rota_4_6):
    pos = _posicao_na_rota(
        rota_4_6, 60.0, deslocamento_lateral_m=80.0, rumo_graus=90.0, velocidade_ms=1.2
    )
    c = _orientar(cliente, pos).json()
    assert c["estado"] == "fora_da_rota"
    assert c["confianca"] == "baixa"
    assert c["direcao"] is None
    assert c["mensagem"]["texto"] == "Você saiu da rota. Pare e aguarde."
    assert c["mensagem"]["chave"] == "fora_da_rota"
    assert c["mensagem"]["prioridade"] == "alta"


def test_precisao_de_40_m_e_silencio_sem_posicao(cliente, rota_4_6):
    pos = _posicao_na_rota(rota_4_6, 30.0, precisao_m=40.0, rumo_graus=90.0, velocidade_ms=1.2)
    c = _orientar(cliente, pos).json()
    assert c["estado"] == "precisao_insuficiente"
    assert c["confianca"] == "baixa"
    assert c["progresso_m"] is None and c["distancia_restante_m"] is None
    assert c["direcao"] is None
    assert c["mensagem"]["texto"] == (
        "Não sei onde você está agora. Fique parado por alguns segundos."
    )


def test_perto_do_fim_chegou(cliente, rota_4_6):
    c = _orientar(cliente, _posicao_na_rota(rota_4_6, rota_4_6["distancia_m"] - 3.0)).json()
    assert c["estado"] == "chegou"
    assert c["mensagem"]["chave"] == "chegada"
    assert c["mensagem"]["texto"].startswith("Você chegou")


def test_anti_repeticao_do_cliente_silencia_a_mesma_chave(cliente, rota_4_6):
    pos = _posicao_na_rota(rota_4_6, 3.0, precisao_m=40.0)
    chave = _orientar(cliente, pos).json()["mensagem"]["chave"]
    assert chave == "sem_posicao"
    r = _orientar(cliente, pos, recentes=[{"chave": chave, "ha_segundos": 5.0}])
    assert r.json()["mensagem"] is None
    r = _orientar(cliente, pos, recentes=[{"chave": chave, "ha_segundos": 30.0}])
    assert r.json()["mensagem"]["chave"] == chave


def test_andando_alinhado_da_direcao_frente_e_confirma(cliente, rota_4_6):
    coords = rota_4_6["geometria"]["coordinates"]
    lon_a, lat_a = ponto_na_rota(coords, 3.0)
    lon_b, lat_b = ponto_na_rota(coords, 11.0)
    m_lon = 111_320.0 * math.cos(math.radians(lat_a))
    rumo = math.degrees(math.atan2((lon_b - lon_a) * m_lon, (lat_b - lat_a) * _M_LAT)) % 360
    pos = _posicao_na_rota(rota_4_6, 3.0, rumo_graus=rumo, rumo_oscilacao_graus=4.0)
    pos["velocidade_ms"] = 1.1
    c = _orientar(cliente, pos).json()
    assert c["direcao"] == "frente"
    assert c["estado"] == "na_rota"


def test_parado_ou_bussola_instavel_nao_da_direcao(cliente, rota_4_6):
    base = _posicao_na_rota(rota_4_6, 3.0, rumo_graus=90.0)
    assert _orientar(cliente, {**base, "velocidade_ms": 0.0}).json()["direcao"] is None
    instavel = {**base, "velocidade_ms": 1.2, "rumo_oscilacao_graus": 80.0}
    assert _orientar(cliente, instavel).json()["direcao"] is None


def test_aviso_de_escada_no_seed_real(cliente):
    pontos = {
        f["properties"]["nome"]: f["properties"]["id"]
        for f in cliente.get("/pontos-interesse", params={"bbox": _BBOX}).json()["features"]
    }
    if "Passagem entre os Prédios 6 e 24" not in pontos:
        pytest.skip("seed provisório do OSM não está carregado")
    corpo = {
        "origem_id": pontos["Passagem entre os Prédios 6 e 24"],
        "destino_id": pontos["Entrada do Prédio 31"],
    }
    rota = cliente.post("/rotas", json=corpo).json()
    escada = next(t for t in rota["trechos"] if t["tipo"] == "escada")
    antes = sum(t["comprimento_m"] for t in rota["trechos"][: rota["trechos"].index(escada)])
    pos = _posicao_na_rota(rota, max(0.0, antes - 8.0))
    c = cliente.post("/orientacoes", json={**corpo, "posicao": pos}).json()
    assert c["estado"] == "na_rota"
    assert c["mensagem"]["prioridade"] == "perigo"
    assert "escada" in c["mensagem"]["texto"]


def test_rota_inexistente_da_404_como_rotas(cliente):
    r = cliente.post(
        "/orientacoes",
        json={
            "origem_id": 4,
            "destino_id": 999999999,
            "posicao": {"lat": -23.5, "lon": -46.65, "precisao_m": 5.0},
        },
    )
    assert r.status_code == 404
    assert r.json()["campo"] == "destino_id"


def test_sem_caminho_da_404_sem_rota(cliente, rota_4_6):
    # Cadeirante onde só há escada: mesmo 404 sem_rota de /rotas.
    pontos = {
        f["properties"]["nome"]: f["properties"]["id"]
        for f in cliente.get("/pontos-interesse", params={"bbox": _BBOX}).json()["features"]
    }
    if "Passagem entre os Prédios 6 e 24" not in pontos:
        pytest.skip("seed provisório do OSM não está carregado")
    r = cliente.post(
        "/orientacoes",
        json={
            "origem_id": pontos["Passagem entre os Prédios 6 e 24"],
            "destino_id": pontos["Entrada do Prédio 31"],
            "perfil": "cadeirante",
            "posicao": {"lat": -23.5, "lon": -46.65, "precisao_m": 5.0},
        },
    )
    assert r.status_code == 404 and r.json()["codigo"] == "sem_rota"


_POS = {"lat": -23.5, "lon": -46.65, "precisao_m": 5.0}


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"origem_id": 4, "destino_id": 6},  # sem posição
        {"origem_id": 4, "destino_id": 4, "posicao": _POS},
        {"origem_id": 4, "destino_id": 6, "posicao": {**_POS, "lat": 91.0}},
        {"origem_id": 4, "destino_id": 6, "posicao": {**_POS, "precisao_m": -1.0}},
        {"origem_id": 4, "destino_id": 6, "posicao": {**_POS, "rumo_graus": 400.0}},
        {"origem_id": 4, "destino_id": 6, "posicao": {**_POS, "velocidade_ms": -1.0}},
        {"origem_id": 4, "destino_id": 6, "posicao": {**_POS, "extra": 1}},
        {"origem_id": 4, "destino_id": 6, "posicao": _POS, "extra": 1},
        {"origem_id": 4, "destino_id": 6, "posicao": _POS, "perfil": "voador"},
        {"origem_id": 4, "destino_id": 6, "posicao": {**_POS, "lat": "x"}},
        {
            "origem_id": 4,
            "destino_id": 6,
            "posicao": _POS,
            "recentes": [{"chave": "a", "ha_segundos": 1.0}] * 21,
        },
        {
            "origem_id": 4,
            "destino_id": 6,
            "posicao": _POS,
            "recentes": [{"chave": "", "ha_segundos": 1.0}],
        },
    ],
)
def test_corpo_invalido_da_422_em_portugues(cliente, corpo):
    r = cliente.post("/orientacoes", json=corpo)
    assert r.status_code == 422
    assert r.json()["mensagem"] == "Pedido de orientação inválido."
    assert r.json()["erros"]


def test_corpo_grande_da_413(cliente):
    r = cliente.post("/orientacoes", content=" " * (20 * 1024))
    assert r.status_code == 413


def test_nada_da_posicao_vai_para_o_log_nem_para_o_banco(cliente, rota_4_6, conexao, caplog):
    antes = {
        t: conexao.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608
        for t in ("medicoes_gps", "alertas", "barreiras", "fotos_pontos", "pontos_interesse")
    }
    lat_secreta = -23.5473210987
    pos = {**_posicao_na_rota(rota_4_6, 3.0), "lat": lat_secreta}
    with caplog.at_level(logging.DEBUG):
        _orientar(cliente, pos)
        _orientar(cliente, {**pos, "precisao_m": -5.0})  # 422 também não pode ecoar
    texto_do_log = "\n".join(r.getMessage() for r in caplog.records)
    assert "23.5473210987" not in texto_do_log
    assert str(pos["lon"])[:9] not in texto_do_log
    depois = {
        t: conexao.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608
        for t in antes
    }
    assert depois == antes


def test_resposta_de_422_nao_ecoa_a_posicao(cliente):
    r = cliente.post(
        "/orientacoes",
        json={
            "origem_id": 4,
            "destino_id": 6,
            "posicao": {"lat": 91.123456, "lon": -46.65, "precisao_m": 5.0},
        },
    )
    assert r.status_code == 422
    assert "91.123456" not in r.text
