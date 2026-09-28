"""Testes do estágio 3 (agrupamento DBSCAN): `app/validacao/clustering.py`."""

import psycopg

from app.validacao.clustering import RotuloAlerta, rotular_clusters
from tests.auxiliares import LATITUDE_CAMPUS, LONGITUDE_CAMPUS, inserir_alerta, ponto_deslocado

# G8: valores de teste explícitos, sem passar por Configuracoes.
_EPS_METROS = 8
_MIN_PONTOS = 2
_SRID_CALCULO = 31983


def _rotular(conexao: psycopg.Connection, **sobrescritas: object) -> dict[int, RotuloAlerta]:
    parametros: dict[str, object] = {
        "origem": "simulacao",
        "eps_metros": _EPS_METROS,
        "min_pontos": _MIN_PONTOS,
        "srid_calculo": _SRID_CALCULO,
    }
    parametros.update(sobrescritas)
    return {rotulo.alerta_id: rotulo for rotulo in rotular_clusters(conexao, **parametros)}


def _alerta_a(conexao: psycopg.Connection, norte_metros: float, **campos: object) -> int:
    """Insere um alerta a `norte_metros` ao norte do centro do campus."""
    latitude, longitude = ponto_deslocado(
        conexao, LATITUDE_CAMPUS, LONGITUDE_CAMPUS, norte_metros, 0
    )
    return inserir_alerta(conexao, latitude=latitude, longitude=longitude, **campos)


def test_dois_alertas_do_mesmo_tipo_a_5_metros_ficam_no_mesmo_cluster(
    conexao: psycopg.Connection,
) -> None:
    primeiro = _alerta_a(conexao, 0)
    segundo = _alerta_a(conexao, 5)

    rotulos = _rotular(conexao)

    assert rotulos[primeiro].cluster is not None
    assert rotulos[primeiro].cluster == rotulos[segundo].cluster
    assert rotulos[primeiro].tipo_id == rotulos[segundo].tipo_id


def test_rotular_clusters_so_le_nao_altera_status(conexao: psycopg.Connection) -> None:
    primeiro = _alerta_a(conexao, 0)
    segundo = _alerta_a(conexao, 5)

    _rotular(conexao)

    status = conexao.execute(
        "SELECT status FROM alertas WHERE id IN (%s, %s)", (primeiro, segundo)
    ).fetchall()
    assert status == [("bruto",), ("bruto",)]


def test_alertas_a_20_metros_sao_ruido(conexao: psycopg.Connection) -> None:
    primeiro = _alerta_a(conexao, 0)
    segundo = _alerta_a(conexao, 20)

    rotulos = _rotular(conexao)

    assert rotulos[primeiro].cluster is None
    assert rotulos[segundo].cluster is None


def test_tipos_diferentes_a_1_metro_nao_se_agrupam(conexao: psycopg.Connection) -> None:
    degrau = _alerta_a(conexao, 0, tipo="degrau")
    obstaculo = _alerta_a(conexao, 1, tipo="obstaculo")

    rotulos = _rotular(conexao)

    assert rotulos[degrau].cluster is None
    assert rotulos[obstaculo].cluster is None


def test_eps_e_em_metros_5_metros_com_eps_3_e_ruido(conexao: psycopg.Connection) -> None:
    """Se `eps` fosse interpretado em graus (SRID 4326), 3 seria ~330 km e os dois
    alertas, a 5 m um do outro, cairiam no mesmo cluster (CLAUDE.md §5)."""
    primeiro = _alerta_a(conexao, 0)
    segundo = _alerta_a(conexao, 5)

    rotulos = _rotular(conexao, eps_metros=3)

    assert rotulos[primeiro].cluster is None
    assert rotulos[segundo].cluster is None


def test_descartado_nao_entra_no_agrupamento(conexao: psycopg.Connection) -> None:
    bruto = _alerta_a(conexao, 0)
    descartado = _alerta_a(conexao, 1, status="descartado", motivo_descarte="fora_da_area")

    rotulos = _rotular(conexao)

    assert descartado not in rotulos
    assert rotulos[bruto].cluster is None


