"""Testes da tradução de erros do Pydantic para português: `app/validacao/mensagens.py`.

G5: mensagens de erro nunca vazam o inglês nativo do Pydantic (`erro["msg"]`).
"""

import pytest

from app.validacao.mensagens import traduzir_erro_pydantic, traduzir_erros_da_requisicao


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
        ({"type": "less_than_equal", "ctx": {"le": 90.0}}, "Deve ser menor ou igual a 90."),
        ({"type": "less_than_equal", "ctx": {"le": 3}}, "Deve ser menor ou igual a 3."),
        ({"type": "greater_than_equal", "ctx": {"ge": -90}}, "Deve ser maior ou igual a -90."),
        # Padrão brasileiro: sem ".0" à toa e com vírgula decimal.
        (
            {"type": "greater_than_equal", "ctx": {"ge": -180.0}},
            "Deve ser maior ou igual a -180.",
        ),
        ({"type": "less_than", "ctx": {"lt": 0.5}}, "Deve ser menor que 0,5."),
        ({"type": "greater_than", "ctx": {"gt": -46.25}}, "Deve ser maior que -46,25."),
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
        (
            {"type": "literal_error", "ctx": {"expected": "'real' or 'simulacao'"}},
            "Deve ser um destes valores: 'real' ou 'simulacao'.",
        ),
        (
            {"type": "literal_error", "ctx": {"expected": "'a', 'b' or 'c'"}},
            "Deve ser um destes valores: 'a', 'b' ou 'c'.",
        ),
        # value_error: o ValueError de um validador deste projeto, já em português.
        (
            {"type": "value_error", "ctx": {"error": ValueError("bbox inválido.")}},
            "bbox inválido.",
        ),
    ],
)
def test_traduzir_erro_pydantic(erro: dict, mensagem_esperada: str) -> None:
    assert traduzir_erro_pydantic(erro) == mensagem_esperada


def test_traduzir_erro_pydantic_nunca_devolve_o_msg_em_ingles() -> None:
    erro = {"type": "less_than_equal", "ctx": {"le": 90.0}, "msg": "Input should be <= 90"}

    assert traduzir_erro_pydantic(erro) != erro["msg"]


def test_traduzir_erros_da_requisicao_tira_a_origem_do_parametro_do_campo() -> None:
    """`loc` do FastAPI começa pela parte da requisição (`query`, `path`...); o
    campo do Contrato é só o nome do parâmetro, como no `POST /alertas`."""
    erros = [
        {"type": "missing", "loc": ("query", "bbox"), "msg": "Field required"},
        {
            "type": "literal_error",
            "loc": ("query", "status"),
            "msg": "Input should be 'pendente' or 'confirmada'",
            "ctx": {"expected": "'pendente' or 'confirmada'"},
        },
        {"type": "missing", "loc": ("header", "x-token-admin"), "msg": "Field required"},
    ]

    assert traduzir_erros_da_requisicao(erros) == [
        {"campo": "bbox", "erro": "Campo obrigatório."},
        {"campo": "status", "erro": "Deve ser um destes valores: 'pendente' ou 'confirmada'."},
        {"campo": "x-token-admin", "erro": "Campo obrigatório."},
    ]


def test_traduzir_erros_da_requisicao_mantem_loc_sem_origem_conhecida() -> None:
    erros = [{"type": "missing", "loc": ("corpo", "latitude")}, {"type": "missing", "loc": ()}]

    assert traduzir_erros_da_requisicao(erros) == [
        {"campo": "corpo.latitude", "erro": "Campo obrigatório."},
        {"campo": "corpo", "erro": "Campo obrigatório."},
    ]
