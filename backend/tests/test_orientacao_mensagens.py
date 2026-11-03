"""Testes de `app/orientacao/mensagens.py` (RF12, RNF05). Funções puras, nada é gravado.

Rota de teste SINTÉTICA: 100 m, instruções em 0, 40 e 70 m (curva à direita aos 40 m;
escada de 70 a 80 m; chegada aos 100 m). Limiares PROVISÓRIOS do `.env.example`.
"""

import pytest

from app.orientacao.mensagens import (
    ObstaculoNaRota,
    ParametrosMensagens,
    Recente,
    decidir_mensagem,
    obstaculos_dos_trechos,
)
from app.orientacao.posicao import Avaliacao, ProjecaoNaRota

P = ParametrosMensagens(
    intervalo_repeticao_s=20.0,
    intervalo_repeticao_perigo_s=8.0,
    distancia_perigo_m=15.0,
    distancia_curva_iminente_m=10.0,
)

INSTRUCOES = [
    {"texto": "Siga pelo caminho.", "inicio_m": 0.0, "curva": "direita"},
    {"texto": "Siga em frente por 30 metros.", "inicio_m": 40.0, "curva": "escada"},
    {"texto": "Escada, cerca de 10 metros.", "inicio_m": 70.0, "curva": None},
    {"texto": "Você chegou à entrada do Prédio 29.", "inicio_m": 100.0, "curva": None},
]
OBSTACULOS = [ObstaculoNaRota(tipo="escada", inicio_m=70.0, fim_m=80.0)]


def _aval(estado="na_rota", confianca="alta", percorrida=0.0) -> Avaliacao:
    projecao = ProjecaoNaRota(
        lat=0.0,
        lon=0.0,
        distancia_perpendicular_m=1.0,
        distancia_percorrida_m=percorrida,
        distancia_restante_m=100.0 - percorrida,
        indice_trecho=0,
    )
    return Avaliacao(estado=estado, confianca=confianca, projecao=projecao)


def _decidir(aval, direcao=None, recentes=(), obstaculos=OBSTACULOS, instrucoes=INSTRUCOES):
    return decidir_mensagem(
        aval,
        direcao=direcao,
        instrucoes=instrucoes,
        obstaculos=obstaculos,
        recentes=list(recentes),
        parametros=P,
    )


def test_perigo_escada_a_frente_vence_curva_e_fora_da_rota() -> None:
    # aos 60 m: escada em 10 m. (A curva dos 40 m já passou; aqui só prova a prioridade.)
    m = _decidir(_aval(percorrida=60.0))
    assert m is not None and m.prioridade == "perigo"
    assert m.texto == "Atenção: escada em 10 metros."
    assert m.chave.startswith("perigo_escada")


def test_perigo_travessia() -> None:
    obst = [ObstaculoNaRota(tipo="travessia", inicio_m=70.0, fim_m=80.0)]
    m = _decidir(_aval(percorrida=60.0), obstaculos=obst)
    assert m is not None and m.texto == "Atenção: travessia de rua em 10 metros."


def test_escada_longe_nao_gera_perigo() -> None:
    m = _decidir(_aval(percorrida=20.0))  # escada a 50 m, curva a 20 m
    assert m is None or m.prioridade != "perigo"


def test_perigo_vence_curva_iminente() -> None:
    obst = [ObstaculoNaRota(tipo="escada", inicio_m=44.0, fim_m=50.0)]
    m = _decidir(_aval(percorrida=35.0), obstaculos=obst)  # curva a 5 m, escada a 9 m
    assert m is not None and m.prioridade == "perigo"


def test_perigo_com_texto_logo_a_frente_quando_encostado() -> None:
    m = _decidir(_aval(percorrida=70.0))
    assert m is not None and m.texto == "Atenção: escada logo à frente."


def test_perigo_so_vale_na_rota_nao_fora_dela() -> None:
    m = _decidir(_aval(estado="fora_da_rota", confianca="baixa", percorrida=60.0))
    assert m is not None and m.chave == "fora_da_rota"


def test_fora_da_rota_manda_parar_sem_dar_direcao_de_volta() -> None:
    m = _decidir(
        _aval(estado="fora_da_rota", confianca="baixa", percorrida=10.0), direcao="direita"
    )
    assert m is not None
    assert m.texto == "Você saiu da rota. Pare e aguarde."
    assert m.prioridade == "alta"
    for palavra in ("direita", "esquerda", "frente", "volte", "atrás"):
        assert palavra not in m.texto


def test_curva_iminente() -> None:
    m = _decidir(_aval(percorrida=31.0))  # curva em 9 m -> 10
    assert m is not None
    assert m.texto == "Em 10 metros, vire à direita."
    assert m.chave == "curva_0"
    assert m.prioridade == "media"


def test_curva_longe_nao_avisa() -> None:
    assert _decidir(_aval(percorrida=10.0)) is None


