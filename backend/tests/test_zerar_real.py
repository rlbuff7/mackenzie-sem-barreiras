"""Testes de `./db/banco.sh zerar-real`: limpeza dos dados reais antes da coleta (R23).

O subcomando roda o psql de dentro do container, numa conexão à parte, então não
enxerga a transação desfeita da fixture `conexao`. Por isso os dados daqui são
CONFIRMADOS (commit) no banco de teste e apagados no fim, mesmo se o teste falhar.
O subcomando recebe `BANCO_ALVO` com o banco de teste: nunca roda contra o banco
de desenvolvimento.
"""

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.config import obter_configuracoes
from tests.auxiliares import inserir_alerta

_RAIZ_REPO = Path(__file__).resolve().parent.parent.parent
_TABELAS = ("alertas", "barreiras", "alertas_rejeitados", "execucoes_pipeline")
_ORIGENS = ("real", "simulacao")
_CONFIRMACAO = "--sim-apagar-dados-reais"

# Por origem: 2 alertas (1 agrupado numa barreira, 1 bruto), 1 barreira,
# 1 rejeitado e a linha de execucoes_pipeline.
_POR_ORIGEM = {"alertas": 2, "barreiras": 1, "alertas_rejeitados": 1, "execucoes_pipeline": 1}


def _contagens(conexao: psycopg.Connection) -> dict[tuple[str, str], int]:
    return {
        (tabela, origem): conexao.execute(
            f"SELECT count(*) FROM {tabela} WHERE origem = %s", (origem,)
        ).fetchone()[0]
        for tabela in _TABELAS
        for origem in _ORIGENS
    }


def _inserir_dados_da_origem(conexao: psycopg.Connection, origem: str) -> None:
    barreira_id = conexao.execute(
        """
        INSERT INTO barreiras (geom, tipo_id, confirmacoes, status, origem)
        SELECT ST_SetSRID(ST_MakePoint(-46.6524631, -23.5471938), 4326), id, 1,
               'pendente', %(origem)s
        FROM tipos_barreira WHERE codigo = 'degrau'
        RETURNING id
        """,
        {"origem": origem},
    ).fetchone()[0]
    inserir_alerta(conexao, status="agrupado", barreira_id=barreira_id, origem=origem)
    inserir_alerta(conexao, origem=origem)
    conexao.execute(
        "INSERT INTO alertas_rejeitados (payload, erros, origem) VALUES (%s, %s, %s)",
        (Jsonb({"latitude": 200}), Jsonb([{"campo": "latitude", "erro": "..."}]), origem),
    )
    conexao.execute(
        """
        INSERT INTO execucoes_pipeline
            (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
        VALUES (%s, 8, 2, 3, 31983)
        """,
        (origem,),
    )


@pytest.fixture
def conexao_confirmada() -> Iterator[psycopg.Connection]:
    """Banco de teste com dados das duas origens, CONFIRMADOS; limpo no fim.

    Os outros testes desfazem tudo o que gravam, então as quatro tabelas começam
    vazias; a limpeza final as devolve a esse estado.
    """
    conexao = psycopg.connect(obter_configuracoes().conninfo, autocommit=True)
    try:
        assert set(_contagens(conexao).values()) == {0}, "banco de teste não está vazio"
        with conexao.transaction():
            for origem in _ORIGENS:
                _inserir_dados_da_origem(conexao, origem)
        yield conexao
    finally:
        with conexao.transaction():
            for tabela in _TABELAS:
                conexao.execute(f"DELETE FROM {tabela}")
        conexao.close()


def _zerar_real(*argumentos: str) -> subprocess.CompletedProcess[str]:
    banco_de_teste = obter_configuracoes().postgres_db
    assert banco_de_teste.endswith("_teste")  # nunca o banco de desenvolvimento
    return subprocess.run(
        [str(_RAIZ_REPO / "db" / "banco.sh"), "zerar-real", *argumentos],
        cwd=_RAIZ_REPO,
        env={**os.environ, "BANCO_ALVO": banco_de_teste},
        capture_output=True,
        text=True,
        check=False,
    )


def _linha_da_tabela(saida: str, tabela: str, real: int, simulacao: int) -> bool:
    """A tabela de contagens do subcomando tem a linha `tabela | real | simulacao`."""
    padrao = rf"^\s*{tabela}\s*\|\s*{real}\s*\|\s*{simulacao}\s*$"
    return re.search(padrao, saida, flags=re.MULTILINE) is not None


def test_sem_confirmacao_mostra_as_contagens_nao_apaga_e_sai_com_1(
    conexao_confirmada: psycopg.Connection,
) -> None:
    antes = _contagens(conexao_confirmada)

    resultado = _zerar_real()

    assert resultado.returncode == 1
    for tabela, quantidade in _POR_ORIGEM.items():
        assert _linha_da_tabela(resultado.stdout, tabela, quantidade, quantidade), resultado.stdout
    assert _CONFIRMACAO in resultado.stderr
    assert _contagens(conexao_confirmada) == antes


def test_confirmacao_diferente_da_exata_nao_apaga(
    conexao_confirmada: psycopg.Connection,
) -> None:
    antes = _contagens(conexao_confirmada)

    resultado = _zerar_real("--sim")

    assert resultado.returncode == 1
    assert _contagens(conexao_confirmada) == antes


def test_com_confirmacao_apaga_so_a_origem_real(
    conexao_confirmada: psycopg.Connection,
) -> None:
    resultado = _zerar_real(_CONFIRMACAO)

    assert resultado.returncode == 0, resultado.stderr
    depois = _contagens(conexao_confirmada)
    for tabela, quantidade in _POR_ORIGEM.items():
        assert depois[(tabela, "real")] == 0
        assert depois[(tabela, "simulacao")] == quantidade
        # Mostra as contagens antes e depois.
        assert _linha_da_tabela(resultado.stdout, tabela, quantidade, quantidade)
        assert _linha_da_tabela(resultado.stdout, tabela, 0, quantidade)
