"""`POST /rotas` (E6): caminho entre dois pontos de interesse do campus.

Rota PÚBLICA (sem token): não grava nada e não recebe a posição de ninguém. A origem é
um ponto de interesse escolhido numa lista (`origem_id`), não a posição do aparelho.
O corpo não é registrado em log. Silêncio é melhor que palpite: sem caminho mapeado, 404
`sem_rota`; nunca liga dois pontos em linha reta.

Rota `async` pelo mesmo motivo de `POST /alertas`: lê o corpo cru em fluxo, com teto de
`LIMITE_CORPO_BYTES` (413).
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg import Connection
from pydantic import ValidationError

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.rotas.caminho import calcular_caminho, concatenar_geometria
from app.rotas.instrucoes import arredondar_metros, montar_instrucoes
from app.rotas.rotulos import ATRIBUICAO_OSM, rotulo_das_fontes
from app.routers.alertas import _ler_corpo_limitado, _mensagem_corpo_grande
from app.schemas.rota import RotaEntrada
from app.validacao.mensagens import traduzir_erros_da_requisicao

router = APIRouter()

AVISO_DE_SEGURANCA = (
    "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade."
)


def _erro(status: int, mensagem: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"mensagem": mensagem, **extra})


def _ponto_com_no(conexao: Connection, ponto_id: int) -> tuple[Any, ...] | None:
    """(id, tipo, nome, lat, lon, id do nó ou None); `None` se o ponto não existe.
    Mais de um nó por ponto: usa o de menor id."""
    return conexao.execute(
        """SELECT p.id, p.tipo, p.nome, ST_Y(p.geom), ST_X(p.geom),
                  (SELECT min(n.id) FROM nos n WHERE n.ponto_interesse_id = p.id)
           FROM pontos_interesse p WHERE p.id = %s""",
        (ponto_id,),
    ).fetchone()


def _montar_rota(
    conexao: Connection, entrada: RotaEntrada, config: Configuracoes
) -> JSONResponse | dict[str, Any]:
    origem = _ponto_com_no(conexao, entrada.origem_id)
    destino = _ponto_com_no(conexao, entrada.destino_id)
    if origem is None:
        return _erro(404, "Ponto de interesse não encontrado.", campo="origem_id")
    if destino is None:
        return _erro(404, "Ponto de interesse não encontrado.", campo="destino_id")
    if destino[1] != "entrada":
        return _erro(
            422,
            "Pedido de rota inválido.",
            erros=[{"campo": "destino_id", "erro": "Escolha uma entrada de prédio."}],
        )
    sem_no = "Este ponto ainda não está ligado ao mapa de caminhos."
    for campo, ponto in (("origem_id", origem), ("destino_id", destino)):
        if ponto[5] is None:
            return _erro(422, "Pedido de rota inválido.", erros=[{"campo": campo, "erro": sem_no}])
    if conexao.execute("SELECT count(*) FROM arestas").fetchone()[0] == 0:
        return _erro(503, "O mapa de caminhos do campus ainda não foi carregado.")

    trechos = calcular_caminho(
        conexao,
        no_origem=origem[5],
        no_destino=destino[5],
        perfil=entrada.perfil,
        config=config,
    )
    if not trechos:
        return _erro(404, "Não há caminho mapeado entre esses dois pontos.", codigo="sem_rota")

    nos_do_caminho = [t.no_para for t in trechos]
    referencias = dict(
        conexao.execute(
            """SELECT n.id, p.nome FROM nos n JOIN pontos_interesse p ON p.id = n.ponto_interesse_id
               WHERE p.tipo = 'entrada' AND n.id = ANY(%s)""",
            (nos_do_caminho,),
        ).fetchall()
    )

    fontes = {t.fonte_verificacao for t in trechos}
    distancia = sum(t.comprimento_m for t in trechos)
    escadas = sum(t.comprimento_m for t in trechos if t.tipo == "escada")
    acessibilidades = [False if t.tipo == "escada" else t.acessivel_cadeirante for t in trechos]
    if any(a is False for a in acessibilidades):
        acessivel: bool | None = False
    elif all(a is True for a in acessibilidades):
        acessivel = True
    else:
        acessivel = None

    avisos = []
    if escadas:
        avisos.append(f"O caminho tem escada (cerca de {arredondar_metros(escadas)} metros).")
    if any(t.tipo == "travessia" for t in trechos):
        avisos.append("O caminho atravessa uma rua.")
    if fontes - {"conferido_a_pe"}:
        avisos.append("Há trecho ainda não conferido a pé.")

    resposta: dict[str, Any] = {
        "rotulo": rotulo_das_fontes(fontes),
        "provisorio": "provisorio" in fontes,
        "perfil": entrada.perfil,
        "origem": {
            "id": origem[0],
            "nome": origem[2],
            "latitude": origem[3],
            "longitude": origem[4],
        },
        "destino": {
            "id": destino[0],
            "nome": destino[2],
            "latitude": destino[3],
            "longitude": destino[4],
        },
        "distancia_m": round(distancia, 1),
        "custo": round(sum(t.custo for t in trechos), 1),
        "acessivel_cadeirante": acessivel,
        "avisos": avisos,
        "aviso_seguranca": AVISO_DE_SEGURANCA,
        "trechos": [
            {
                "ordem": i,
                "aresta_id": t.aresta_id,
                "tipo": t.tipo,
                "comprimento_m": round(t.comprimento_m, 1),
                "acessivel_cadeirante": t.acessivel_cadeirante,
                "fonte_verificacao": t.fonte_verificacao,
            }
            for i, t in enumerate(trechos, start=1)
        ],
        "instrucoes": [
            {"ordem": i, "texto": texto}
            for i, texto in enumerate(montar_instrucoes(trechos, referencias, destino[2]), start=1)
        ],
        "geometria": {"type": "LineString", "coordinates": concatenar_geometria(trechos)},
    }
    if any(t.mapeado_por and "OpenStreetMap" in t.mapeado_por for t in trechos):
        resposta["atribuicao"] = ATRIBUICAO_OSM
    return resposta


@router.post("/rotas")
async def calcular_rota(
    request: Request,
    conexao: ConexaoDaRequisicao,
    config: Configuracoes = Depends(obter_configuracoes),
) -> Any:
    corpo_bruto = await _ler_corpo_limitado(request, config.limite_corpo_bytes)
    if corpo_bruto is None:
        return _erro(413, _mensagem_corpo_grande(config.limite_corpo_bytes))
    try:
        entrada = RotaEntrada.model_validate_json(corpo_bruto)
    except ValidationError as erro:
        return _erro(
            422,
            "Pedido de rota inválido.",
            erros=traduzir_erros_da_requisicao(erro.errors()),
        )
    return await run_in_threadpool(_montar_rota, conexao, entrada, config)
