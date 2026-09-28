"""Testes da tradução de erros do Pydantic para português: `app/validacao/mensagens.py`.

G5: mensagens de erro nunca vazam o inglês nativo do Pydantic (`erro["msg"]`).
"""

import pytest

from app.validacao.mensagens import traduzir_erro_pydantic


@pytest.mark.parametrize(
    ("erro", "mensagem_esperada"),
    [
        ({"type": "missing", "ctx": None}, "Campo obrigatório."),
        (
            {"type": "extra_forbidden", "ctx": None},
            "Campo desconhecido: não é aceito neste formulário.",
        ),
        ({"type": "uuid_parsing", "ctx": {"error": "..."}}, "Não é um UUID válido."),
        ({"type": "uuid_type", "ctx": None}, "Deve ser um UUID (texto)."),
        ({"type": "string_type", "ctx": None}, "Deve ser um texto."),
        ({"type": "int_type", "ctx": None}, "Deve ser um número inteiro."),
        ({"type": "float_type", "ctx": None}, "Deve ser um número."),
        ({"type": "int_parsing", "ctx": None}, "Não é um número inteiro válido."),
        ({"type": "float_parsing", "ctx": None}, "Não é um número válido."),
        ({"type": "bool_parsing", "ctx": None}, "Não é um valor verdadeiro/falso válido."),
        ({"type": "bool_type", "ctx": None}, "Deve ser verdadeiro ou falso."),
        ({"type": "model_type", "ctx": None}, "Deve ser um objeto JSON (chave-valor)."),
        ({"type": "dict_type", "ctx": None}, "Deve ser um objeto JSON (chave-valor)."),
        ({"type": "json_invalid", "ctx": None}, "JSON malformado."),
        ({"type": "less_than_equal", "ctx": {"le": 90.0}}, "Deve ser menor ou igual a 90.0."),
        ({"type": "less_than_equal", "ctx": {"le": 3}}, "Deve ser menor ou igual a 3."),
        ({"type": "greater_than_equal", "ctx": {"ge": -90}}, "Deve ser maior ou igual a -90."),
        ({"type": "less_than", "ctx": {"lt": 10}}, "Deve ser menor que 10."),
        ({"type": "greater_than", "ctx": {"gt": 0}}, "Deve ser maior que 0."),
        (
            {"type": "string_too_long", "ctx": {"max_length": 500}},
            "Deve ter no máximo 500 caracteres.",
        ),
        (
            {"type": "string_too_short", "ctx": {"min_length": 1}},
            "Deve ter no mínimo 1 caracteres.",
        ),
        (
            {"type": "string_pattern_mismatch", "ctx": {"pattern": "^[a-z_]+$"}},
            "Não corresponde ao formato esperado (^[a-z_]+$).",
        ),
        # Tipo desconhecido: cai no fallback, nunca no `msg` em inglês do Pydantic.
        (
            {"type": "algum_tipo_novo_do_pydantic", "ctx": None, "msg": "some english text"},
            "Valor inválido.",
        ),
        ({"type": "less_than_equal", "ctx": None}, "Valor inválido."),  # ctx incompleto
    ],
)
def test_traduzir_erro_pydantic(erro: dict, mensagem_esperada: str) -> None:
    assert traduzir_erro_pydantic(erro) == mensagem_esperada


def test_traduzir_erro_pydantic_nunca_devolve_o_msg_em_ingles() -> None:
    erro = {"type": "less_than_equal", "ctx": {"le": 90.0}, "msg": "Input should be <= 90"}

    assert traduzir_erro_pydantic(erro) != erro["msg"]
