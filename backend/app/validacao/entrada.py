"""Estágios 1 (schema) e 2 (geofence) do pipeline, na entrada (CLAUDE.md §6).

`registrar_alerta` é a fonte única usada por `POST /alertas` (origem="real") e,
a partir do M3, pelo gerador de dados sintéticos (origem="simulacao") — nunca
inserção direta em `alertas`/`alertas_rejeitados` fora daqui (G9). Não faz
commit: quem decide commit/rollback é `obter_conexao` (app/db.py).
"""

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.config import Configuracoes
from app.schemas.alerta import AlertaEntrada, ErroCampo
from app.validacao.geofence import ponto_dentro_da_area

_ORIGENS_VALIDAS = {"real", "simulacao"}

# Chave-sentinela que `routers/alertas.py` usa para embrulhar um corpo de
# requisição que não é sequer JSON válido (ver docstring de `registrar_alerta`
# sobre o tratamento desse caso).
_CHAVE_CORPO_INVALIDO = "corpo_invalido"


@dataclass
class ResultadoEntrada:
    """Resultado de `registrar_alerta`: o que o router precisa para responder."""

    aceito: bool
    id: int | None
    status: str | None
    motivo_descarte: str | None
    erros: list[ErroCampo] = field(default_factory=list)


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
    (schema inválido ou tipo inexistente/inativo) insere `payload` cru em
    `alertas_rejeitados`, nunca em `alertas` (G9), e devolve `aceito=False`.

    `payload` no formato `{"corpo_invalido": <texto>}` é o caso especial de
    corpo de requisição que não é JSON válido (routers/alertas.py): não há
    campos individuais para validar, então o erro aponta direto `campo="corpo"`
    em vez de rodar `AlertaEntrada` (que produziria erros espúrios de campos
    "ausentes").
    """
    if origem not in _ORIGENS_VALIDAS:
        raise ValueError(f"origem inválida: {origem!r} (esperado 'real' ou 'simulacao')")

    if isinstance(payload, dict) and set(payload) == {_CHAVE_CORPO_INVALIDO}:
        erros = [ErroCampo(campo="corpo", erro="JSON malformado.")]
        _rejeitar(conexao, payload, erros, origem)
        return ResultadoEntrada(
            aceito=False, id=None, status=None, motivo_descarte=None, erros=erros
        )

    try:
        alerta = AlertaEntrada.model_validate(payload)
    except ValidationError as erro_validacao:
        erros = [
            ErroCampo(campo=".".join(str(parte) for parte in erro["loc"]), erro=erro["msg"])
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
