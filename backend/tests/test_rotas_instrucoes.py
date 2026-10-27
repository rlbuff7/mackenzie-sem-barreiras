"""Instruções em texto da rota (app/rotas/instrucoes.py): puras, sem banco."""

import math

import pytest

from app.rotas.instrucoes import arredondar_metros, montar_instrucoes, montar_instrucoes_detalhadas
from app.rotas.modelos import Trecho

LON0, LAT0 = -46.652, -23.547
_M_LAT = 110_600.0
_M_LON = 111_320.0 * math.cos(math.radians(LAT0))


def _coords(pontos_m):
    """[(x, y)] em metros (x leste, y norte) para [[lon, lat]]."""
    return [[LON0 + x / _M_LON, LAT0 + y / _M_LAT] for x, y in pontos_m]


def _t(i, tipo, pontos_m, de, para, metros=None):
    """Trecho com geometria sintética; o comprimento é o geométrico, salvo `metros`."""
    geometrico = sum(math.dist(a, b) for a, b in zip(pontos_m, pontos_m[1:], strict=False))
    return Trecho(
        aresta_id=i,
        tipo=tipo,
        comprimento_m=geometrico if metros is None else metros,
        acessivel_cadeirante=None,
        fonte_verificacao="provisorio",
        no_de=de,
        no_para=para,
        custo=geometrico,
        coordenadas=_coords(pontos_m),
    )


def _sem_geometria(i, tipo, metros, de, para):
    return Trecho(i, tipo, metros, None, "provisorio", de, para, metros, [])


@pytest.mark.parametrize(
    ("metros", "esperado"),
    [(0.4, 5), (3.0, 5), (7.4, 5), (7.5, 10), (12.4, 10), (12.5, 15), (12.0, 10), (40.2, 40)],
)
def test_arredondamento_em_multiplos_de_5_com_minimo_5(metros, esperado):
    assert arredondar_metros(metros) == esperado


def test_reta_com_varios_trechos_e_uma_instrucao_so_sem_curva():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 20)], 1, 2),
        _t(2, "calcada", [(0, 20), (3, 40)], 2, 3),  # ~8,5° de desvio: continua em frente
    ]
    textos = montar_instrucoes(trechos, {}, "Entrada do Prédio 31", "Entrada do Prédio 29")
    assert len(textos) == 2
    assert textos[0] == (
        "Saindo da entrada do Prédio 29, siga pelo caminho em direção à entrada do Prédio 31, "
        "por cerca de 40 metros (uns 40 segundos)."
    )
    assert textos[1] == "Você chegou à entrada do Prédio 31."


def test_curva_de_90_graus_a_direita_vem_na_mesma_instrucao():
    trechos = [_t(1, "calcada", [(0, 0), (0, 40), (30, 40)], 1, 2)]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert len(textos) == 3
    assert textos[0].endswith("por cerca de 40 metros (uns 40 segundos). Depois, vire à direita.")
    assert textos[1] == "Siga em frente por cerca de 30 metros (uns 30 segundos)."
    assert "direita" not in textos[0].split("Depois")[0]  # primeiro passo sem lado


def test_curva_leve_de_40_graus_a_esquerda():
    # norte, depois 40° à esquerda (rumo 320°)
    fim = (-30 * math.sin(math.radians(40)), 40 + 30 * math.cos(math.radians(40)))
    trechos = [_t(1, "calcada", [(0, 0), (0, 40), fim], 1, 2)]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert "Depois, vire levemente à esquerda." in textos[0]
    assert len(textos) == 3


def test_retorno_acima_de_135_graus():
    trechos = [_t(1, "calcada", [(0, 0), (0, 40), (5, 10)], 1, 2)]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert "Depois, faça o retorno." in textos[0]


def test_curva_de_60_graus_ja_e_curva_normal_e_24_graus_nao_e_curva():
    def com_angulo(graus):
        fim = (30 * math.sin(math.radians(graus)), 40 + 30 * math.cos(math.radians(graus)))
        return montar_instrucoes([_t(1, "calcada", [(0, 0), (0, 40), fim], 1, 2)], {}, "B", "A")

    assert "Depois, vire à direita." in com_angulo(60)[0]
    assert len(com_angulo(24)) == 2


