"""`POST /medicoes`, `GET /medicoes/resumo` e `/medicoes/analise` (medição de GPS em tempo real).

É dado DA EQUIPE: os celulares dela nos pontos de controle do campus, enviados na
hora (com fila no celular quando falta sinal). A posição de quem NAVEGA nunca é
gravada (regra do M4); esta rota não serve para isso e não recebe nome de pessoa,
só o modelo do aparelho.

`POST /medicoes` é protegido pelo código da equipe (header `X-Codigo-Equipe`) e é
idempotente: cada medição traz um `id_cliente` (UUID gerado no celular) e o reenvio
de um lote inteiro, que a fila do celular faz sempre que falta sinal, não duplica
nada (`ON CONFLICT (id_cliente) DO NOTHING`). O lote inteiro vai numa transação: se
um item é inválido, nenhum é gravado.

Rota `async` pelo mesmo motivo de `POST /alertas`: lê o corpo cru em fluxo, com
teto de `LIMITE_CORPO_BYTES` (413), antes de qualquer parse.
"""

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg import Connection
from pydantic import ValidationError

from app.config import Configuracoes, obter_configuracoes
from app.db import ConexaoDaRequisicao
from app.routers.alertas import _ler_corpo_limitado, _mensagem_corpo_grande
from app.routers.validacao import exigir_token_admin
from app.schemas.medicao import MedicaoEntrada, MedicoesEntrada, MedicoesGravadas
from app.validacao.mensagens import traduzir_erros_da_requisicao

router = APIRouter(prefix="/medicoes")

# Posição em 4326 (grau), como o GPS informa: `ST_MakePoint(longitude, latitude)`.
# Sem posição, `ST_MakePoint(NULL, NULL)` devolve NULL (função estrita) e `geom` fica
# NULL, como bússola e vibração.
_SQL_INSERIR = """
    INSERT INTO medicoes_gps (
        id_cliente, tipo, medido_em, aparelho, ponto, condicao, geom, precisao_m,
        altitude_m, altitude_precisao_m, velocidade_ms, rumo_gps_graus,
        bussola_graus, bussola_fonte, bussola_oscilacao_graus,
        vibracao_suportada, observacao, user_agent
    ) VALUES (
        %(id_cliente)s, %(tipo)s, %(medido_em)s, %(aparelho)s, %(ponto)s, %(condicao)s,
        ST_SetSRID(ST_MakePoint(%(longitude)s::float8, %(latitude)s::float8), 4326),
        %(precisao_m)s,
        %(altitude_m)s, %(altitude_precisao_m)s, %(velocidade_ms)s, %(rumo_gps_graus)s,
        %(bussola_graus)s, %(bussola_fonte)s, %(bussola_oscilacao_graus)s,
        %(vibracao_suportada)s, %(observacao)s, %(user_agent)s
    )
    ON CONFLICT (id_cliente) DO NOTHING
"""


def exigir_codigo_equipe(
    x_codigo_equipe: Annotated[str | None, Header()] = None,
    config: Configuracoes = Depends(obter_configuracoes),
) -> None:
    """Exige o header `X-Codigo-Equipe` igual a `MEDICAO_CODIGO_EQUIPE`.

    Diferente do token de administrador, código vazio no servidor NÃO deixa a rota
    aberta: ela fica DESLIGADA (503). Quem grava dado de campo precisa ser a equipe;
    esquecer a variável no servidor nunca pode abrir a escrita ao público.

    `secrets.compare_digest` compara em tempo constante (uma comparação com `==`
    revelaria, pelo tempo, quantos caracteres do código estão certos); os dois lados
    viram bytes porque `compare_digest` só aceita `str` ASCII.

    Entra em `dependencies=[...]` da rota, então roda antes do corpo e de
    `obter_conexao`: 503 e 401 não leem o corpo nem ocupam uma conexão do pool.
    """
    if not config.medicao_codigo_equipe.strip():
        raise HTTPException(status_code=503, detail="Medição desligada neste servidor.")
    if x_codigo_equipe is None or not secrets.compare_digest(
        x_codigo_equipe.encode(), config.medicao_codigo_equipe.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Código da equipe ausente ou inválido (header X-Codigo-Equipe).",
        )


def _gravar_lote(conexao: Connection, medicoes: list[MedicaoEntrada]) -> MedicoesGravadas:
    """Insere o lote (uma transação, quem faz commit é `obter_conexao`) e conta
    quantas linhas entraram; as demais já existiam (mesmo `id_cliente`)."""
    gravadas = 0
    with conexao.cursor() as cursor:
        for medicao in medicoes:
            cursor.execute(_SQL_INSERIR, medicao.model_dump())
            gravadas += cursor.rowcount
    return MedicoesGravadas(gravadas=gravadas, repetidas=len(medicoes) - gravadas)


