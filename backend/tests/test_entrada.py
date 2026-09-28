"""Testes dos estágios 1 (schema) e 2 (geofence) na entrada: `app/validacao/entrada.py`."""

import hashlib
from uuid import uuid4

import psycopg
import pytest

from app.config import obter_configuracoes
from app.schemas.alerta import ErroCampo
from app.validacao.entrada import (
    CorpoInvalido,
    buscar_tipo_ativo,
    calcular_sessao_hash,
    registrar_alerta,
)

_DENTRO_DA_AREA = {"latitude": -23.5471938, "longitude": -46.6524631}
_FORA_DA_AREA = {"latitude": -23.5614, "longitude": -46.6558}


def _payload(**sobrescritas: object) -> dict:
    base: dict[str, object] = {
        **_DENTRO_DA_AREA,
        "tipo": "degrau",
        "severidade": 2,
        "descricao": "degrau alto na entrada",
        "sessao_id": str(uuid4()),
    }
    base.update(sobrescritas)
    return base


# --- calcular_sessao_hash (D1) ---


def test_calcular_sessao_hash_e_o_sha256_do_uuid() -> None:
    sessao_id = uuid4()

    hash_calculado = calcular_sessao_hash(sessao_id)

    assert hash_calculado == hashlib.sha256(str(sessao_id).encode()).hexdigest()
    assert hash_calculado != str(sessao_id)


def test_calcular_sessao_hash_e_estavel_para_a_mesma_sessao() -> None:
    sessao_id = uuid4()

    assert calcular_sessao_hash(sessao_id) == calcular_sessao_hash(sessao_id)


# --- buscar_tipo_ativo (D3) ---


def test_buscar_tipo_ativo_encontra_tipo_do_seed(conexao: psycopg.Connection) -> None:
    assert buscar_tipo_ativo(conexao, "degrau") is not None


def test_buscar_tipo_ativo_none_para_codigo_inexistente(conexao: psycopg.Connection) -> None:
    assert buscar_tipo_ativo(conexao, "tipo_que_nao_existe") is None


def test_buscar_tipo_ativo_none_para_tipo_inativo(conexao: psycopg.Connection) -> None:
    conexao.execute("UPDATE tipos_barreira SET ativo = false WHERE codigo = 'degrau'")

    assert buscar_tipo_ativo(conexao, "degrau") is None


# --- registrar_alerta: aceitos ---


def test_registrar_alerta_valido_dentro_da_area_vira_bruto(conexao: psycopg.Connection) -> None:
    config = obter_configuracoes()

    resultado = registrar_alerta(conexao, _payload(), origem="real", config=config)

    assert resultado.aceito is True
    assert resultado.status == "bruto"
    assert resultado.motivo_descarte is None
    assert resultado.erros == []
    linha = conexao.execute(
        "SELECT status, motivo_descarte, origem FROM alertas WHERE id = %s",
        (resultado.id,),
    ).fetchone()
    assert linha == ("bruto", None, "real")


