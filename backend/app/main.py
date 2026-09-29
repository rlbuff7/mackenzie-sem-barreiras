"""Ponto de entrada da API do Mackenzie sem Barreiras.

M2: endpoints de referência (`app/routers/referencia.py`) e os estágios 1
(schema) e 2 (geofence) do pipeline na entrada (`POST /alertas`,
`GET /barreiras`). M3: agrupamento e promoção (estágios 3 e 4) em lote e as
estatísticas do funil (`app/routers/validacao.py`).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import obter_configuracoes
from app.db import lifespan
from app.routers import alertas, barreiras, referencia, validacao
from app.validacao.mensagens import traduzir_erros_da_requisicao

app = FastAPI(title="Mackenzie sem Barreiras", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def responder_requisicao_invalida(
    request: Request, erro: RequestValidationError
) -> JSONResponse:
    """422 de parâmetro inválido (bbox ausente, `status`/`origem` fora das opções)
    em português e no formato do resto da API (G5), no lugar do `{"detail": [...]}`
    em inglês do FastAPI. `POST /alertas` não passa por aqui: lê o corpo cru e
    monta o próprio 422 (`app/routers/alertas.py`)."""
    return JSONResponse(
        status_code=422,
        content={
            "mensagem": "Requisição inválida.",
            "erros": traduzir_erros_da_requisicao(erro.errors()),
        },
    )


# CORS é montagem de app (não depende de requisição), então a configuração é
# lida uma vez aqui — diferente das rotas, que sempre pedem `Depends(obter_configuracoes)`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=obter_configuracoes().cors_origens,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(referencia.router)
app.include_router(alertas.router)
app.include_router(barreiras.router)
app.include_router(validacao.router)