def test_zigue_zague_curto_e_ignorado():
    # 30 m ao norte, um degrau de 5 m para leste, 30 m ao norte: sem curva fantasma
    trechos = [_t(1, "calcada", [(0, 0), (0, 30), (5, 30), (5, 60)], 1, 2)]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert len(textos) == 2
    assert "Depois" not in textos[0]
    assert "cerca de 65 metros" in textos[0]


def test_aresta_invertida_na_ordem_da_rota_gera_a_curva_certa():
    # trecho 2 foi guardado de leste para oeste, mas a rota o percorre de oeste para leste:
    # a camada de caminho entrega as coordenadas já no sentido da rota
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 40)], 1, 2),
        _t(2, "calcada", [(0, 40), (30, 40)], 2, 3),
    ]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert "Depois, vire à direita." in textos[0]
    # e o mesmo caminho ao contrário (leste para oeste depois sul) vira à esquerda... de volta
    volta = [
        _t(1, "calcada", [(30, 40), (0, 40)], 1, 2),
        _t(2, "calcada", [(0, 40), (0, 0)], 2, 3),
    ]
    assert "Depois, vire à esquerda." in montar_instrucoes(volta, {}, "B", "A")[0]


def test_escada_a_seguir_e_anunciada_no_fim_da_instrucao_anterior():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 20)], 1, 2),
        _t(2, "escada", [(0, 20), (0, 25)], 2, 3),
        _t(3, "calcada", [(0, 25), (0, 45)], 3, 4),
    ]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert textos[0].endswith("Em cerca de 20 metros, escada.")
    assert textos[1] == "Escada, cerca de 5 metros (uns 10 segundos). Use o corrimão se houver."
    assert textos[2] == "Siga em frente por cerca de 20 metros (uns 20 segundos)."
    assert "tem corrimão" not in " ".join(textos)


def test_escada_depois_de_curva_diz_logo_em_seguida():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 20)], 1, 2),
        _t(2, "escada", [(0, 20), (10, 20)], 2, 3),
    ]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert "Depois, vire à direita. Logo em seguida, escada." in textos[0]


def test_travessia_e_anunciada_antes():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 20)], 1, 2),
        _t(2, "travessia", [(0, 20), (0, 28)], 2, 3),
    ]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert textos[0].endswith("Atenção: travessia.")
    assert textos[1].startswith("Siga em frente por cerca de 10 metros")


@pytest.mark.parametrize(
    ("metros", "trecho_esperado"),
    [
        (5, "cerca de 5 metros (uns 5 segundos)"),
        (90, "cerca de 90 metros (uns 90 segundos)"),
        (95, "cerca de 95 metros (cerca de 1 minuto e meio)"),
        (120, "cerca de 120 metros (cerca de 2 minutos)"),
        (150, "cerca de 150 metros (cerca de 2 minutos e meio)"),
        (410, "cerca de 410 metros (cerca de 7 minutos)"),
    ],
)
def test_tempo_em_segundos_ate_90_e_depois_em_minutos(metros, trecho_esperado):
    textos = montar_instrucoes([_t(1, "calcada", [(0, 0), (0, metros)], 1, 2)], {}, "B", "A")
    assert trecho_esperado in textos[0]


def test_ponto_de_interesse_no_meio_e_mencionado_sem_virar_referencia_de_direcao():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 40)], 1, 2),
        _t(2, "calcada", [(0, 40), (0, 80)], 2, 3),
    ]
    refs = {2: "Entrada do Prédio 29", 3: "Entrada B"}
    textos = montar_instrucoes(trechos, refs, "Entrada B", "Entrada A")
    assert "em direção à entrada do Prédio 29" in textos[0]
    assert "Você passa" not in textos[0]  # a referência de direção não se repete
    textos = montar_instrucoes(trechos, {2: "Prédio 19"}, "Entrada B", "Entrada A")
    assert "em direção ao prédio 19" in textos[0]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert "em direção à entrada B" in textos[0]


