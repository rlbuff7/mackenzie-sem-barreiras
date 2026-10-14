"""Testes das faixas dos parâmetros de validação em `app/config.py` (R15)."""

import pytest
from pydantic import ValidationError

from app.config import Configuracoes


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("DBSCAN_EPS_METROS", "0"),
        ("DBSCAN_EPS_METROS", "-8"),
        ("DBSCAN_MIN_POINTS", "0"),
        ("MIN_CONFIRMACOES", "0"),
    ],
)
def test_parametro_de_validacao_fora_da_faixa_e_recusado_na_leitura(
    monkeypatch: pytest.MonkeyPatch, variavel: str, valor: str
) -> None:
    """Um `.env` com valor sem sentido falha ao subir a API, não na primeira
    execução do pipeline. A variável de ambiente tem prioridade sobre o `.env`."""
    monkeypatch.setenv(variavel, valor)

    with pytest.raises(ValidationError):
        Configuracoes()


def test_parametros_do_env_do_projeto_sao_aceitos() -> None:
    configuracoes = Configuracoes()

    assert configuracoes.dbscan_eps_metros > 0
    assert configuracoes.dbscan_min_points >= 1
    assert configuracoes.min_confirmacoes >= 1


def test_codigo_da_equipe_da_medicao_vem_vazio_por_padrao() -> None:
    """Vazio = medição desligada no servidor (`POST /medicoes` responde 503)."""
    assert Configuracoes.model_fields["medicao_codigo_equipe"].default == ""


def test_codigo_da_equipe_da_medicao_e_lido_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDICAO_CODIGO_EQUIPE", "codigo-de-teste")

    assert Configuracoes().medicao_codigo_equipe == "codigo-de-teste"