def test_registrar_alerta_valido_fora_da_area_vira_descartado(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()

    resultado = registrar_alerta(conexao, _payload(**_FORA_DA_AREA), origem="real", config=config)

    assert resultado.aceito is True
    assert resultado.status == "descartado"
    assert resultado.motivo_descarte == "fora_da_area"
    linha = conexao.execute(
        "SELECT status, motivo_descarte FROM alertas WHERE id = %s",
        (resultado.id,),
    ).fetchone()
    assert linha == ("descartado", "fora_da_area")


def test_registrar_alerta_origem_simulacao_e_gravada(conexao: psycopg.Connection) -> None:
    config = obter_configuracoes()

    resultado = registrar_alerta(conexao, _payload(), origem="simulacao", config=config)

    origem = conexao.execute(
        "SELECT origem FROM alertas WHERE id = %s", (resultado.id,)
    ).fetchone()[0]
    assert origem == "simulacao"


def test_registrar_alerta_descricao_vazia_vira_null(conexao: psycopg.Connection) -> None:
    config = obter_configuracoes()

    resultado = registrar_alerta(conexao, _payload(descricao="   "), origem="real", config=config)

    descricao = conexao.execute(
        "SELECT descricao FROM alertas WHERE id = %s", (resultado.id,)
    ).fetchone()[0]
    assert descricao is None


def test_registrar_alerta_grava_sha256_da_sessao_nao_o_uuid_cru(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()
    sessao_id = uuid4()

    resultado = registrar_alerta(
        conexao, _payload(sessao_id=str(sessao_id)), origem="real", config=config
    )

    sessao_hash = conexao.execute(
        "SELECT sessao_hash FROM alertas WHERE id = %s", (resultado.id,)
    ).fetchone()[0]
    assert sessao_hash == calcular_sessao_hash(sessao_id)
    assert sessao_hash != str(sessao_id)


def test_registrar_alerta_mesma_sessao_produz_o_mesmo_hash(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()
    sessao_id = str(uuid4())

    primeiro = registrar_alerta(
        conexao, _payload(sessao_id=sessao_id), origem="real", config=config
    )
    segundo = registrar_alerta(conexao, _payload(sessao_id=sessao_id), origem="real", config=config)

    linhas = conexao.execute(
        "SELECT sessao_hash FROM alertas WHERE id IN (%s, %s)",
        (primeiro.id, segundo.id),
    ).fetchall()
    assert linhas[0][0] == linhas[1][0]


# --- registrar_alerta: reprovados no estágio 1 (schema) ---


@pytest.mark.parametrize(
    ("sobrescritas", "campo_esperado", "mensagem_esperada"),
    [
        ({"latitude": 200}, "latitude", "Deve ser menor ou igual a 90.0."),
        (
            {"tipo": "tipo_que_nao_existe"},
            "tipo",
            "Tipo de barreira inexistente ou inativo.",
        ),
        ({"severidade": 7}, "severidade", "Deve ser menor ou igual a 3."),
        (
            {"campo_extra": "nao_deveria_existir"},
            "campo_extra",
            "Campo desconhecido: não é aceito neste formulário.",
        ),
        ({"sessao_id": "nao-e-um-uuid"}, "sessao_id", "Não é um UUID válido."),
    ],
    ids=[
        "latitude_fora_da_faixa",
        "tipo_inexistente",
        "severidade_fora_da_faixa",
        "campo_extra",
        "sessao_id_invalido",
    ],
)
def test_registrar_alerta_reprovado_vai_para_rejeitados_com_mensagem_em_portugues(
    conexao: psycopg.Connection,
    sobrescritas: dict,
    campo_esperado: str,
    mensagem_esperada: str,
) -> None:
    """G5: a mensagem de erro nunca é o inglês nativo do Pydantic."""
    config = obter_configuracoes()
    antes = conexao.execute("SELECT count(*) FROM alertas_rejeitados").fetchone()[0]

    resultado = registrar_alerta(conexao, _payload(**sobrescritas), origem="real", config=config)

    assert resultado.aceito is False
    erros_por_campo = {erro.campo: erro.erro for erro in resultado.erros}
    assert erros_por_campo[campo_esperado] == mensagem_esperada
    depois = conexao.execute("SELECT count(*) FROM alertas_rejeitados").fetchone()[0]
    assert depois == antes + 1


def test_registrar_alerta_payload_com_chave_corpo_invalido_e_validado_normalmente(
    conexao: psycopg.Connection,
) -> None:
    """Um payload de verdade que por acaso usa a chave `corpo_invalido` (um dict
    comum, não a marca `CorpoInvalido`) passa pela validação normal contra
    `AlertaEntrada` — só uma instância de `CorpoInvalido` (produzida por
    `routers/alertas.py` quando o corpo cru não é JSON válido) aciona o atalho
    de "corpo malformado". Isso prova que o atalho não colide com um payload
    de cliente que só coincida com o formato interno."""
    config = obter_configuracoes()

    resultado = registrar_alerta(conexao, {"corpo_invalido": "x"}, origem="real", config=config)

    assert resultado.aceito is False
    campos = {erro.campo for erro in resultado.erros}
    assert "corpo" not in campos
    assert "corpo_invalido" in campos  # campo extra, rejeitado por extra="forbid"
    assert "latitude" in campos  # campo obrigatório ausente


def test_registrar_alerta_corpo_invalido_grava_erro_no_campo_corpo(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()

    resultado = registrar_alerta(
        conexao, CorpoInvalido("{isso nao e json"), origem="real", config=config
    )

    assert resultado.aceito is False
    assert resultado.erros == [ErroCampo(campo="corpo", erro="JSON malformado.")]
    payload_gravado = conexao.execute(
        "SELECT payload FROM alertas_rejeitados ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert payload_gravado == {"corpo_invalido": "{isso nao e json"}


def test_registrar_alerta_tipo_inativo_vai_para_rejeitados(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()
    conexao.execute("UPDATE tipos_barreira SET ativo = false WHERE codigo = 'degrau'")

    resultado = registrar_alerta(conexao, _payload(), origem="real", config=config)

    assert resultado.aceito is False
    assert resultado.erros[0].campo == "tipo"


def test_registrar_alerta_erro_aponta_o_campo_da_latitude(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()

    resultado = registrar_alerta(conexao, _payload(latitude=200), origem="real", config=config)

    campos = {erro.campo for erro in resultado.erros}
    assert "latitude" in campos


def test_registrar_alerta_origem_invalida_levanta_value_error(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()

    with pytest.raises(ValueError):
        registrar_alerta(conexao, _payload(), origem="rascunho", config=config)
