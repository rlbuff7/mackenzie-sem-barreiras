"""Fator de custo dos trechos de rota (app/rotas/custo.py) e a configuração que o alimenta."""

import pytest
from pydantic import ValidationError

from app.config import Configuracoes
from app.rotas.custo import fator_do_trecho, trecho_proibido


@pytest.fixture
def config() -> Configuracoes:
    return Configuracoes(
        penalidade_escada=4.0, penalidade_travessia=2.0, penalidade_trecho_nao_verificado=1.5
    )


def _fator(config, **kw):
    base = dict(
        tipo="calcada",
        acessivel_cadeirante=True,
        fonte_verificacao="conferido_a_pe",
        perfil="sem_restricao",
    )
    return fator_do_trecho(config=config, **{**base, **kw})


def test_escada_pesa_penalidade_e_rampa_nao(config):
    assert _fator(config, tipo="escada", acessivel_cadeirante=False) == config.penalidade_escada
    assert _fator(config, tipo="rampa") == 1.0


def test_travessia_pesa_penalidade(config):
    assert _fator(config, tipo="travessia") == config.penalidade_travessia


def test_trecho_nao_conferido_a_pe_pesa_mais(config):
    base = _fator(config)
    for fonte in ("imagem", "provisorio"):
        assert (
            _fator(config, fonte_verificacao=fonte)
            == base * config.penalidade_trecho_nao_verificado
        )


def test_cadeirante_nunca_usa_escada_nem_trecho_inacessivel(config):
    assert trecho_proibido(tipo="escada", acessivel_cadeirante=None, perfil="cadeirante")
    assert trecho_proibido(tipo="escada", acessivel_cadeirante=False, perfil="cadeirante")
    assert trecho_proibido(tipo="calcada", acessivel_cadeirante=False, perfil="cadeirante")
    assert not trecho_proibido(tipo="calcada", acessivel_cadeirante=None, perfil="cadeirante")
    assert not trecho_proibido(tipo="calcada", acessivel_cadeirante=True, perfil="cadeirante")


def test_sem_restricao_pode_usar_escada(config):
    assert not trecho_proibido(tipo="escada", acessivel_cadeirante=False, perfil="sem_restricao")


def test_fator_de_trecho_proibido_levanta_erro_em_vez_de_inventar_custo(config):
    with pytest.raises(ValueError):
        _fator(config, tipo="escada", acessivel_cadeirante=False, perfil="cadeirante")


def test_cadeirante_em_trecho_nao_verificado_de_acessibilidade_pesa_mais(config):
    sim = _fator(config, perfil="cadeirante", acessivel_cadeirante=True)
    nao_sabe = _fator(config, perfil="cadeirante", acessivel_cadeirante=None)
    assert nao_sabe == sim * config.penalidade_trecho_nao_verificado


@pytest.mark.parametrize(
    "variavel",
    ["PENALIDADE_ESCADA", "PENALIDADE_TRAVESSIA", "PENALIDADE_TRECHO_NAO_VERIFICADO"],
)
@pytest.mark.parametrize("valor", ["0", "-1"])
def test_penalidade_menor_ou_igual_a_zero_e_recusada(monkeypatch, variavel, valor):
    monkeypatch.setenv(variavel, valor)
    with pytest.raises(ValidationError):
        Configuracoes()


def test_limite_de_pontos_de_interesse_tem_padrao_500():
    assert Configuracoes.model_fields["limite_pontos_interesse_por_consulta"].default == 500
