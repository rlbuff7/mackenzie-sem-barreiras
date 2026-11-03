"""`POST /orientacoes` (M4): o que falar agora a quem está navegando por uma rota.

PRIVACIDADE (RNF04): a posição de quem navega e a trilha NUNCA
são gravadas. Esta rota não escreve em
banco, arquivo nem log; o corpo só vive em memória durante a chamada. O app não configura
logging de corpo (nenhum `logging`/`print` em `app/`), o log de acesso do uvicorn registra
só método, caminho e status, e o `nginx.conf` não usa `$request_body` no `log_format`;
`tests/test_api_orientacoes.py` confere que nada da posição aparece no log. Se alguém ligar
log de corpo (middleware, nginx), tem de excluir esta rota.

Sem token (como `/rotas`), corpo limitado em bytes. O servidor recalcula a rota com a mesma
lógica de `POST /rotas` (`_montar_rota`: perfis, 404 `sem_rota`, 422), então não há sessão:
o cliente reenvia origem, destino, perfil, a posição e as mensagens recentes.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg import Connection
from pydantic import ValidationError

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.orientacao.mensagens import (
    ParametrosMensagens,
    Recente,
    decidir_mensagem,
    obstaculos_dos_trechos,
)
from app.orientacao.posicao import ParametrosOrientacao, Posicao, avaliar_posicao
from app.orientacao.rumo import ParametrosRumo, PontoTrilha, direcao_relativa
from app.routers.alertas import _ler_corpo_limitado, _mensagem_corpo_grande
from app.routers.rotas import _erro, _montar_rota
from app.schemas.orientacao import OrientacaoEntrada
from app.schemas.rota import RotaEntrada
from app.validacao.mensagens import traduzir_erros_da_requisicao

router = APIRouter()


def _orientar(
    conexao: Connection, entrada: OrientacaoEntrada, config: Configuracoes
) -> JSONResponse | dict[str, Any]:
    rota = _montar_rota(
        conexao,
        RotaEntrada(
            origem_id=entrada.origem_id, destino_id=entrada.destino_id, perfil=entrada.perfil
        ),
        config,
    )
    if isinstance(rota, JSONResponse):  # 404 sem_rota, 404 ponto, 422, 503: igual a /rotas
        return rota

    geometria = rota["geometria"]["coordinates"]
    pos = entrada.posicao
    avaliacao = avaliar_posicao(
        Posicao(lat=pos.lat, lon=pos.lon, precisao_m=pos.precisao_m),
        geometria,
        ParametrosOrientacao.de_configuracoes(config),
    )
    projecao = avaliacao.projecao

    direcao = None
    fonte_rumo = None
    # Direção só com a posição confiável e na rota: fora da rota, nunca "vire para voltar".
    if projecao is not None and avaliacao.estado == "na_rota" and avaliacao.confianca != "baixa":
        achado = direcao_relativa(
            geometria,
            lat=pos.lat,
            lon=pos.lon,
            distancia_percorrida_m=projecao.distancia_percorrida_m,
            precisao_m=pos.precisao_m,
            bussola_graus=pos.rumo_bussola_graus,
            bussola_oscilacao_graus=pos.rumo_bussola_oscilacao_graus,
            trilha=[PontoTrilha(t.lat, t.lon, t.precisao_m, t.ha_segundos) for t in entrada.trilha],
            parametros=ParametrosRumo.de_configuracoes(config),
        )
        if achado is not None:
            direcao, fonte_rumo = achado

    mensagem = decidir_mensagem(
        avaliacao,
        direcao=direcao,
        instrucoes=rota["instrucoes"],
        obstaculos=obstaculos_dos_trechos(rota["trechos"]),
        recentes=[Recente(r.chave, r.ha_segundos) for r in entrada.recentes],
        parametros=ParametrosMensagens.de_configuracoes(config),
    )
    mostrar = projecao is not None and avaliacao.estado != "fora_da_rota"
    return {
        "estado": avaliacao.estado,
        "confianca": avaliacao.confianca,
        "mensagem": (
            {"chave": mensagem.chave, "texto": mensagem.texto, "prioridade": mensagem.prioridade}
            if mensagem
            else None
        ),
        # Sem projeção (precisão ruim) ou fora da rota, o progresso seria palpite: null.
        "distancia_restante_m": round(projecao.distancia_restante_m, 1) if mostrar else None,
        "progresso_m": round(projecao.distancia_percorrida_m, 1) if mostrar else None,
        "direcao": direcao,
        "fonte_rumo": fonte_rumo,
    }


@router.post("/orientacoes")
async def orientar(
    request: Request,
    conexao: ConexaoDaRequisicao,
    config: Configuracoes = Depends(obter_configuracoes),
) -> Any:
    corpo_bruto = await _ler_corpo_limitado(request, config.limite_corpo_bytes)
    if corpo_bruto is None:
        return _erro(413, _mensagem_corpo_grande(config.limite_corpo_bytes))
    try:
        entrada = OrientacaoEntrada.model_validate_json(corpo_bruto)
    except ValidationError as erro:
        return _erro(
            422,
            "Pedido de orientação inválido.",
            erros=traduzir_erros_da_requisicao(erro.errors()),
        )
    return await run_in_threadpool(_orientar, conexao, entrada, config)
