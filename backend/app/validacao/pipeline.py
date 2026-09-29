"""Estágio 4 do pipeline de validação (promoção) e a execução em lote (CLAUDE.md §6; D6).

Os estágios 1 (schema) e 2 (geofence) rodam na entrada, alerta por alerta
(`app/validacao/entrada.py`). Os estágios 3 (agrupamento) e 4 (promoção) só fazem
sentido sobre o conjunto dos alertas, porque um alerta só se confirma na presença
de outros. Por isso rodam em lote, em `executar_pipeline`, chamado por
`POST /validacao/executar` e pelos scripts de simulação (Task 4).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from psycopg import Connection

from app.validacao.clustering import rotular_clusters
from app.validacao.entrada import ORIGENS_VALIDAS
from app.validacao.estatisticas import ROTULOS_POR_ORIGEM

# Chave do advisory lock que serializa as execuções do pipeline (D6). O número em
# si é arbitrário: basta ser uma constante que nenhum outro uso de advisory lock
# deste banco repita (hoje não há outro). 0x4D5342 é "MSB" (Mackenzie sem
# Barreiras) em ASCII, para ser reconhecível em `pg_locks` (locktype 'advisory',
# classid 0, objid 5067586).
CHAVE_LOCK_PIPELINE = 0x4D5342


@dataclass
class ResumoExecucao:
    """O que uma execução do pipeline fez. Tem os mesmos campos da resposta de
    `POST /validacao/executar` (Contrato da API).

    `rotulo` diz de onde vêm os números (G10: "SIMULAÇÃO" em toda saída de dado
    sintético), com o mesmo texto das estatísticas. `alertas_processados` conta
    os alertas que entraram no agrupamento (todos os não descartados da origem) e
    é sempre `agrupados + ruido_isolado`. Os dois campos de barreiras contam
    barreiras, não alertas. `parametros` registra com que valores a execução
    rodou, para que um resultado nunca seja lido sem eles; os mesmos valores
    ficam gravados em `execucoes_pipeline`, com o instante `executado_em`.
    """

    origem: str
    rotulo: str
    alertas_processados: int
    agrupados: int
    ruido_isolado: int
    barreiras_pendentes: int
    barreiras_confirmadas: int
    parametros: dict[str, float | int]
    executado_em: datetime


def decidir_status_barreira(sessoes_distintas: int, min_confirmacoes: int) -> str:
    """Estágio 4: `confirmada` se o cluster tem pelo menos `min_confirmacoes`
    sessões distintas; senão, `pendente`.

    A regra conta SESSÕES, não alertas (CLAUDE.md §6). Cinco alertas da mesma
    sessão no mesmo lugar são uma pessoa só, e uma pessoa sozinha não pode
    confirmar uma barreira. É a defesa contra o ataque Sybil mais simples:
    repetir o mesmo relato. Quem limpa o navegador vira uma sessão nova (D1),
    limitação a declarar no texto.

    `pendente` não é descarte: a barreira existe e aparece no mapa, mas
    aguarda confirmações de outras pessoas.

    `min_confirmacoes < 1` levanta `ValueError`: todo cluster tem pelo menos uma
    sessão, então 1 já confirmaria qualquer cluster, e 0 ou menos não tem
    significado. Um valor assim só pode ser erro de configuração.
    """
    if min_confirmacoes < 1:
        raise ValueError(f"min_confirmacoes deve ser pelo menos 1 (recebido: {min_confirmacoes})")
    return "confirmada" if sessoes_distintas >= min_confirmacoes else "pendente"


def executar_pipeline(
    conexao: Connection,
    *,
    origem: str,
    eps_metros: float,
    min_pontos: int,
    min_confirmacoes: int,
    srid_calculo: int,
    srid_armazenamento: int,
) -> ResumoExecucao:
    """Reconstrói do zero o agrupamento e as barreiras de `origem` (D6).

    Antes de tocar no banco, valida a origem e os parâmetros (`ValueError`):
    `eps_metros > 0` (o PostGIS aceita 0 e NaN sem erro e só recusa negativos, e
    isso já depois do reset), `min_pontos >= 1` e `min_confirmacoes >= 1`. Um
    valor inválido não pode apagar as barreiras e só então falhar, nem passar
    em silêncio quando não há cluster para chegar ao estágio 4.

    Passos, todos na transação de quem chamou:

    1. `pg_advisory_xact_lock(CHAVE_LOCK_PIPELINE)`. Duas execuções ao mesmo
       tempo (dois cliques em "executar", a API e um script) apagariam e
       recriariam as mesmas barreiras em paralelo. O lock faz a segunda esperar a
       primeira terminar. É um lock de TRANSAÇÃO: é liberado sozinho no commit
       ou no rollback de quem chamou, o que combina com a regra de que as
       funções de `app/validacao/` nunca fazem commit (quem faz é `obter_conexao`).
    2. Reset: alertas `agrupado` e `ruido_isolado` da origem voltam a `bruto`
       (sem `barreira_id`) e as barreiras da origem são apagadas.
    3. Estágio 3: `rotular_clusters` sobre todos os alertas não descartados.
    4. Estágio 4, para cada cluster (`tipo_id`, `cluster`): uma barreira nova
       com o centroide do cluster, `confirmacoes` = número de sessões distintas e
       status dado por `decidir_status_barreira`. Os alertas do cluster viram
       `agrupado`, ligados a ela.
    5. Os alertas que o DBSCAN marcou como ruído viram `ruido_isolado`.
    6. A linha da origem em `execucoes_pipeline` recebe os parâmetros usados e o
       instante da execução (R14). É dela que as estatísticas leem os parâmetros:
       o funil e os parâmetros que o produziram saem sempre da mesma transação,
       mesmo que o `.env` mude depois ou que um script rode com outros valores.

    Por que reconstruir tudo em vez de atualizar só o que mudou: no DBSCAN, o
    rótulo de um alerta depende de todos os outros. Um alerta novo pode
    transformar ruído em cluster, juntar-se a uma barreira que já existe ou unir
    dois clusters em um. Tratar cada um desses casos incrementalmente seria mais
    código e mais chance de erro. Recalcular do zero dá sempre o mesmo resultado
    que uma primeira execução sobre os mesmos dados. Isso resolve a reavaliação
    do ruído (T4) e torna a função idempotente: rodar duas vezes seguidas produz
    o mesmo resumo. Custo aceito: os ids das barreiras mudam a cada execução,
    então nenhum cliente deve guardar esses ids por muito tempo. A execução
    percorre todos os alertas da origem, o que é aceitável na escala de um TCC.

    O que nunca muda: alertas `descartado` (status final; nem o reset nem o
    agrupamento os tocam) e os dados da outra origem (G10: `real` e `simulacao`
    são processadas em execuções separadas e nunca se misturam).

    Alertas que chegam durante a execução (`POST /alertas` não disputa o lock):
    quem chega antes da leitura do estágio 3 entra no agrupamento; quem chega
    depois continua `bruto` até a próxima execução.

    Parâmetros explícitos: quem chama passa os valores da configuração (a rota
    faz isso). A análise de sensibilidade (Task 4) passa outros valores sem
    mexer no `.env`. `srid_armazenamento` é o SRID em que o centroide volta a
    ser gravado, o mesmo das colunas `geom`.
    """
    if origem not in ORIGENS_VALIDAS:
        raise ValueError(f"origem inválida: {origem!r} (esperado 'real' ou 'simulacao')")
    _validar_parametros(
        eps_metros=eps_metros, min_pontos=min_pontos, min_confirmacoes=min_confirmacoes
    )

    conexao.execute(
        "SELECT pg_advisory_xact_lock(%(chave)s::bigint)", {"chave": CHAVE_LOCK_PIPELINE}
    )
    _desfazer_execucao_anterior(conexao, origem)

    rotulos = rotular_clusters(
        conexao,
        origem=origem,
        eps_metros=eps_metros,
        min_pontos=min_pontos,
        srid_calculo=srid_calculo,
    )

    # Os rótulos vêm em ordem de id; o dicionário mantém a ordem de inserção.
    # Então as barreiras são criadas na ordem do menor alerta de cada cluster,
    # e duas execuções sobre os mesmos dados criam as barreiras na mesma ordem.
    alertas_por_cluster: dict[tuple[int, int], list[int]] = defaultdict(list)
    alertas_ruido: list[int] = []
    for rotulo in rotulos:
        if rotulo.cluster is None:
            alertas_ruido.append(rotulo.alerta_id)
        else:
            alertas_por_cluster[(rotulo.tipo_id, rotulo.cluster)].append(rotulo.alerta_id)

    barreiras_por_status = {"pendente": 0, "confirmada": 0}
    for (tipo_id, _), alerta_ids in alertas_por_cluster.items():
        status = _promover_cluster(
            conexao,
            alerta_ids,
            tipo_id=tipo_id,
            origem=origem,
            min_confirmacoes=min_confirmacoes,
            srid_calculo=srid_calculo,
            srid_armazenamento=srid_armazenamento,
        )
        barreiras_por_status[status] += 1

    if alertas_ruido:
        conexao.execute(
            "UPDATE alertas SET status = 'ruido_isolado' WHERE id = ANY(%(ids)s)",
            {"ids": alertas_ruido},
        )

    executado_em = _registrar_execucao(
        conexao,
        origem=origem,
        eps_metros=eps_metros,
        min_pontos=min_pontos,
        min_confirmacoes=min_confirmacoes,
        srid_calculo=srid_calculo,
    )

    return ResumoExecucao(
        origem=origem,
        rotulo=ROTULOS_POR_ORIGEM[origem],
        alertas_processados=len(rotulos),
        agrupados=len(rotulos) - len(alertas_ruido),
        ruido_isolado=len(alertas_ruido),
        barreiras_pendentes=barreiras_por_status["pendente"],
        barreiras_confirmadas=barreiras_por_status["confirmada"],
        parametros={
            "eps_metros": eps_metros,
            "min_pontos": min_pontos,
            "min_confirmacoes": min_confirmacoes,
        },
        executado_em=executado_em,
    )


def _validar_parametros(*, eps_metros: float, min_pontos: int, min_confirmacoes: int) -> None:
    """Recusa parâmetros sem sentido antes de qualquer SQL (ver `executar_pipeline`).

    `not (eps_metros > 0)` em vez de `eps_metros <= 0`: com NaN as duas comparações
    dão falso, e só a primeira forma recusa o NaN.
    """
    if not (eps_metros > 0):
        raise ValueError(f"eps_metros deve ser maior que 0 (recebido: {eps_metros})")
    if min_pontos < 1:
        raise ValueError(f"min_pontos deve ser pelo menos 1 (recebido: {min_pontos})")
    if min_confirmacoes < 1:
        raise ValueError(f"min_confirmacoes deve ser pelo menos 1 (recebido: {min_confirmacoes})")


def _registrar_execucao(
    conexao: Connection,
    *,
    origem: str,
    eps_metros: float,
    min_pontos: int,
    min_confirmacoes: int,
    srid_calculo: int,
) -> datetime:
    """Passo 6 de `executar_pipeline`: grava (upsert) os parâmetros desta execução
    na linha da origem em `execucoes_pipeline` e devolve `executado_em`.

    Uma linha por origem basta: cada execução reconstrói tudo do zero (D6), então
    só a última explica o estado atual. `executado_em` é o `now()` da transação,
    o mesmo instante para tudo o que esta execução gravou.
    """
    return conexao.execute(
        """
        INSERT INTO execucoes_pipeline
            (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
        VALUES (%(origem)s, %(eps_metros)s, %(min_pontos)s, %(min_confirmacoes)s,
                %(srid_calculo)s)
        ON CONFLICT (origem) DO UPDATE
            SET eps_metros       = EXCLUDED.eps_metros,
                min_pontos       = EXCLUDED.min_pontos,
                min_confirmacoes = EXCLUDED.min_confirmacoes,
                srid_calculo     = EXCLUDED.srid_calculo,
                executado_em     = EXCLUDED.executado_em
        RETURNING executado_em
        """,
        {
            "origem": origem,
            "eps_metros": eps_metros,
            "min_pontos": min_pontos,
            "min_confirmacoes": min_confirmacoes,
            "srid_calculo": srid_calculo,
        },
    ).fetchone()[0]


def _desfazer_execucao_anterior(conexao: Connection, origem: str) -> None:
    """Passo 2 de `executar_pipeline`: volta a origem ao estado anterior a
    qualquer execução.

    A ordem importa: `alertas.barreira_id` referencia `barreiras`, então os
    alertas soltam a barreira antes de ela ser apagada. `descartado` fica fora
    do `WHERE`: é status final.
    """
    conexao.execute(
        """
        UPDATE alertas
        SET status = 'bruto', barreira_id = NULL
        WHERE origem = %(origem)s
          AND status IN ('agrupado', 'ruido_isolado')
        """,
        {"origem": origem},
    )
    conexao.execute("DELETE FROM barreiras WHERE origem = %(origem)s", {"origem": origem})


def _promover_cluster(
    conexao: Connection,
    alerta_ids: list[int],
    *,
    tipo_id: int,
    origem: str,
    min_confirmacoes: int,
    srid_calculo: int,
    srid_armazenamento: int,
) -> str:
    """Passo 4 de `executar_pipeline` para um cluster: cria a barreira, liga os
    alertas a ela e devolve o status dela.

    `confirmacoes` recebe `COUNT(DISTINCT sessao_hash)`: sessões distintas, não
    alertas (ver `decidir_status_barreira`). `sessao_hash` é `NOT NULL` no schema
    justamente porque o `COUNT(DISTINCT ...)` ignoraria NULL sem avisar.

    Geometria: o centroide dos alertas. Ele é calculado no SRID de cálculo
    (métrico) e só então transformado de volta para o SRID de armazenamento, como
    toda conta geométrica do projeto (G6). Com pontos a poucos metros uns dos
    outros, o centroide calculado em graus daria praticamente o mesmo ponto. A
    regra vale por coerência e pelos clusters longos que o encadeamento produz
    (T5).
    """
    sessoes_distintas = conexao.execute(
        "SELECT COUNT(DISTINCT sessao_hash) FROM alertas WHERE id = ANY(%(ids)s)",
        {"ids": alerta_ids},
    ).fetchone()[0]
    status = decidir_status_barreira(sessoes_distintas, min_confirmacoes)

    barreira_id = conexao.execute(
        """
        INSERT INTO barreiras (geom, tipo_id, confirmacoes, status, origem)
        SELECT ST_Transform(
                   ST_Centroid(ST_Collect(ST_Transform(geom, %(srid_calculo)s))),
                   %(srid_armazenamento)s
               ),
               %(tipo_id)s, %(confirmacoes)s, %(status)s, %(origem)s
        FROM alertas
        WHERE id = ANY(%(ids)s)
        RETURNING id
        """,
        {
            "srid_calculo": srid_calculo,
            "srid_armazenamento": srid_armazenamento,
            "tipo_id": tipo_id,
            "confirmacoes": sessoes_distintas,
            "status": status,
            "origem": origem,
            "ids": alerta_ids,
        },
    ).fetchone()[0]

    conexao.execute(
        """
        UPDATE alertas
        SET status = 'agrupado', barreira_id = %(barreira_id)s
        WHERE id = ANY(%(ids)s)
        """,
        {"barreira_id": barreira_id, "ids": alerta_ids},
    )
    return status
