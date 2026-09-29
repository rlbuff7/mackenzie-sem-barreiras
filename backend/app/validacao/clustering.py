"""Estágio 3 do pipeline de validação: agrupamento espacial (CLAUDE.md §6, estágio 3).

Um alerta isolado é um indício fraco; vários alertas do mesmo tipo no mesmo lugar,
vindos de pessoas diferentes, são um indício forte. Este estágio encontra esses
grupos com o DBSCAN (Ester et al., 1996), executado dentro do PostGIS por
`ST_ClusterDBSCAN`. A decisão sobre o que cada grupo vale (barreira `pendente` ou
`confirmada`) é do estágio 4, em `app/validacao/pipeline.py`; aqui só se rotula.
"""

from dataclasses import dataclass

from psycopg import Connection


@dataclass(frozen=True)
class RotuloAlerta:
    """Rótulo que o DBSCAN deu a um alerta.

    `cluster` é o número do cluster DENTRO do tipo do alerta: o PostGIS numera os
    clusters de cada partição a partir de 0, então o cluster 0 do tipo `degrau` e o
    cluster 0 do tipo `obstaculo` são grupos diferentes. A identidade de um cluster
    é o par (`tipo_id`, `cluster`). `cluster = None` significa ruído.
    """

    alerta_id: int
    tipo_id: int
    cluster: int | None


def rotular_clusters(
    conexao: Connection,
    *,
    origem: str,
    eps_metros: float,
    min_pontos: int,
    srid_calculo: int,
) -> list[RotuloAlerta]:
    """Roda o DBSCAN sobre os alertas de `origem` e devolve um rótulo por alerta.

    Só lê o banco: não muda o `status` de nenhum alerta. Gravar o resultado é
    trabalho de `executar_pipeline` (estágio 4). Devolve os rótulos em ordem de id.

    Quais alertas entram: os da `origem` pedida com status `bruto`,
    `ruido_isolado` ou `agrupado`, ou seja, tudo que não foi `descartado`.
    `descartado` é final (fora da área, por exemplo) e nunca volta ao
    agrupamento. As duas origens nunca se misturam (G10): um alerta sintético não
    pode confirmar um alerta real, nem o contrário.

    Por que reprojetar (G6, CLAUDE.md §5): os alertas são armazenados em SRID
    4326, cuja unidade é o GRAU. O `eps` do `ST_ClusterDBSCAN` é lido na unidade
    do SRID da geometria. Em 4326, `eps = 8` seria 8 graus (8° de latitude são
    quase 900 km) e o agrupamento juntaria a cidade inteira sem dar erro nenhum.
    Por isso o DBSCAN roda sobre `ST_Transform(geom, srid_calculo)`. Com o SRID de
    cálculo do projeto (31983, SIRGAS 2000 / UTM 23S, que cobre São Paulo) a
    unidade é o metro e `eps_metros` é, de fato, uma distância em metros.
    `ST_ClusterDBSCAN` não aceita `geography`, então a reprojeção é o único caminho.

    Por que particionar por tipo (`PARTITION BY tipo_id`): um degrau e um
    obstáculo a 1 m um do outro são duas barreiras diferentes, não duas
    confirmações da mesma barreira. Cada tipo é agrupado separadamente.

    O que é ruído: o DBSCAN chama de ponto-núcleo o alerta que tem pelo menos
    `min_pontos` alertas (contando ele mesmo) a até `eps_metros` de distância.
    Um cluster é formado por núcleos vizinhos entre si e pelos alertas ao alcance
    deles. O alerta que não é núcleo nem está ao alcance de um núcleo recebe
    cluster NULL: é ruído, um relato sem nenhum outro que o corrobore. Ruído não
    é descarte: o alerta volta a ser avaliado em toda execução, porque pode
    ganhar vizinhos com os alertas que chegarem depois (T4, D6).

    Efeito de encadeamento (T5): o DBSCAN liga vizinhos de vizinhos. Alertas a
    cada 7 m ao longo de uma calçada, com `eps` de 8 m, formam um único cluster de
    comprimento arbitrário, embora os extremos fiquem longe um do outro. Uma
    calçada inteira irregular pode virar uma só "barreira", com o centroide no
    meio dela. O efeito foi MEDIDO com dados sintéticos na análise de
    sensibilidade (população `sequencia`, Task 4): barreiras distintas a 15 m
    ficam separadas com eps = 8 m e começam a se fundir a partir de ~10,3 m. Os
    números e o que falta decidir estão em `docs/decisoes-pendentes.md` (T5).
    Aqui o efeito é aceito como propriedade do algoritmo.

    Determinismo (`ORDER BY id` dentro do `OVER`): o DBSCAN percorre os alertas
    em ordem, e dois detalhes dependem dessa ordem. (1) A numeração dos clusters,
    que segue a ordem em que cada cluster é encontrado. (2) O destino de um ponto
    de BORDA, que não é núcleo mas está ao alcance de núcleos de dois clusters
    diferentes: ele fica com o primeiro cluster que o alcança. Sem ordem explícita,
    a ordem seria a física da tabela, que muda com qualquer `UPDATE` (MVCC).
    Verificado no PostGIS 3.4.3 do projeto: o `ORDER BY` do `OVER` é respeitado
    (inverter a ordem inverte a numeração e o destino do ponto de borda), e a
    função lê a partição inteira, sem se limitar à moldura (frame) padrão que o
    `ORDER BY` cria. Com `ORDER BY id`, o resultado é reproduzível: a numeração
    segue o menor id de cada cluster e o ponto de borda fica com o cluster do
    núcleo de menor id que o alcança (ver
    `test_ponto_de_borda_disputado_vai_para_o_cluster_de_menor_id`). Com
    `min_pontos = 2` (o valor provisório do projeto) não existem pontos de borda,
    porque todo alerta com um vizinho já é núcleo; a ordem só afeta a numeração.
    """
    linhas = conexao.execute(
        """
        SELECT id,
               tipo_id,
               ST_ClusterDBSCAN(
                   ST_Transform(geom, %(srid_calculo)s),
                   eps := %(eps_metros)s,
                   minpoints := %(min_pontos)s
               ) OVER (PARTITION BY tipo_id ORDER BY id) AS cluster
        FROM alertas
        WHERE origem = %(origem)s
          AND status IN ('bruto', 'ruido_isolado', 'agrupado')
        ORDER BY id
        """,
        {
            "srid_calculo": srid_calculo,
            "eps_metros": eps_metros,
            "min_pontos": min_pontos,
            "origem": origem,
        },
    ).fetchall()
    return [
        RotuloAlerta(alerta_id=alerta_id, tipo_id=tipo_id, cluster=cluster)
        for alerta_id, tipo_id, cluster in linhas
    ]
