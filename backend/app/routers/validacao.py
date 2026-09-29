"""`POST /validacao/executar` e `GET /validacao/estatisticas` (Contrato da API).

A lógica fica em `app/validacao/` (`pipeline.py`, `estatisticas.py`). Este módulo só
traduz HTTP: passa os parâmetros da configuração para a execução, protege a execução
com o token de administrador (D7) e devolve o JSON do Contrato. As estatísticas não
recebem parâmetros da configuração: mostram os da última execução (R14).
"""

import secrets
from dataclasses import asdict
from datetime import UTC
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.validacao.estatisticas import calcular_estatisticas
from app.validacao.pipeline import executar_pipeline

router = APIRouter(prefix="/validacao")


def exigir_token_admin(
    x_token_admin: Annotated[str | None, Header()] = None,
    config: Configuracoes = Depends(obter_configuracoes),
) -> None:
    """Exige o header `X-Token-Admin` igual a `TOKEN_ADMIN` quando ele está
    configurado (D7). `TOKEN_ADMIN` vazio deixa a rota aberta, só em
    desenvolvimento.

    Executar o pipeline apaga e recria todas as barreiras de uma origem (D6).
    Não é algo que qualquer visitante do mapa deva poder disparar.

    `secrets.compare_digest` compara em tempo constante: uma comparação comum
    (`==`) para no primeiro caractere diferente, e o tempo de resposta
    revelaria aos poucos quantos caracteres do token estão certos. Os dois lados
    viram bytes porque `compare_digest` só aceita `str` ASCII.

    Esta dependência entra em `dependencies=[...]` da rota, então roda antes de
    `obter_conexao`: uma requisição sem token recebe 401 sem ocupar uma
    conexão do pool.
    """
    if not config.token_admin:
        return
    if x_token_admin is None or not secrets.compare_digest(
        x_token_admin.encode(), config.token_admin.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Token de administrador ausente ou inválido (header X-Token-Admin).",
        )


@router.post("/executar", dependencies=[Depends(exigir_token_admin)])
def executar(
    conexao: ConexaoDaRequisicao,
    origem: Literal["real", "simulacao"] = "real",
    config: Configuracoes = Depends(obter_configuracoes),
) -> dict[str, Any]:
    """Roda o pipeline (estágios 3 e 4) sobre a origem pedida (padrão `real`), com
    os parâmetros da configuração (G7).

    `executado_em` sai em UTC, no mesmo formato de `GET /validacao/estatisticas`,
    para que o cliente possa comparar os dois textos diretamente.
    """
    resumo = executar_pipeline(
        conexao,
        origem=origem,
        eps_metros=config.dbscan_eps_metros,
        min_pontos=config.dbscan_min_points,
        min_confirmacoes=config.min_confirmacoes,
        srid_calculo=config.srid_calculo,
        srid_armazenamento=config.srid_armazenamento,
    )
    return {**asdict(resumo), "executado_em": resumo.executado_em.astimezone(UTC).isoformat()}


@router.get("/estatisticas")
def estatisticas(
    conexao: ConexaoDaRequisicao,
    origem: Literal["real", "simulacao"] = "real",
) -> dict[str, Any]:
    """Contagens do funil da origem pedida (padrão `real`). Rota pública, só leitura.

    `parametros` e `executado_em` vêm da última execução do pipeline daquela
    origem, não da configuração atual (R14); `null` se ela nunca foi processada.
    """
    return calcular_estatisticas(conexao, origem=origem)
