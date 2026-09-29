"""Tradução de erros do Pydantic para mensagens em português (G5).

`ValidationError.errors()` só devolve `msg` em inglês — não há como configurar
uma _locale_ no Pydantic v2. G5 exige mensagens em português em toda a API, e o
Contrato nunca expõe o inglês do Pydantic num 422. `traduzir_erro_pydantic`
mapeia o campo `type` de cada erro (estável entre versões do Pydantic, ao
contrário de `msg`, que muda de texto livremente) para uma frase em português,
usando `ctx` para preencher limites (ex.: `le`, `max_length`).

Tipo de erro não mapeado cai no fallback genérico — nunca vaza `erro["msg"]`
em inglês para a resposta.

`traduzir_erros_da_requisicao` aplica a mesma tradução aos erros de validação
de parâmetros das rotas (query), que o FastAPI levanta como
`RequestValidationError` e o handler de `app/main.py` devolve em português.
"""

from collections.abc import Iterable
from typing import Any

_MENSAGEM_PADRAO = "Valor inválido."

# Erros sem parâmetro nenhum: mensagem fixa.
_MENSAGENS_FIXAS: dict[str, str] = {
    "missing": "Campo obrigatório.",
    "extra_forbidden": "Campo desconhecido: não é aceito neste formulário.",
    "uuid_parsing": "Não é um UUID válido.",
    "uuid_type": "Deve ser um UUID (texto).",
    "string_type": "Deve ser um texto.",
    "int_type": "Deve ser um número inteiro.",
    "float_type": "Deve ser um número.",
    "int_parsing": "Não é um número inteiro válido.",
    "float_parsing": "Não é um número válido.",
    "bool_parsing": "Não é um valor verdadeiro/falso válido.",
    "bool_type": "Deve ser verdadeiro ou falso.",
    "none_required": "Deve ser nulo.",
    "model_type": "Deve ser um objeto JSON (chave-valor).",
    "dict_type": "Deve ser um objeto JSON (chave-valor).",
    "json_invalid": "JSON malformado.",
}

# Erros que citam um limite do `ctx`: mensagem montada em cima do valor real
# do `Field` (nunca hardcoded aqui — vem do próprio erro do Pydantic).
_MENSAGENS_COM_LIMITE: dict[str, Any] = {
    "less_than_equal": lambda ctx: f"Deve ser menor ou igual a {ctx['le']}.",
    "greater_than_equal": lambda ctx: f"Deve ser maior ou igual a {ctx['ge']}.",
    "less_than": lambda ctx: f"Deve ser menor que {ctx['lt']}.",
    "greater_than": lambda ctx: f"Deve ser maior que {ctx['gt']}.",
    "string_too_long": lambda ctx: f"Deve ter no máximo {ctx['max_length']} caracteres.",
    "string_too_short": lambda ctx: f"Deve ter no mínimo {ctx['min_length']} caracteres.",
    "string_pattern_mismatch": lambda ctx: (
        f"Não corresponde ao formato esperado ({ctx['pattern']})."
    ),
    # `expected` vem do Pydantic como "'a', 'b' or 'c'": só o "or" é inglês.
    "literal_error": lambda ctx: (
        f"Deve ser um destes valores: {ctx['expected'].replace(' or ', ' ou ')}."
    ),
    # O ValueError de um validador DESTE projeto (ex.: o bbox de GET /barreiras),
    # cuja mensagem já é escrita em português. Os validadores do próprio Pydantic
    # usam tipos específicos, nunca `value_error`.
    "value_error": lambda ctx: str(ctx["error"]),
}

# Primeiro elemento do `loc` de um erro de parâmetro: a parte da requisição.
_PARTES_DA_REQUISICAO = frozenset({"query", "path", "header", "cookie", "body"})


def traduzir_erro_pydantic(erro: dict[str, Any]) -> str:
    """Mensagem em português para um item de `ValidationError.errors()`.

    `erro` é o dicionário que o Pydantic devolve por erro (tem `type`, `loc`,
    `msg`, `ctx`, `input`); só `type` e `ctx` são usados aqui — `msg` (inglês)
    nunca é lido.
    """
    tipo = erro.get("type", "")

    if tipo in _MENSAGENS_FIXAS:
        return _MENSAGENS_FIXAS[tipo]

    if tipo in _MENSAGENS_COM_LIMITE:
        ctx = erro.get("ctx") or {}
        try:
            return _MENSAGENS_COM_LIMITE[tipo](ctx)
        except KeyError:
            return _MENSAGEM_PADRAO

    return _MENSAGEM_PADRAO


def traduzir_erros_da_requisicao(erros: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """`[{"campo", "erro"}]` em português para os erros de um `RequestValidationError`.

    O `campo` é o nome do parâmetro, sem a parte da requisição que o FastAPI põe
    no começo do `loc` (`("query", "bbox")` vira `"bbox"`), no mesmo formato dos
    erros de `POST /alertas`. Um `loc` vazio aponta o corpo inteiro (`"corpo"`).
    """
    traduzidos = []
    for erro in erros:
        partes = [str(parte) for parte in erro.get("loc", ())]
        if len(partes) > 1 and partes[0] in _PARTES_DA_REQUISICAO:
            partes = partes[1:]
        traduzidos.append(
            {"campo": ".".join(partes) or "corpo", "erro": traduzir_erro_pydantic(erro)}
        )
    return traduzidos
