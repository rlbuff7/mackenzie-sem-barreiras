"""Estatísticas do funil de validação (`GET /validacao/estatisticas`, CLAUDE.md §7).

É daqui que sai a figura do funil do documento final: quantos relatos chegaram,
quantos cada estágio barrou e quantas barreiras sobraram. Os números vêm sempre
do banco, nunca de valores fixos (CLAUDE.md §7).
"""

from datetime import UTC, datetime
from typing import Any

from psycopg import Connection

from app.validacao.entrada import ORIGENS_VALIDAS

# G10: toda saída diz de onde vêm os números. Um número sintético nunca pode ser
# lido como resultado de coleta real.
ROTULOS_POR_ORIGEM = {
    "real": "Dados reais de campo",
    "simulacao": "SIMULAÇÃO — dados sintéticos",
}

# Motivo gravado pelo geofence (estágio 2) em `app/validacao/entrada.py`. Aparece
# sempre na resposta, mesmo com zero, para que a figura do funil tenha sempre o
# estágio do geofence.
_MOTIVO_FORA_DA_AREA = "fora_da_area"


def calcular_estatisticas(conexao: Connection, *, origem: str) -> dict[str, Any]:
    """Contagens do funil de uma origem, no formato do Contrato da API.

    Unidades: o bloco `alertas` conta ALERTAS e o bloco `barreiras` conta
    BARREIRAS. A unidade muda no agrupamento (vários alertas formam uma
    barreira), e o funil do pôster do TCC I não deixava isso claro; aqui os dois
    blocos ficam separados.

    Bloco `alertas`, na ordem do funil:

    - `recebidos`: tudo o que chegou, ou seja, `rejeitados_schema` mais as
      linhas de `alertas` da origem. O payload reprovado no estágio 1 não cabe em
      `alertas` e fica em `alertas_rejeitados` (T1).
    - `rejeitados_schema`: reprovados no estágio 1.
    - `descartados`: reprovados depois do schema, agrupados por
      `motivo_descarte`. Um motivo novo aparece sozinho, sem mudar este código.
      `fora_da_area` (estágio 2) está sempre presente, mesmo com 0.
    - `aguardando_pipeline`: `bruto`, ainda não passaram pelo estágio 3.
    - `ruido_isolado`: sem vizinhos na última execução (não é descarte, T4).
    - `agrupados`: pertencem a um cluster, ligados a uma barreira.

    Todo alerta recebido está em exatamente um desses estágios, então
    `recebidos` é a soma de todos os outros.

    Bloco `barreiras`: `total`, `pendentes` e `confirmadas` (estágio 4).

    `parametros` (`eps_metros`, `min_pontos`, `min_confirmacoes`) e
    `executado_em` são os da ÚLTIMA EXECUÇÃO do pipeline para a origem, lidos de
    `execucoes_pipeline` (R14). NÃO são a configuração atual: os status e as
    barreiras foram produzidos por aquela execução, e o `.env` pode ter mudado
    depois, ou um script pode ter rodado com outros valores (análise de
    sensibilidade). Assim a figura do funil nunca leva parâmetros que não
    produziram os números. Origem nunca processada: os dois são `None`.

    Um único snapshot: tudo sai de UMA consulta. Em READ COMMITTED (o padrão do
    Postgres) cada comando enxerga os dados confirmados até o seu início; com
    várias consultas, uma execução do pipeline confirmada entre elas produziria
    um funil misturado (alertas de antes, barreiras de depois). Numa consulta
    só, as contagens e os parâmetros são sempre do mesmo instante.

    `gerado_em` é o instante do cálculo (UTC, ISO-8601); `executado_em` também
    sai em UTC.
    """
    if origem not in ORIGENS_VALIDAS:
        raise ValueError(f"origem inválida: {origem!r} (esperado 'real' ou 'simulacao')")

    linha = conexao.execute(
        """
        WITH alertas_da_origem AS (
            SELECT status, motivo_descarte FROM alertas WHERE origem = %(origem)s
        ),
        barreiras_da_origem AS (
            SELECT status FROM barreiras WHERE origem = %(origem)s
        )
        SELECT
            (SELECT count(*) FROM alertas_rejeitados WHERE origem = %(origem)s),
            (SELECT count(*) FROM alertas_da_origem),
            (SELECT COALESCE(jsonb_object_agg(motivo_descarte, total), '{}'::jsonb)
             FROM (SELECT motivo_descarte, count(*) AS total
                   FROM alertas_da_origem
                   WHERE status = 'descartado'
                   GROUP BY motivo_descarte) AS por_motivo),
            (SELECT count(*) FROM alertas_da_origem WHERE status = 'bruto'),
            (SELECT count(*) FROM alertas_da_origem WHERE status = 'ruido_isolado'),
            (SELECT count(*) FROM alertas_da_origem WHERE status = 'agrupado'),
            (SELECT count(*) FROM barreiras_da_origem),
            (SELECT count(*) FROM barreiras_da_origem WHERE status = 'pendente'),
            (SELECT count(*) FROM barreiras_da_origem WHERE status = 'confirmada'),
            execucao.eps_metros,
            execucao.min_pontos,
            execucao.min_confirmacoes,
            execucao.executado_em
        FROM (VALUES (1)) AS uma_linha
        LEFT JOIN execucoes_pipeline AS execucao ON execucao.origem = %(origem)s
        """,
        {"origem": origem},
    ).fetchone()
    (
        rejeitados_schema,
        linhas_alertas,
        descartados_por_motivo,
        aguardando_pipeline,
        ruido_isolado,
        agrupados,
        barreiras_total,
        barreiras_pendentes,
        barreiras_confirmadas,
        eps_metros,
        min_pontos,
        min_confirmacoes,
        executado_em,
    ) = linha

    # `fora_da_area` primeiro (é o estágio 2 do funil), os outros em ordem
    # alfabética, para a resposta ter sempre a mesma forma.
    descartados = {_MOTIVO_FORA_DA_AREA: descartados_por_motivo.pop(_MOTIVO_FORA_DA_AREA, 0)}
    descartados.update(sorted(descartados_por_motivo.items()))

    nunca_executado = executado_em is None
    return {
        "origem": origem,
        "rotulo": ROTULOS_POR_ORIGEM[origem],
        "alertas": {
            "recebidos": rejeitados_schema + linhas_alertas,
            "rejeitados_schema": rejeitados_schema,
            "descartados": descartados,
            "aguardando_pipeline": aguardando_pipeline,
            "ruido_isolado": ruido_isolado,
            "agrupados": agrupados,
        },
        "barreiras": {
            "total": barreiras_total,
            "pendentes": barreiras_pendentes,
            "confirmadas": barreiras_confirmadas,
        },
        "parametros": None
        if nunca_executado
        else {
            "eps_metros": eps_metros,
            "min_pontos": min_pontos,
            "min_confirmacoes": min_confirmacoes,
        },
        "executado_em": None if nunca_executado else executado_em.astimezone(UTC).isoformat(),
        "gerado_em": datetime.now(UTC).isoformat(),
    }