def test_no_maximo_duas_referencias_por_instrucao():
    trechos = [_t(i, "calcada", [(0, i * 10), (0, i * 10 + 10)], i, i + 1) for i in range(1, 5)]
    refs = {2: "Prédio 1", 3: "Prédio 2", 4: "Prédio 3"}
    texto = montar_instrucoes(trechos, refs, "Entrada Z", "Entrada A")[0]
    assert "em direção ao prédio 1," in texto  # a 1ª virou direção
    assert "Você passa pelo prédio 2 e pelo prédio 3." in texto


def test_sem_geometria_nao_inventa_curva():
    trechos = [_sem_geometria(1, "calcada", 20, 1, 2), _sem_geometria(2, "escada", 5, 2, 3)]
    textos = montar_instrucoes(trechos, {}, "Entrada X", "Entrada A")
    assert textos[0].endswith("Em cerca de 20 metros, escada.")
    assert len(textos) == 3


def test_rota_de_um_trecho_so_tem_duas_instrucoes():
    assert len(montar_instrucoes([_t(1, "calcada", [(0, 0), (0, 5)], 1, 2)], {}, "Y", "X")) == 2


def test_texto_nao_afirma_piso_corrimao_ou_posicao():
    texto = " ".join(
        montar_instrucoes([_t(1, "calcada", [(0, 0), (0, 40), (30, 40)], 1, 2)], {}, "B", "A")
    ).lower()
    assert "à sua frente" not in texto


def test_escada_fala_metros_e_tempo_a_meio_metro_por_segundo():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 20)], 1, 2),
        _t(2, "escada", [(0, 20), (0, 40)], 2, 3),
        _t(3, "calcada", [(0, 40), (0, 60)], 3, 4),
    ]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert textos[1] == "Escada, cerca de 20 metros (uns 40 segundos). Use o corrimão se houver."


def _graus(rumo_graus, metros):
    r = math.radians(rumo_graus)
    return metros * math.sin(r), metros * math.cos(r)


def _ponto(origem, rumo, metros):
    dx, dy = _graus(rumo, metros)
    return (origem[0] + dx, origem[1] + dy)


def test_duas_curvas_leves_a_menos_de_25m_viram_uma_pela_soma():
    p0 = (0.0, 0.0)
    p1 = _ponto(p0, 0, 30)
    p2 = _ponto(p1, 40, 10)  # leve à direita (40°), perna curta de 10 m
    p3 = _ponto(p2, 80, 30)  # mais 40°: soma 80° -> curva normal
    trechos = [_t(1, "calcada", [p0, p1, p2, p3], 1, 2)]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert len(textos) == 3
    assert "Depois, vire à direita." in textos[0]
    assert "levemente" not in " ".join(textos)
    assert "cerca de 35 metros" in textos[1]  # o pedaço do meio é dividido ao meio entre as pernas


def test_duas_curvas_leves_que_se_anulam_viram_siga_em_frente():
    p0 = (0.0, 0.0)
    p1 = _ponto(p0, 0, 30)
    p2 = _ponto(p1, 40, 10)
    p3 = _ponto(p2, 0, 30)  # volta ao rumo original: soma 0
    trechos = [_t(1, "calcada", [p0, p1, p2, p3], 1, 2)]
    textos = montar_instrucoes(trechos, {}, "Entrada B", "Entrada A")
    assert len(textos) == 2
    assert "Depois" not in textos[0]


