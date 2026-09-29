"""Ponto de entrada da API do Mackenzie sem Barreiras.

M2: endpoints de referência (`app/routers/referencia.py`) e os estágios 1
(schema) e 2 (geofence) do pipeline na entrada (`POST /alertas`,
`GET /barreiras`). M3: agrupamento e promoção (estágios 3 e 4) em lote e as
estatísticas do funil (`app/routers/validacao.py`).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import obter_configuracoes
from app.db import lifespan
from app.routers import alertas, barreiras, referencia, validacao

app = FastAPI(title="Mackenzie sem Barreiras", lifespan=lifespan)

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
