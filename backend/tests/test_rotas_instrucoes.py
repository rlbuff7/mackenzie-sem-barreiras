"""Instruções em texto da rota (app/rotas/instrucoes.py): puras, sem banco."""

import pytest

from app.rotas.instrucoes import arredondar_metros, montar_instrucoes
from app.rotas.modelos import Trecho


def _t(i, tipo, metros, de, para):
    return Trecho(
        aresta_id=i,
        tipo=tipo,
        comprimento_m=metros,
        acessivel_cadeirante=None,
        fonte_verificacao="provisorio",
        no_de=de,
        no_para=para,
        custo=metros,
        coordenadas=[],
    )


@pytest.mark.parametrize(
    ("metros", "esperado"),
    [(0.4, 5), (3.0, 5), (7.4, 5), (7.5, 10), (12.4, 10), (12.5, 15), (12.0, 10), (40.2, 40)],
)
def test_arredondamento_em_multiplos_de_5_com_minimo_5(metros, esperado):
    assert arredondar_metros(metros) == esperado


def test_tres_calcadas_seguidas_viram_uma_instrucao():
    trechos = [_t(1, "calcada", 20, 1, 2), _t(2, "calcada", 10, 2, 3), _t(3, "calcada", 10, 3, 4)]
    assert montar_instrucoes(trechos, {}, "Entrada do Prédio 31") == [
        "Siga pelo caminho por cerca de 40 metros.",
        "Você chegou à entrada do Prédio 31.",
    ]


def test_escada_e_anunciada_antes_do_trecho_e_em_instrucao_propria():
    trechos = [_t(1, "calcada", 30, 1, 2), _t(2, "escada", 12, 2, 3), _t(3, "calcada", 20, 3, 4)]
    textos = montar_instrucoes(trechos, {}, "Entrada X")
    assert textos[0].startswith("Siga pelo caminho")
    assert textos[1] == "Atenção: há uma escada no caminho, cerca de 10 metros."
    assert textos[2].startswith("Siga pelo caminho")


def test_no_maximo_duas_referencias_por_instrucao():
    trechos = [_t(i, "calcada", 10, i, i + 1) for i in range(1, 6)]
    refs = {2: "Entrada A", 3: "Entrada B", 4: "Entrada C"}
    primeira = montar_instrucoes(trechos, refs, "Entrada Z")[0]
    assert primeira.count("Você passa por:") == 1
    assert "Entrada A e Entrada B" in primeira
    assert "Entrada C" not in primeira


def test_origem_e_destino_nao_sao_citados_como_referencia():
    trechos = [_t(1, "calcada", 10, 1, 2)]
    textos = montar_instrucoes(trechos, {1: "Origem", 2: "Destino"}, "Destino")
    assert "Você passa por" not in " ".join(textos)


def test_chegada_e_sempre_a_ultima():
    textos = montar_instrucoes([_t(1, "rampa", 10, 1, 2)], {}, "Entrada do Prédio 29")
    assert textos[0] == "Siga por uma rampa, cerca de 10 metros."
    assert textos[-1] == "Você chegou à entrada do Prédio 29."


def test_rota_de_um_trecho_so_tem_duas_instrucoes():
    assert len(montar_instrucoes([_t(1, "calcada", 5, 1, 2)], {}, "Entrada Y")) == 2


def test_nunca_diz_esquerda_direita_nem_a_frente():
    trechos = [_t(1, "calcada", 30, 1, 2), _t(2, "travessia", 8, 2, 3), _t(3, "rampa", 9, 3, 4)]
    texto = " ".join(montar_instrucoes(trechos, {2: "Entrada A"}, "Entrada B")).lower()
    for proibida in ("esquerda", "direita", "à frente", "a frente", "vire"):
        assert proibida not in texto


def test_travessia_e_anunciada_com_atencao():
    textos = montar_instrucoes([_t(1, "travessia", 8, 1, 2)], {}, "Entrada B")
    assert textos[0].startswith("Atenção: você atravessa")
