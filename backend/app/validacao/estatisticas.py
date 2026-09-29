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


def calcular_estatisticas(
    conexao: Connection, *, origem: str, parametros: dict[str, float | int]
) -> dict[str, Any]:
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

    `parametros` (`eps_metros`, `min_pontos`, `min_confirmacoes`) é devolvido
    como veio. O banco não guarda com que parâmetros o estado atual foi
    produzido. A rota passa os da configuração, que são os que
    `POST /validacao/executar` usa; se um script rodou o pipeline com outros
    valores (análise de sensibilidade, Task 4), as contagens refletem a última
    execução, não necessariamente estes parâmetros.

    `gerado_em` é o instante do cálculo (UTC, ISO-8601).
    """
    if origem not in ORIGENS_VALIDAS:
        raise ValueError(f"origem inválida: {origem!r} (esperado 'real' ou 'simulacao')")

    rejeitados_schema = conexao.execute(
        "SELECT count(*) FROM alertas_rejeitados WHERE origem = %(origem)s",
        {"origem": origem},
    ).fetchone()[0]

    linhas_alertas = conexao.execute(
        """
        SELECT status, motivo_descarte, count(*)
        FROM alertas
        WHERE origem = %(origem)s
        GROUP BY status, motivo_descarte
        """,
        {"origem": origem},
    ).fetchall()
    alertas_por_status: dict[str, int] = {}
    descartados_por_motivo: dict[str, int] = {}
    for status, motivo_descarte, total in linhas_alertas:
        alertas_por_status[status] = alertas_por_status.get(status, 0) + total
        if status == "descartado":
            descartados_por_motivo[motivo_descarte] = total

    barreiras_por_status = dict(
        conexao.execute(
            "SELECT status, count(*) FROM barreiras WHERE origem = %(origem)s GROUP BY status",
            {"origem": origem},
        ).fetchall()
    )

    # `fora_da_area` primeiro (é o estágio 2 do funil), os outros em ordem
    # alfabética, para a resposta ter sempre a mesma forma.
    descartados = {_MOTIVO_FORA_DA_AREA: descartados_por_motivo.pop(_MOTIVO_FORA_DA_AREA, 0)}
    descartados.update(sorted(descartados_por_motivo.items()))

    return {
        "origem": origem,
        "rotulo": ROTULOS_POR_ORIGEM[origem],
        "alertas": {
            "recebidos": rejeitados_schema + sum(alertas_por_status.values()),
            "rejeitados_schema": rejeitados_schema,
            "descartados": descartados,
            "aguardando_pipeline": alertas_por_status.get("bruto", 0),
            "ruido_isolado": alertas_por_status.get("ruido_isolado", 0),
            "agrupados": alertas_por_status.get("agrupado", 0),
        },
        "barreiras": {
            "total": sum(barreiras_por_status.values()),
            "pendentes": barreiras_por_status.get("pendente", 0),
            "confirmadas": barreiras_por_status.get("confirmada", 0),
        },
        "parametros": {
            "eps_metros": parametros["eps_metros"],
            "min_pontos": parametros["min_pontos"],
            "min_confirmacoes": parametros["min_confirmacoes"],
        },
        "gerado_em": datetime.now(UTC).isoformat(),
    }
