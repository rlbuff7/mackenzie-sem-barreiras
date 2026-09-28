"""Ponto de entrada da API do Mackenzie sem Barreiras.

M2: fundação e endpoints de referência (`app/routers/referencia.py`). Ainda sem
lógica de validação — isso entra no M3, em `app/validacao/`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import obter_configuracoes
from app.db import lifespan
from app.routers import referencia

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