def test_ruido_isolado_de_execucao_anterior_volta_a_ser_avaliado(
    conexao: psycopg.Connection,
) -> None:
    """Ruído não é descarte (T4): um alerta marcado `ruido_isolado` entra de novo
    no agrupamento e pode formar cluster com um alerta que chegou depois."""
    antigo = _alerta_a(conexao, 0, status="ruido_isolado")
    novo = _alerta_a(conexao, 5)

    rotulos = _rotular(conexao)

    assert rotulos[antigo].cluster is not None
    assert rotulos[antigo].cluster == rotulos[novo].cluster


def test_origens_nao_se_misturam(conexao: psycopg.Connection) -> None:
    real = _alerta_a(conexao, 0, origem="real")
    simulacao = _alerta_a(conexao, 1, origem="simulacao")

    rotulos_real = _rotular(conexao, origem="real")

    assert set(rotulos_real) == {real}
    assert rotulos_real[real].cluster is None
    assert simulacao not in rotulos_real


def test_encadeamento_alertas_a_cada_7_metros_viram_um_cluster(
    conexao: psycopg.Connection,
) -> None:
    """Efeito de encadeamento do DBSCAN (T5, ainda em aberto): cada alerta está a
    7 m do vizinho (< eps de 8 m), então os três formam UM cluster — embora os
    extremos estejam a 14 m, bem acima de `eps`. Documenta o comportamento; a
    discussão (e a medição com dados sintéticos) fica para a Task 4."""
    alertas = [_alerta_a(conexao, norte) for norte in (0, 7, 14)]

    rotulos = _rotular(conexao)

    clusters = {rotulos[alerta].cluster for alerta in alertas}
    assert len(clusters) == 1
    assert None not in clusters


def test_ponto_de_borda_disputado_vai_para_o_cluster_de_menor_id(
    conexao: psycopg.Connection,
) -> None:
    """Determinismo: o resultado depende do id, não da ordem física das linhas.

    Com `min_pontos=4` e `eps=9,5 m`: grupo A (4 alertas a 0–3 m) e grupo B (4
    alertas a 21–24 m) são clusters; o alerta a 12 m tem só 2 vizinhos (a 9 m
    de A e a 9 m de B), então é ponto de BORDA, alcançável pelos dois. O
    DBSCAN o entrega ao primeiro cluster que o alcança na ordem de leitura.

    Os ids de A são os menores. Em seguida, um `UPDATE` de `status` (coluna
    indexada, então não é um HOT update) grava versões novas das linhas de A no
    fim da tabela e do índice (MVCC): tanto uma varredura sequencial quanto uma
    pelo índice `(origem, status)` passam a ler A por último. Sem `ORDER BY id`
    dentro do `OVER`, o ponto de borda iria para B (conferido removendo o
    `ORDER BY id`: este teste falha); com `ORDER BY id`, vai para A.

    Um `UPDATE` só de `descricao` NÃO serviria: é HOT, o índice continua
    apontando para a posição original e a leitura pelo índice segue na ordem
    de inserção.
    """
    grupo_a = [_alerta_a(conexao, norte) for norte in (0, 1, 2, 3)]
    borda = _alerta_a(conexao, 12)
    grupo_b = [_alerta_a(conexao, norte) for norte in (21, 22, 23, 24)]
    conexao.execute("UPDATE alertas SET status = 'ruido_isolado' WHERE id = ANY(%s)", (grupo_a,))

    rotulos = _rotular(conexao, eps_metros=9.5, min_pontos=4)

    cluster_a = {rotulos[alerta].cluster for alerta in grupo_a}
    cluster_b = {rotulos[alerta].cluster for alerta in grupo_b}
    assert len(cluster_a) == 1
    assert len(cluster_b) == 1
    assert cluster_a != cluster_b
    assert rotulos[borda].cluster in cluster_a


def test_sem_alertas_devolve_lista_vazia(conexao: psycopg.Connection) -> None:
    assert _rotular(conexao) == {}