@router.post(
    "",
    response_model=MedicoesGravadas,
    dependencies=[Depends(exigir_codigo_equipe)],
)
async def gravar_medicoes(
    request: Request,
    conexao: ConexaoDaRequisicao,
    config: Configuracoes = Depends(obter_configuracoes),
) -> MedicoesGravadas | JSONResponse:
    corpo_bruto = await _ler_corpo_limitado(request, config.limite_corpo_bytes)
    if corpo_bruto is None:
        return JSONResponse(
            status_code=413,
            content={"mensagem": _mensagem_corpo_grande(config.limite_corpo_bytes)},
        )
    try:
        lote = MedicoesEntrada.model_validate_json(corpo_bruto)
    except ValidationError as erro:
        return JSONResponse(
            status_code=422,
            content={
                "mensagem": "Medição inválida.",
                "erros": traduzir_erros_da_requisicao(erro.errors()),
            },
        )
    # I/O de banco síncrono (psycopg): fora do event loop.
    return await run_in_threadpool(_gravar_lote, conexao, lote.medicoes)


def _arredondar(valor: float | None) -> float | None:
    return None if valor is None else round(valor, 2)


@router.get("/resumo", dependencies=[Depends(exigir_token_admin)])
def resumo(conexao: ConexaoDaRequisicao) -> dict[str, Any]:
    """Conferência da ida a campo sem psql. Precisão em metros, mediana e p90 por
    `percentile_cont` (interpolada) sobre as medições que têm `precisao_m`.

    - `por_aparelho`: `pontos` = quantos pontos de controle distintos o aparelho
      mediu; `medicoes` = linhas do aparelho, de todos os tipos.
    - `por_ponto`: só linhas com número de ponto; `medicoes` conta todas elas.
    """
    total = conexao.execute("SELECT count(*) FROM medicoes_gps").fetchone()[0]
    por_aparelho = conexao.execute(
        """
        SELECT aparelho, count(DISTINCT ponto), count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY precisao_m)
        FROM medicoes_gps
        GROUP BY aparelho
        ORDER BY aparelho
        """
    ).fetchall()
    por_ponto = conexao.execute(
        """
        SELECT ponto, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY precisao_m),
               percentile_cont(0.9) WITHIN GROUP (ORDER BY precisao_m)
        FROM medicoes_gps
        WHERE ponto IS NOT NULL
        GROUP BY ponto
        ORDER BY ponto
        """
    ).fetchall()
    return {
        "total": total,
        "por_aparelho": [
            {
                "aparelho": aparelho,
                "pontos": pontos,
                "medicoes": medicoes,
                "precisao_mediana_m": _arredondar(mediana),
            }
            for aparelho, pontos, medicoes, mediana in por_aparelho
        ],
        "por_ponto": [
            {
                "ponto": ponto,
                "medicoes": medicoes,
                "precisao_mediana_m": _arredondar(mediana),
                "precisao_p90_m": _arredondar(p90),
            }
            for ponto, medicoes, mediana, p90 in por_ponto
        ],
    }


AVISO_ANALISE = (
    "O erro é a distância entre a posição medida pelo celular e uma referência "
    "estimada por imagem de satélite (não é topografia). Ele inclui, portanto, a "
    "incerteza da própria referência: não é o erro absoluto do GPS."
)


def _arredondar_1(valor: float | None) -> float | None:
    return None if valor is None else round(valor, 1)


@router.get("/analise", dependencies=[Depends(exigir_token_admin)])
def analise(conexao: ConexaoDaRequisicao) -> dict[str, Any]:
    """Erro das medições de ponto contra a referência dos pontos de controle.

    Lê as views `vw_erro_medicoes` (uma linha por medição de ponto com referência;
    distância em SRID 31983, metros) e `vw_erro_por_ponto_aparelho`. Medição de ponto
    sem referência cadastrada (11 e 12) não entra. Erros em metros com 1 casa;
    `fracao_erro_dentro_precisao` é uma fração de 0 a 1 com 2 casas. Em
    `por_condicao` só entram medições que informaram a condição. Sem dados: listas
    vazias e total 0.
    """
    total = conexao.execute("SELECT count(*) FROM vw_erro_medicoes").fetchone()[0]
    por_ponto_aparelho = conexao.execute(
        """
        SELECT ponto_codigo, p.nome, aparelho, n, erro_mediana_m, erro_p90_m,
               fracao_erro_dentro_precisao
        FROM vw_erro_por_ponto_aparelho v
        JOIN pontos_controle p ON p.numero = v.ponto
        ORDER BY ponto, aparelho
        """
    ).fetchall()
    por_condicao = conexao.execute(
        """
        SELECT condicao, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY erro_m),
               percentile_cont(0.9) WITHIN GROUP (ORDER BY erro_m)
        FROM vw_erro_medicoes
        WHERE condicao IS NOT NULL
        GROUP BY condicao
        ORDER BY condicao
        """
    ).fetchall()
    return {
        "aviso": AVISO_ANALISE,
        "total_medicoes_analisadas": total,
        "por_ponto_aparelho": [
            {
                "ponto_codigo": codigo,
                "ponto_nome": nome,
                "aparelho": aparelho,
                "n": n,
                "erro_mediana_m": _arredondar_1(mediana),
                "erro_p90_m": _arredondar_1(p90),
                "fracao_erro_dentro_precisao": None if fracao is None else round(fracao, 2),
            }
            for codigo, nome, aparelho, n, mediana, p90, fracao in por_ponto_aparelho
        ],
        "por_condicao": [
            {
                "condicao": condicao,
                "n": n,
                "erro_mediana_m": _arredondar_1(mediana),
                "erro_p90_m": _arredondar_1(p90),
            }
            for condicao, n, mediana, p90 in por_condicao
        ],
    }
