"""`POST /alertas` (Contrato da API): estágios 1 (schema) e 2 (geofence) na entrada.

Rota `async` porque precisa ler o CORPO CRU da requisição (`await
request.body()`) antes de qualquer parse: um corpo que não é JSON válido ainda
precisa virar uma linha em `alertas_rejeitados` (contagem do funil), e o parse
automático de corpo do FastAPI responderia 422 sozinho, sem passar por
`registrar_alerta` — por isso a rota não declara `payload: AlertaEntrada` como
parâmetro.
"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg import Connection

from app.config import Configuracoes, obter_configuracoes
from app.db import obter_conexao
from app.schemas.alerta import AlertaRegistrado
from app.validacao.entrada import registrar_alerta

router = APIRouter()

# Corpo malformado vira `alertas_rejeitados.payload` (JSONB); um corpo enorme
# não deveria inflar essa tabela, então o texto cru é truncado (Contrato).
_TAMANHO_MAXIMO_CORPO_INVALIDO = 2000

_MENSAGENS_POR_STATUS = {
    "bruto": "Alerta recebido. Ele será validado quando outras pessoas confirmarem.",
    "descartado": "O ponto está fora da área de estudo do projeto.",
}


@router.post("/alertas", status_code=201, response_model=AlertaRegistrado)
async def criar_alerta(
    request: Request,
    conexao: Connection = Depends(obter_conexao),
    config: Configuracoes = Depends(obter_configuracoes),
) -> AlertaRegistrado | JSONResponse:
    corpo_bruto = await request.body()
    try:
        payload = json.loads(corpo_bruto)
    except json.JSONDecodeError:
        texto = corpo_bruto.decode("utf-8", errors="replace")
        payload = {"corpo_invalido": texto[:_TAMANHO_MAXIMO_CORPO_INVALIDO]}

    # `registrar_alerta` faz I/O de banco síncrono (psycopg); roda fora do
    # event loop para não bloquear as outras requisições.
    resultado = await run_in_threadpool(
        registrar_alerta, conexao, payload, origem="real", config=config
    )

    if not resultado.aceito:
        # Devolver uma Response explícita ignora o `response_model` da rota
        # (o Contrato do 422 não é AlertaRegistrado, é {mensagem, erros}).
        return JSONResponse(
            status_code=422,
            content={
                "mensagem": "Alerta inválido.",
                "erros": [erro.model_dump() for erro in resultado.erros],
            },
        )

    return AlertaRegistrado(
        id=resultado.id,
        status=resultado.status,
        motivo_descarte=resultado.motivo_descarte,
        mensagem=_MENSAGENS_POR_STATUS[resultado.status],
    )