def test_entrada_aproximada_e_falada_como_lateral_sem_mudar_o_nome():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 40)], 1, 2),
        _t(2, "calcada", [(0, 40), (0, 80)], 2, 3),
    ]
    nome = "Entrada aproximada: Escola de Engenharia Mackenzie"
    refs = {2: nome, 3: "Entrada B"}
    textos = montar_instrucoes(trechos, refs, "Entrada B", "Entrada A")
    assert "em direção à lateral da Escola de Engenharia Mackenzie" in textos[0]
    refs = {2: "Prédio 19", 3: "Entrada B"}
    trechos3 = [
        _t(1, "calcada", [(0, 0), (0, 40)], 1, 2),
        _t(2, "calcada", [(0, 40), (30, 40)], 2, 3),
        _t(3, "calcada", [(30, 40), (30, 80)], 3, 4),
    ]
    refs = {2: "Prédio 19", 3: nome}
    textos = montar_instrucoes(trechos3, refs, "Entrada B", "Entrada A")
    assert "Você passa pela lateral da Escola de Engenharia Mackenzie." in " ".join(textos)
    assert nome == "Entrada aproximada: Escola de Engenharia Mackenzie"


def test_inicio_m_crescente_ultimo_e_distancia_total_e_curva_coerente_com_o_texto():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 40)], 1, 2),
        _t(2, "calcada", [(0, 40), (30, 40)], 2, 3),  # direita (90°)
        _t(3, "calcada", [(30, 40), (30, 0)], 3, 4),  # direita (90°)
        _t(4, "escada", [(30, 0), (30, -10)], 4, 5),
    ]
    itens = montar_instrucoes_detalhadas(trechos, {}, "Entrada B", "Entrada A")
    inicios = [i["inicio_m"] for i in itens]
    assert inicios[0] == 0
    assert inicios == sorted(inicios) and len(set(inicios)) == len(inicios)
    assert abs(inicios[-1] - sum(t.comprimento_m for t in trechos)) <= 1.0
    for item in itens:
        texto, curva = item["texto"], item["curva"]
        if curva in ("direita", "esquerda"):
            assert f"Depois, vire à {curva}." in texto
        elif curva in ("leve_direita", "leve_esquerda"):
            assert f"Depois, vire levemente à {curva.removeprefix('leve_')}." in texto
        elif curva == "retorno":
            assert "Depois, faça o retorno." in texto
        elif curva == "escada":
            assert "escada" in texto and "Depois, vire" not in texto
        else:
            assert "Depois, vire" not in texto and "retorno" not in texto
    assert itens[0]["curva"] == "direita"
    assert itens[-1]["curva"] is None


def test_curva_escada_quando_a_proxima_perna_e_escada_sem_curva():
    trechos = [
        _t(1, "calcada", [(0, 0), (0, 40)], 1, 2),
        _t(2, "escada", [(0, 40), (0, 50)], 2, 3),
    ]
    itens = montar_instrucoes_detalhadas(trechos, {}, "B", "A")
    assert [i["curva"] for i in itens] == ["escada", None, None]


def test_curva_leve_e_retorno():
    leve = [_t(1, "calcada", [(0, 0), (0, 40)], 1, 2), _t(2, "calcada", [(0, 40), (-30, 60)], 2, 3)]
    assert montar_instrucoes_detalhadas(leve, {}, "B", "A")[0]["curva"] == "leve_esquerda"
    volta = [_t(1, "calcada", [(0, 0), (0, 40)], 1, 2), _t(2, "calcada", [(0, 40), (2, 0)], 2, 3)]
    assert montar_instrucoes_detalhadas(volta, {}, "B", "A")[0]["curva"] == "retorno"


def test_curvas_leves_juntadas_ficam_no_ponto_medio_entre_os_dois_vertices():
    p0 = (0.0, 0.0)
    p1 = _ponto(p0, 0, 30)  # 1º vértice (30 m)
    p2 = _ponto(p1, 40, 8)  # 2º vértice (38 m), 8 m depois
    p3 = _ponto(p2, 80, 30)
    trechos = [_t(1, "calcada", [p0, p1, p2, p3], 1, 2)]
    det = montar_instrucoes_detalhadas(trechos, {}, "Entrada B", "Entrada A")
    assert [i["inicio_m"] for i in det] == [0.0, 34.0, 68.0]
    assert det[0]["curva"] == "direita"
    assert "cerca de 35 metros" in det[0]["texto"]  # 34 m arredonda para 35
    assert "cerca de 35 metros" in det[1]["texto"]  # 34 m
