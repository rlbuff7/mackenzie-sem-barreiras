"""Estágios 1 (schema) e 2 (geofence) do pipeline, na entrada (CLAUDE.md §6).

`registrar_alerta` é a fonte única usada por `POST /alertas` (origem="real") e,
a partir do M3, pelo gerador de dados sintéticos (origem="simulacao") — nunca
inserção direta em `alertas`/`alertas_rejeitados` fora daqui (G9). Não faz
commit: quem decide commit/rollback é `obter_conexao` (app/db.py).
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.config import Configuracoes
from app.schemas.alerta import AlertaEntrada, ErroCampo
from app.validacao.geofence import ponto_dentro_da_area
from app.validacao.mensagens import traduzir_erro_pydantic

# Origens aceitas em `alertas.origem` (migration 002, D2). Pública porque o
# pipeline (pipeline.py) e as estatísticas (estatisticas.py) validam contra ela.
ORIGENS_VALIDAS = frozenset({"real", "simulacao"})

MENSAGEM_JSON_MALFORMADO = "JSON malformado."
MENSAGEM_CARACTERE_NAO_GRAVAVEL = (
    "O corpo tem um caractere que não pode ser gravado (U+0000 ou um substituto UTF-16 isolado)."
)

# Erro de schema que não aponta campo nenhum (loc vazio): o corpo inteiro está
# errado, por exemplo um JSON válido que não é objeto (`42`, `[]`, `null`).
_CAMPO_DO_CORPO_INTEIRO = "corpo"


@dataclass
class CorpoInvalido:
    """Marca um corpo de requisição que não é JSON válido (routers/alertas.py).

    `json.loads` só devolve `dict | list | str | int | float | bool | None`
    (RFC 8259) — nunca uma instância desta classe. Por isso o `isinstance`
    em `registrar_alerta` é seguro: nenhum cliente, malicioso ou não, consegue
    enviar um corpo que produza um `CorpoInvalido` por acidente. Antes disso o
    atalho comparava o `payload` a um dict com uma chave-sentinela
    (`{"corpo_invalido": texto}`), o que um cliente podia forjar de propósito
    (ou por coincidência) para escapar da validação de schema de verdade —
    daí a troca para um tipo que o parser de JSON nunca produz.

    `erro` é a mensagem do estágio 1 para o campo `corpo`: JSON malformado, ou
    um JSON válido com um caractere que o PostgreSQL não grava
    (ver `interpretar_corpo`).
    """

    texto: str
    erro: str = MENSAGEM_JSON_MALFORMADO


@dataclass
class ResultadoEntrada:
    """Resultado de `registrar_alerta`: o que o router precisa para responder."""

    aceito: bool
    id: int | None
    status: str | None
    motivo_descarte: str | None
    erros: list[ErroCampo] = field(default_factory=list)


def _recusar_constante_nao_json(nome: str) -> float:
    """`NaN`, `Infinity` e `-Infinity` não são JSON (RFC 8259), mas `json.loads`
    os aceita por padrão. O jsonb do PostgreSQL os recusa: gravar o payload
    rejeitado daria 500. Aqui viram JSON malformado."""
    raise ValueError(f"constante fora do JSON: {nome}")


def _float_finito(texto: str) -> float:
    """`1e999` é JSON válido, mas estoura o float e vira `inf`, com o mesmo
    problema de `Infinity` no jsonb."""
    valor = float(texto)
    if not math.isfinite(valor):
        raise ValueError(f"número fora da faixa do float: {texto}")
    return valor


def _texto_gravavel(texto: str) -> bool:
    """O PostgreSQL não grava U+0000 (nem em TEXT nem em jsonb), e um substituto
    UTF-16 isolado (`\\ud800`) não tem codificação UTF-8. `json.loads` produz os
    dois a partir de escapes válidos (`\\u0000`, `\\ud800`)."""
    if "\x00" in texto:
        return False
    try:
        texto.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _tem_texto_nao_gravavel(payload: object) -> bool:
    """Procura, em chaves e valores de qualquer profundidade, um texto que o
    banco não grava. Iterativo, com pilha própria: o `payload` pode vir do
    `json.loads` com centenas de níveis de aninhamento."""
    pendentes = [payload]
    while pendentes:
        valor = pendentes.pop()
        if isinstance(valor, str):
            if not _texto_gravavel(valor):
                return True
        elif isinstance(valor, dict):
            pendentes.extend(valor.keys())
            pendentes.extend(valor.values())
        elif isinstance(valor, list):
            pendentes.extend(valor)
    return False


def interpretar_corpo(corpo_bruto: bytes, *, tamanho_maximo_texto: int) -> object:
    """Converte o corpo cru de `POST /alertas` no `payload` de `registrar_alerta`.

    Devolve o JSON interpretado quando ele é válido e gravável, mesmo que não
    seja um objeto (`42`, `[]`, `null`): esses são reprovados pelo schema, com
    `campo="corpo"`. Devolve um `CorpoInvalido` (reprovado no estágio 1, com uma
    linha em `alertas_rejeitados`, nunca um 500) quando:

    - o corpo não é JSON: sintaxe, UTF-8 inválido (`UnicodeDecodeError`), número
      com mais dígitos do que o Python aceita (todos são `ValueError`) ou
      aninhamento profundo demais (`RecursionError`);
    - o corpo usa `NaN`, `Infinity`, `-Infinity` ou um número que estoura o float
      (`1e999`), que o jsonb não grava;
    - algum texto (chave ou valor) tem U+0000 ou um substituto UTF-16 isolado,
      que nem jsonb nem TEXT gravam. Decisão: o corpo inteiro é rejeitado com
      uma mensagem própria, em vez de remover o caractere e aceitar um alerta
      diferente do que foi enviado.

    `CorpoInvalido.texto` guarda o corpo cru como texto (UTF-8 com substituição
    dos bytes inválidos), cortado em `tamanho_maximo_texto` caracteres e com
    U+0000 trocado por U+FFFD, para que o próprio registro do rejeitado nunca
    falhe.
    """
    texto = corpo_bruto.decode("utf-8", errors="replace").replace("\x00", "\ufffd")
    texto = texto[:tamanho_maximo_texto]
    try:
        payload = json.loads(
            corpo_bruto, parse_constant=_recusar_constante_nao_json, parse_float=_float_finito
        )
    except (ValueError, RecursionError):
        return CorpoInvalido(texto)
    if _tem_texto_nao_gravavel(payload):
        return CorpoInvalido(texto, erro=MENSAGEM_CARACTERE_NAO_GRAVAVEL)
    return payload


def calcular_sessao_hash(sessao_id: UUID) -> str:
    """sha256 hexadecimal do UUID de sessão (D1).

    Nunca se grava o UUID cru nem qualquer IP: o hash identifica reports da
    mesma origem sem guardar um identificador reversível (LGPD, T3).
    """
    return hashlib.sha256(str(sessao_id).encode()).hexdigest()


def buscar_tipo_ativo(conexao: Connection, codigo: str) -> int | None:
    """Id do tipo de barreira, só se `codigo` existir e estiver ativo (D3)."""
    linha = conexao.execute(
        "SELECT id FROM tipos_barreira WHERE codigo = %(codigo)s AND ativo",
        {"codigo": codigo},
    ).fetchone()
    return linha[0] if linha else None


def registrar_alerta(
    conexao: Connection, payload: object, *, origem: str, config: Configuracoes
) -> ResultadoEntrada:
    """Roda os estágios 1 (schema) e 2 (geofence) sobre `payload`.

    Passos: valida `payload` com `AlertaEntrada`; se passar, confirma que
    `tipo` existe e está ativo; se as duas coisas passarem, roda o geofence
    (estágio 2) e insere em `alertas` com `status='bruto'` (dentro da área) ou
    `status='descartado'` + `motivo_descarte='fora_da_area'` (fora — D4: ainda
    é um alerta aceito, só não vira barreira). Qualquer reprovação no estágio 1
    (schema inválido ou tipo inexistente/inativo) insere o payload em
    `alertas_rejeitados`, nunca em `alertas` (G9), e devolve `aceito=False`.
    Mensagens de erro são sempre traduzidas para português (G5) —
    `ValidationError.errors()` só vem em inglês.

    `payload` sendo um `CorpoInvalido` é o caso especial de corpo de
    requisição que não é JSON válido ou não pode ser gravado
    (`interpretar_corpo`): não há campos individuais para validar, então o erro
    aponta direto `campo="corpo"` em vez de rodar `AlertaEntrada` (que
    produziria erros espúrios de campos "ausentes"). `CorpoInvalido` é um tipo
    dedicado, não um dict com uma chave-sentinela, para que um cliente nunca
    consiga produzir esse atalho através de um JSON de verdade (ver docstring
    da classe). Um JSON válido que não é objeto (`42`, `[]`, `null`) passa pelo
    schema e também é reprovado com `campo="corpo"`.
    """
    if origem not in ORIGENS_VALIDAS:
        raise ValueError(f"origem inválida: {origem!r} (esperado 'real' ou 'simulacao')")

    if isinstance(payload, CorpoInvalido):
        erros = [ErroCampo(campo=_CAMPO_DO_CORPO_INTEIRO, erro=payload.erro)]
        _rejeitar(conexao, {"corpo_invalido": payload.texto}, erros, origem)
        return ResultadoEntrada(
            aceito=False, id=None, status=None, motivo_descarte=None, erros=erros
        )

    try:
        alerta = AlertaEntrada.model_validate(payload)
    except ValidationError as erro_validacao:
        erros = [
            ErroCampo(
                campo=".".join(str(parte) for parte in erro["loc"]) or _CAMPO_DO_CORPO_INTEIRO,
                erro=traduzir_erro_pydantic(erro),
            )
            for erro in erro_validacao.errors()
        ]
        _rejeitar(conexao, payload, erros, origem)
        return ResultadoEntrada(
            aceito=False, id=None, status=None, motivo_descarte=None, erros=erros
        )

    tipo_id = buscar_tipo_ativo(conexao, alerta.tipo)
    if tipo_id is None:
        erros = [ErroCampo(campo="tipo", erro="Tipo de barreira inexistente ou inativo.")]
        _rejeitar(conexao, payload, erros, origem)
        return ResultadoEntrada(
            aceito=False, id=None, status=None, motivo_descarte=None, erros=erros
        )

    dentro_da_area = ponto_dentro_da_area(
        conexao, alerta.latitude, alerta.longitude, config.srid_armazenamento
    )
    status = "bruto" if dentro_da_area else "descartado"
    motivo_descarte = None if dentro_da_area else "fora_da_area"
    sessao_hash = calcular_sessao_hash(alerta.sessao_id)

    linha = conexao.execute(
        """
        INSERT INTO alertas
            (geom, tipo_id, severidade, descricao, sessao_hash, status, motivo_descarte, origem)
        VALUES (
            ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), %(srid)s),
            %(tipo_id)s, %(severidade)s, %(descricao)s, %(sessao_hash)s,
            %(status)s, %(motivo_descarte)s, %(origem)s
        )
        RETURNING id
        """,
        {
            "longitude": alerta.longitude,
            "latitude": alerta.latitude,
            "srid": config.srid_armazenamento,
            "tipo_id": tipo_id,
            "severidade": alerta.severidade,
            "descricao": alerta.descricao,
            "sessao_hash": sessao_hash,
            "status": status,
            "motivo_descarte": motivo_descarte,
            "origem": origem,
        },
    ).fetchone()

    return ResultadoEntrada(
        aceito=True, id=linha[0], status=status, motivo_descarte=motivo_descarte, erros=[]
    )


def _rejeitar(conexao: Connection, payload: object, erros: list[ErroCampo], origem: str) -> None:
    """Grava o payload reprovado no estágio 1 em `alertas_rejeitados` (G9, T1)."""
    conexao.execute(
        """
        INSERT INTO alertas_rejeitados (payload, erros, origem)
        VALUES (%(payload)s, %(erros)s, %(origem)s)
        """,
        {
            "payload": Jsonb(payload),
            "erros": Jsonb([erro.model_dump() for erro in erros]),
            "origem": origem,
        },
    )