def test_curva_ja_passada_nao_avisa() -> None:
    assert _decidir(_aval(percorrida=45.0), obstaculos=[]) is None


def test_curva_leve_e_retorno_tem_texto_proprio() -> None:
    for codigo, frase in (
        ("leve_esquerda", "Em 5 metros, vire levemente à esquerda."),
        ("retorno", "Em 5 metros, faça o retorno."),
        ("esquerda", "Em 5 metros, vire à esquerda."),
    ):
        instrucoes = [
            {"texto": "a", "inicio_m": 0.0, "curva": codigo},
            {"texto": "b", "inicio_m": 40.0, "curva": None},
            {"texto": "Você chegou à entrada do Prédio 29.", "inicio_m": 100.0, "curva": None},
        ]
        m = _decidir(_aval(percorrida=36.0), obstaculos=[], instrucoes=instrucoes)
        assert m is not None and m.texto == frase


def test_curva_com_confianca_baixa_fica_em_silencio() -> None:
    assert _decidir(_aval(confianca="baixa", percorrida=33.0), obstaculos=[]) is None


def test_chegada_usa_a_frase_da_ultima_instrucao() -> None:
    m = _decidir(_aval(estado="chegou", percorrida=95.0))
    assert m is not None
    assert m.texto == "Você chegou à entrada do Prédio 29."
    assert m.chave == "chegada"


def test_confirmacao_periodica_so_com_direcao_frente_e_confianca() -> None:
    aval = _aval(percorrida=10.0)
    m = _decidir(aval, direcao="frente", obstaculos=[])
    assert m is not None and m.texto == "Siga em frente." and m.prioridade == "baixa"
    assert _decidir(aval, direcao=None, obstaculos=[]) is None
    assert _decidir(aval, direcao="direita", obstaculos=[]) is None
    assert _decidir(_aval(confianca="baixa", percorrida=10.0), "frente", obstaculos=[]) is None


def test_precisao_insuficiente_so_a_mensagem_de_silencio() -> None:
    aval = Avaliacao(estado="precisao_insuficiente", confianca="baixa", projecao=None)
    m = _decidir(aval, direcao="frente")
    assert m is not None
    assert m.texto == "Não sei onde você está agora. Fique parado por alguns segundos."
    assert m.chave == "sem_posicao"
    assert m.prioridade == "alta"


def test_anti_repeticao_mesma_chave_dentro_do_intervalo_fica_em_silencio() -> None:
    aval = _aval(percorrida=31.0)
    assert _decidir(aval, recentes=[Recente("curva_0", 19.9)]) is None
    assert _decidir(aval, recentes=[Recente("curva_0", 20.0)]) is not None


def test_anti_repeticao_outra_chave_nao_bloqueia() -> None:
    assert _decidir(_aval(percorrida=31.0), recentes=[Recente("siga_em_frente", 1.0)]) is not None


def test_anti_repeticao_nao_cai_para_mensagem_de_menor_prioridade() -> None:
    # O perigo foi dito há 2 s: silêncio, e não "Siga em frente." por cima.
    aval = _aval(percorrida=60.0)
    primeira = _decidir(aval, direcao="frente")
    assert primeira is not None
    assert _decidir(aval, direcao="frente", recentes=[Recente(primeira.chave, 2.0)]) is None


def test_perigo_repete_em_intervalo_menor() -> None:
    aval = _aval(percorrida=60.0)
    chave = _decidir(aval).chave
    assert _decidir(aval, recentes=[Recente(chave, 7.9)]) is None
    assert _decidir(aval, recentes=[Recente(chave, 8.0)]) is not None  # < 20 s, mas perigo


def test_silencio_repete_so_no_intervalo() -> None:
    aval = Avaliacao(estado="precisao_insuficiente", confianca="baixa", projecao=None)
    assert _decidir(aval, recentes=[Recente("sem_posicao", 10.0)]) is None
    assert _decidir(aval, recentes=[Recente("sem_posicao", 25.0)]) is not None


def test_obstaculos_dos_trechos_acumula_comprimentos() -> None:
    trechos = [
        {"tipo": "calcada", "comprimento_m": 30.0},
        {"tipo": "escada", "comprimento_m": 10.0},
        {"tipo": "calcada", "comprimento_m": 20.0},
        {"tipo": "travessia", "comprimento_m": 8.0},
    ]
    assert obstaculos_dos_trechos(trechos) == [
        ObstaculoNaRota("escada", 30.0, 40.0),
        ObstaculoNaRota("travessia", 60.0, 68.0),
    ]


@pytest.mark.parametrize("estado", ["na_rota", "chegou", "fora_da_rota"])
def test_nenhuma_mensagem_menciona_via_ou_direcao_de_volta(estado) -> None:
    m = _decidir(_aval(estado=estado, confianca="baixa", percorrida=50.0))
    if m is not None:
        assert "rua" not in m.texto.replace("travessia de rua", "")
