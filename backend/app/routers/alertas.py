"""`POST /alertas` (Contrato da API): estágios 1 (schema) e 2 (geofence) na entrada.

Rota `async` porque precisa ler o CORPO CRU da requisição, em fluxo com teto de
`LIMITE_CORPO_BYTES` (`_ler_corpo_limitado`: confere o Content-Length e corta a
leitura; acima do teto, 413), antes de qualquer parse: um corpo que não é JSON válido ainda
precisa virar uma linha em `alertas_rejeitados` (contagem do funil), e o parse
automático de corpo do FastAPI responderia 422 sozinho, sem passar por
`registrar_alerta` — por isso a rota não declara `payload: AlertaEntrada` como
parâmetro. A interpretação do corpo cru fica em
`app/validacao/entrada.py::interpretar_corpo`, que faz todo corpo impossível de
gravar (UTF-8 inválido, `NaN`, U+0000...) virar reprovação do estágio 1, nunca 500.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.schemas.alerta import AlertaRegistrado
from app.validacao.entrada import interpretar_corpo, registrar_alerta

router = APIRouter()

# Corpo malformado vira `alertas_rejeitados.payload` (JSONB); um corpo enorme
# não deveria inflar essa tabela, então o texto cru é truncado (Contrato).
_TAMANHO_MAXIMO_CORPO_INVALIDO = 2000

_MENSAGENS_POR_STATUS = {
    "bruto": "Alerta recebido. Ele será validado quando outras pessoas confirmarem.",
    "descartado": "O ponto está fora da área de estudo do projeto.",
}


def _mensagem_corpo_grande(limite_bytes: int) -> str:
    limite = f"{limite_bytes // 1024} KiB" if limite_bytes % 1024 == 0 else f"{limite_bytes} bytes"
    return f"Corpo grande demais: o limite é {limite}."


async def _ler_corpo_limitado(request: Request, limite_bytes: int) -> bytes | None:
    """Corpo cru da requisição, ou `None` se passar de `limite_bytes`.

    Confere o `Content-Length` antes de ler qualquer byte e, como o cabeçalho
    pode faltar (transferência em pedaços) ou mentir, também corta a leitura do
    fluxo assim que o acumulado passa do limite: um corpo enorme nunca é
    inteiro para a memória. Nada é gravado (abuso, não relato).
    """
    declarado = request.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > limite_bytes:
        return None
    pedacos: list[bytes] = []
    total = 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > limite_bytes:
            return None
        pedacos.append(pedaco)
    return b"".join(pedacos)


@router.post("/alertas", status_code=201, response_model=AlertaRegistrado)
async def criar_alerta(
    request: Request,
    conexao: ConexaoDaRequisicao,
    config: Configuracoes = Depends(obter_configuracoes),
) -> AlertaRegistrado | JSONResponse:
    corpo_bruto = await _ler_corpo_limitado(request, config.limite_corpo_bytes)
    if corpo_bruto is None:
        return JSONResponse(
            status_code=413,
            content={"mensagem": _mensagem_corpo_grande(config.limite_corpo_bytes)},
        )
    # Um corpo que não se pode gravar vira um `CorpoInvalido`, tipo dedicado
    # (não um dict com chave-sentinela): `json.loads` nunca devolve uma
    # instância dele, então um cliente não consegue forjar este atalho enviando
    # `{"corpo_invalido": "..."}` de propósito — esse corpo, sendo JSON válido,
    # é validado normalmente contra `AlertaEntrada`.
    payload = interpretar_corpo(corpo_bruto, tamanho_maximo_texto=_TAMANHO_MAXIMO_CORPO_INVALIDO)

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
