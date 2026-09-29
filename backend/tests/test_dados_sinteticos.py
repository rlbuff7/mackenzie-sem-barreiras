"""Testes do experimento com dados sintéticos (Task 4; CLAUDE.md §9, D8).

SIMULAÇÃO: todo dado gerado aqui é sintético e gravado com `origem='simulacao'` (G10).

Cobre `scripts/gerar_dados_sinteticos.py` (geração determinística, distâncias mínimas,
geofence, inválidos, limpeza, avaliação e um teste de eficácia ponta a ponta),
`scripts/analisar_sensibilidade.py` (cada rodada da grade é desfeita) e a montagem dos
estágios de `scripts/gerar_figura_funil.py` (sem testar o matplotlib).
"""

import math
from collections import Counter
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app.config import obter_configuracoes
from app.validacao.entrada import ResultadoEntrada, registrar_alerta
from app.validacao.geofence import ponto_dentro_da_area
from app.validacao.pipeline import executar_pipeline
from scripts.analisar_sensibilidade import (
    COLUNAS_CSV,
    PADRAO_SENSIBILIDADE,
    DistanciasDeReferencia,
    analisar_grade,
    distancias_de_referencia,
    executar_analise,
    formatar_referencias,
    linha_csv,
)
from scripts.gerar_dados_sinteticos import (
    CATEGORIAS,
    CENTRO_LATITUDE,
    CENTRO_LONGITUDE,
    FATOR_SEPARACAO,
    RAIO_FORA_MAXIMO_METROS,
    RAIO_FORA_MINIMO_METROS,
    RAIO_GERACAO_METROS,
    SESSOES_VARIAVEIS,
    VARIACOES_INVALIDAS,
    EstadoAlerta,
    EstadoFinal,
    ItemGerado,
    ItemRegistrado,
    OpcoesGeracao,
    avaliar,
    avisos_de_geracao,
    deslocar_ponto,
    gerar_populacoes,
    ler_estado_final,
    ler_tipos_ativos,
    limpar_simulacao,
    registrar_populacoes,
    sufixo_das_opcoes,
)
from scripts.gerar_figura_funil import OrigemNaoProcessada, montar_funil
from tests.auxiliares import inserir_alerta

# G8: valores de teste explícitos, sem passar por Configuracoes.
_EPS_METROS = 8
_MIN_PONTOS = 2
_MIN_CONFIRMACOES = 3
_SRID_CALCULO = 31983
_SRID_ARMAZENAMENTO = 4326
_SEPARACAO_METROS = FATOR_SEPARACAO * _EPS_METROS

# As cinco populações de controle (D8); `sequencia` fica desligada por padrão.
_CONTROLE = ("aglomerado", "sessao_repetida", "ruido", "fora_da_area", "invalido")

# Os quatro códigos do seed (db/seeds/001_tipos_barreira.sql), em ordem alfabética.
_TIPOS = ("ausencia_rampa", "calcada_irregular", "degrau", "obstaculo")

# Configuração pequena e bem separada para os testes que batem no banco.
_OPCOES_PEQUENAS = OpcoesGeracao(
    semente=7,
    aglomerados=3,
    pontos_por_aglomerado=4,
    dispersao_metros=3,
    sessao_repetida=2,
    ruido=5,
    fora_da_area=3,
    invalidos=5,
)


def _gerar(opcoes: OpcoesGeracao | None = None) -> list[ItemGerado]:
    """Gera sem banco, com os padrões da CLI quando `opcoes` é None."""
    return gerar_populacoes(opcoes or OpcoesGeracao(), tipos=_TIPOS, eps_metros=_EPS_METROS)


# O maior eps da grade da sensibilidade: as sequências ficam a 4 × ele do resto.
_EPS_MAXIMO_METROS = 20
_OPCOES_COM_SEQUENCIAS = OpcoesGeracao(sequencias=5)


def _gerar_com_sequencias(opcoes: OpcoesGeracao = _OPCOES_COM_SEQUENCIAS) -> list[ItemGerado]:
    return gerar_populacoes(
        opcoes, tipos=_TIPOS, eps_metros=_EPS_METROS, eps_maximo_metros=_EPS_MAXIMO_METROS
    )


def _media_metros(itens: list[ItemGerado]) -> tuple[float, float]:
    return (
        sum(i.norte_metros for i in itens) / len(itens),
        sum(i.leste_metros for i in itens) / len(itens),
    )


def _da_categoria(itens: list[ItemGerado], categoria: str) -> list[ItemGerado]:
    return [item for item in itens if item.categoria == categoria]


def _distancia_metros(a: ItemGerado, b: ItemGerado) -> float:
    """Distância no plano local em que o gerador sorteia os pontos (metros)."""
    return math.hypot(a.norte_metros - b.norte_metros, a.leste_metros - b.leste_metros)


def _distancia_ao_centro_metros(item: ItemGerado) -> float:
    return math.hypot(item.norte_metros, item.leste_metros)


def _distancia_geodesica_metros(
    conexao: psycopg.Connection, lat_a: float, lon_a: float, lat_b: float, lon_b: float
) -> float:
    """Distância no elipsoide (`geography`), independente da aproximação local."""
    return conexao.execute(
        """
        SELECT ST_Distance(
            ST_SetSRID(ST_MakePoint(%(lon_a)s, %(lat_a)s), 4326)::geography,
            ST_SetSRID(ST_MakePoint(%(lon_b)s, %(lat_b)s), 4326)::geography
        )
        """,
        {"lat_a": lat_a, "lon_a": lon_a, "lat_b": lat_b, "lon_b": lon_b},
    ).fetchone()[0]


# --- geração: determinismo e quantidades ---


def test_mesma_semente_gera_as_mesmas_populacoes() -> None:
    assert _gerar() == _gerar()


def test_sementes_diferentes_geram_populacoes_diferentes() -> None:
    assert _gerar(OpcoesGeracao(semente=1)) != _gerar(OpcoesGeracao(semente=2))


def test_mudar_a_quantidade_de_ruido_nao_move_os_grupos() -> None:
    """Cada categoria tem o seu próprio gerador aleatório: pedir mais ruído não
    muda onde os aglomerados caem (os grupos são sorteados antes do ruído)."""
    grupos_padrao = [i for i in _gerar() if i.grupo is not None]
    grupos_com_mais_ruido = [i for i in _gerar(OpcoesGeracao(ruido=60)) if i.grupo is not None]

    assert grupos_padrao == grupos_com_mais_ruido


def test_quantidades_por_categoria_seguem_as_opcoes() -> None:
    contagem = Counter(item.categoria for item in _gerar())

    assert contagem == {
        "aglomerado": 20 * 4,
        "sessao_repetida": 5 * 4,
        "ruido": 40,
        "fora_da_area": 30,
        "invalido": 10,
    }
    assert set(contagem) == set(CATEGORIAS) - {"sequencia"}  # sequências: desligadas


def test_aglomerado_tem_uma_sessao_por_relato_e_sessao_repetida_uma_so() -> None:
    itens = _gerar()
    for categoria, sessoes_esperadas in (("aglomerado", 4), ("sessao_repetida", 1)):
        grupos: dict[int, list[ItemGerado]] = {}
        for item in _da_categoria(itens, categoria):
            grupos.setdefault(item.grupo, []).append(item)
        for relatos in grupos.values():
            assert len(relatos) == 4
            assert len({r.payload["sessao_id"] for r in relatos}) == sessoes_esperadas
            assert len({r.payload["tipo"] for r in relatos}) == 1


def test_sessoes_variaveis_sorteiam_de_2_a_5_relatos_de_sessoes_distintas() -> None:
    """Com `sessoes_variaveis`, cada aglomerado tem k relatos de k sessões distintas,
    k sorteado de SESSOES_VARIAVEIS pela semente; a sessão repetida não muda."""
    opcoes = OpcoesGeracao(sessoes_variaveis=True)
    itens = _gerar(opcoes)
    assert itens == _gerar(opcoes)

    tamanhos = Counter(i.grupo for i in _da_categoria(itens, "aglomerado"))
    assert set(tamanhos.values()) <= set(SESSOES_VARIAVEIS)
    assert len(set(tamanhos.values())) >= 3  # 20 grupos: o sorteio varia de verdade
    for grupo in tamanhos:
        relatos = [i for i in _da_categoria(itens, "aglomerado") if i.grupo == grupo]
        assert len({r.payload["sessao_id"] for r in relatos}) == len(relatos)
    assert Counter(i.grupo for i in _da_categoria(itens, "sessao_repetida")) == {
        grupo: 4 for grupo in range(5)
    }


def test_ruido_e_fora_da_area_tem_sessoes_distintas_e_sem_grupo() -> None:
    itens = _da_categoria(_gerar(), "ruido") + _da_categoria(_gerar(), "fora_da_area")

    assert all(item.grupo is None for item in itens)
    assert len({item.payload["sessao_id"] for item in itens}) == len(itens)


def test_todo_payload_valido_e_rotulado_como_simulacao() -> None:
    for item in _gerar():
        if item.categoria != "invalido":
            assert item.payload["descricao"].startswith("SIMULAÇÃO")


# --- geração: geometria ---


def test_pontos_de_um_grupo_ficam_dentro_da_dispersao() -> None:
    """Raio máximo `dispersao_metros` em torno do centro do grupo: dois relatos do
    mesmo grupo ficam a no máximo 2 × dispersão um do outro (abaixo do eps)."""
    itens = [i for i in _gerar() if i.grupo is not None]
    for a in itens:
        for b in itens:
            if (a.categoria, a.grupo) == (b.categoria, b.grupo):
                assert _distancia_metros(a, b) <= 2 * 3 + 1e-9


def test_grupos_diferentes_ficam_separados_por_4_eps_entre_centros() -> None:
    """Centros a ≥ 4 × eps: dois relatos de grupos diferentes (de qualquer tipo)
    ficam a pelo menos 4 × eps − 2 × dispersão."""
    itens = [i for i in _gerar() if i.grupo is not None]
    for a in itens:
        for b in itens:
            if (a.categoria, a.grupo) != (b.categoria, b.grupo):
                assert _distancia_metros(a, b) >= _SEPARACAO_METROS - 2 * 3


def test_ruido_fica_a_4_eps_de_qualquer_outro_ponto_do_mesmo_tipo() -> None:
    itens = _gerar()
    dentro = [i for i in itens if i.categoria in ("aglomerado", "sessao_repetida", "ruido")]
    for ruido in _da_categoria(itens, "ruido"):
        for outro in dentro:
            if outro is not ruido and outro.payload["tipo"] == ruido.payload["tipo"]:
                assert _distancia_metros(ruido, outro) >= _SEPARACAO_METROS


def test_grupos_e_ruido_ficam_a_ate_400_m_e_fora_da_area_entre_700_e_1500_m() -> None:
    for item in _gerar():
        distancia_metros = _distancia_ao_centro_metros(item)
        if item.categoria == "fora_da_area":
            assert RAIO_FORA_MINIMO_METROS <= distancia_metros <= RAIO_FORA_MAXIMO_METROS
        elif item.categoria == "invalido":
            assert distancia_metros <= RAIO_GERACAO_METROS
        else:
            assert distancia_metros <= RAIO_GERACAO_METROS + 3


def test_amostragem_impossivel_falha_com_mensagem_clara() -> None:
    """Com eps = 150 m, os centros precisariam de 600 m entre si num disco de 800 m
    de diâmetro: dez grupos não cabem, e o gerador desiste em vez de travar."""
    with pytest.raises(ValueError, match="não coube"):
        gerar_populacoes(OpcoesGeracao(aglomerados=10), tipos=_TIPOS, eps_metros=150)


def test_sequencias_nao_mudam_as_populacoes_de_controle() -> None:
    """As sequências são sorteadas depois do controle: ligá-las não move nada dele."""
    com_sequencias = _gerar_com_sequencias()

    assert [i for i in com_sequencias if i.categoria != "sequencia"] == _gerar()
    assert com_sequencias == _gerar_com_sequencias()


def test_sequencia_tem_barreiras_distintas_em_linha_com_o_espacamento_pedido() -> None:
    """5 sequências × 4 barreiras × 4 relatos. Numa sequência, todas as barreiras
    têm o mesmo tipo, cada uma com 4 sessões distintas, e os centros ficam em linha
    a 15 m: centros médios consecutivos a 15 ± 2 × 3 m, extremos a 45 ± 2 × 3 m."""
    itens = _da_categoria(_gerar_com_sequencias(), "sequencia")
    assert len(itens) == 5 * 4 * 4

    for sequencia in range(5):
        da_sequencia = [i for i in itens if i.sequencia == sequencia]
        assert len({i.payload["tipo"] for i in da_sequencia}) == 1
        grupos = sorted({i.grupo for i in da_sequencia})
        assert len(grupos) == 4
        medias_metros = []
        for grupo in grupos:
            relatos = [i for i in da_sequencia if i.grupo == grupo]
            assert len({r.payload["sessao_id"] for r in relatos}) == 4
            medias_metros.append(_media_metros(relatos))
        for a, b in zip(medias_metros, medias_metros[1:], strict=False):
            assert 15 - 6 <= math.dist(a, b) <= 15 + 6
        assert 45 - 6 <= math.dist(medias_metros[0], medias_metros[-1]) <= 45 + 6


def test_sequencia_fica_isolada_a_4_vezes_o_maior_eps_de_tudo_do_mesmo_tipo() -> None:
    """Só pode haver fusão DENTRO de uma sequência: de qualquer outro ponto do mesmo
    tipo (controle ou outra sequência), cada ponto dela fica a ≥ 4 × 20 m."""
    itens = _gerar_com_sequencias()
    dentro = [i for i in itens if i.categoria in ("aglomerado", "sessao_repetida", "ruido")]
    sequencias = _da_categoria(itens, "sequencia")
    for ponto in sequencias:
        assert math.hypot(ponto.norte_metros, ponto.leste_metros) <= RAIO_GERACAO_METROS + 3
        for outro in dentro + sequencias:
            if (
                outro.payload["tipo"] == ponto.payload["tipo"]
                and outro.sequencia != ponto.sequencia
            ):
                assert _distancia_metros(ponto, outro) >= FATOR_SEPARACAO * _EPS_MAXIMO_METROS


def test_sequencia_impossivel_falha_com_mensagem_clara() -> None:
    with pytest.raises(ValueError, match="não coube"):
        gerar_populacoes(
            OpcoesGeracao(sequencias=10), tipos=_TIPOS, eps_metros=8, eps_maximo_metros=150
        )


@pytest.mark.parametrize(
    "sobrescritas",
    [
        {"pontos_por_aglomerado": 1},
        {"aglomerados": -1},
        {"ruido": -1},
        {"dispersao_metros": -0.5},
        {"sequencias": -1},
        {"barreiras_por_sequencia": 1},
        {"espacamento_sequencia_metros": 0},
    ],
)
def test_opcoes_sem_sentido_sao_recusadas(sobrescritas: dict) -> None:
    with pytest.raises(ValueError):
        gerar_populacoes(OpcoesGeracao(**sobrescritas), tipos=_TIPOS, eps_metros=_EPS_METROS)


@pytest.mark.parametrize(
    ("dispersao_metros", "eps_maximo_metros", "avisa"),
    [
        (11.9, None, False),
        (12, None, True),  # 1,5 × eps: 4 × 8 − 2 × 12 = 8 m, já ao alcance de eps = 8
        (5.9, 20, False),
        (6, 20, True),  # na grade até 20 m: 4 × 8 − 2 × 6 = 20 m
    ],
)
def test_avisa_quando_a_dispersao_poe_grupos_vizinhos_ao_alcance(
    dispersao_metros: float, eps_maximo_metros: float | None, avisa: bool
) -> None:
    """A separação de 4 × eps vale entre CENTROS: relatos de grupos vizinhos ficam a
    ≥ 4 × eps − 2 × dispersão, fora do alcance só enquanto isso passa do eps."""
    avisos = avisos_de_geracao(
        OpcoesGeracao(dispersao_metros=dispersao_metros),
        eps_metros=_EPS_METROS,
        eps_maximo_metros=eps_maximo_metros,
        min_confirmacoes=_MIN_CONFIRMACOES,
    )

    assert any("dispersão" in aviso for aviso in avisos) is avisa


def test_avisa_quando_nenhum_aglomerado_pode_ser_confirmado() -> None:
    avisos = avisos_de_geracao(
        OpcoesGeracao(pontos_por_aglomerado=2), eps_metros=_EPS_METROS, min_confirmacoes=3
    )

    assert any("nenhum aglomerado" in aviso for aviso in avisos)
    assert avisos_de_geracao(OpcoesGeracao(), eps_metros=_EPS_METROS, min_confirmacoes=3) == []


def test_sem_tipos_a_geracao_e_recusada() -> None:
    with pytest.raises(ValueError, match="tipo"):
        gerar_populacoes(OpcoesGeracao(), tipos=(), eps_metros=_EPS_METROS)


@pytest.mark.parametrize("distancia_metros", [10, 400, 1500])
@pytest.mark.parametrize("azimute_graus", [0, 45, 90, 135, 180, 270])
def test_conversao_local_de_metros_para_graus_erra_menos_de_0_1_por_cento(
    conexao: psycopg.Connection, distancia_metros: float, azimute_graus: float
) -> None:
    azimute = math.radians(azimute_graus)
    latitude, longitude = deslocar_ponto(
        CENTRO_LATITUDE,
        CENTRO_LONGITUDE,
        norte_metros=distancia_metros * math.cos(azimute),
        leste_metros=distancia_metros * math.sin(azimute),
    )

    geodesica_metros = _distancia_geodesica_metros(
        conexao, CENTRO_LATITUDE, CENTRO_LONGITUDE, latitude, longitude
    )

    assert abs(geodesica_metros - distancia_metros) / distancia_metros < 0.001


def test_ruido_fica_a_4_eps_do_vizinho_mais_proximo_tambem_no_elipsoide(
    conexao: psycopg.Connection,
) -> None:
    """A separação vale na distância geodésica, não só no plano local."""
    itens = _gerar()
    dentro = [i for i in itens if i.categoria in ("aglomerado", "sessao_repetida", "ruido")]
    for ruido in _da_categoria(itens, "ruido"):
        vizinho = min(
            (o for o in dentro if o is not ruido and o.payload["tipo"] == ruido.payload["tipo"]),
            key=lambda outro: _distancia_metros(ruido, outro),
        )
        local_metros = _distancia_metros(ruido, vizinho)
        geodesica_metros = _distancia_geodesica_metros(
            conexao,
            ruido.payload["latitude"],
            ruido.payload["longitude"],
            vizinho.payload["latitude"],
            vizinho.payload["longitude"],
        )
        assert abs(geodesica_metros - local_metros) / local_metros < 0.001
        assert geodesica_metros >= _SEPARACAO_METROS * (1 - 0.001)


# --- geração contra o banco: geofence real e schema real ---


def test_pontos_fora_da_area_ficam_fora_pelo_geofence_real(conexao: psycopg.Connection) -> None:
    for item in _gerar_com_sequencias():
        if item.categoria == "invalido":
            continue
        dentro = ponto_dentro_da_area(
            conexao, item.payload["latitude"], item.payload["longitude"], _SRID_ARMAZENAMENTO
        )
        assert dentro is (item.categoria != "fora_da_area"), item


def test_invalidos_cobrem_as_cinco_variacoes() -> None:
    variacoes = Counter(item.variacao for item in _da_categoria(_gerar(), "invalido"))

    assert variacoes == {variacao: 2 for variacao in VARIACOES_INVALIDAS}


def test_invalidos_sao_reprovados_no_estagio_1_pelo_campo_da_variacao(
    conexao: psycopg.Connection,
) -> None:
    campo_esperado = {
        "latitude_fora_da_faixa": "latitude",
        "tipo_inexistente": "tipo",
        "severidade_invalida": "severidade",
        "campo_faltando": "sessao_id",
        "campo_extra": "campo_extra",
    }
    config = obter_configuracoes()

    for item in _da_categoria(_gerar(), "invalido"):
        resultado = registrar_alerta(conexao, item.payload, origem="simulacao", config=config)
        assert resultado.aceito is False
        assert [erro.campo for erro in resultado.erros] == [campo_esperado[item.variacao]]

    rejeitados = conexao.execute(
        "SELECT count(*) FROM alertas_rejeitados WHERE origem = 'simulacao'"
    ).fetchone()[0]
    assert rejeitados == 10


def test_ler_tipos_ativos_devolve_os_codigos_do_seed_em_ordem(
    conexao: psycopg.Connection,
) -> None:
    assert ler_tipos_ativos(conexao) == list(_TIPOS)


# --- limpeza ---


def test_limpar_simulacao_apaga_so_a_origem_simulacao(conexao: psycopg.Connection) -> None:
    config = obter_configuracoes()
    real_id = inserir_alerta(conexao, origem="real")
    registrar_alerta(conexao, {"latitude": 999}, origem="real", config=config)
    registrar_populacoes(conexao, _gerar(_OPCOES_PEQUENAS), config=config)
    for origem in ("real", "simulacao"):
        executar_pipeline(
            conexao,
            origem=origem,
            eps_metros=_EPS_METROS,
            min_pontos=_MIN_PONTOS,
            min_confirmacoes=_MIN_CONFIRMACOES,
            srid_calculo=_SRID_CALCULO,
            srid_armazenamento=_SRID_ARMAZENAMENTO,
        )

    apagados = limpar_simulacao(conexao)

    assert apagados["alertas"] == 3 * 4 + 2 * 4 + 5 + 3
    assert apagados["alertas_rejeitados"] == 5
    assert apagados["barreiras"] == 3 + 2
    assert apagados["execucoes_pipeline"] == 1
    for tabela in ("alertas", "alertas_rejeitados", "barreiras", "execucoes_pipeline"):
        consulta = sql.SQL("SELECT origem, count(*) FROM {} GROUP BY origem").format(
            sql.Identifier(tabela)
        )
        por_origem = dict(conexao.execute(consulta).fetchall())
        assert "simulacao" not in por_origem, tabela
    assert conexao.execute("SELECT status FROM alertas WHERE id = %s", (real_id,)).fetchone() == (
        "ruido_isolado",
    )
    assert dict(
        conexao.execute("SELECT origem, count(*) FROM alertas_rejeitados GROUP BY 1").fetchall()
    ) == {"real": 1}
    assert conexao.execute(
        "SELECT count(*) FROM execucoes_pipeline WHERE origem = 'real'"
    ).fetchone() == (1,)


# --- avaliação (pura, com estados montados à mão) ---


def _registrado(
    alerta_id: int | None,
    categoria: str,
    grupo: int | None = None,
    tipo: str = "degrau",
    sessao: str | None = None,
) -> ItemRegistrado:
    """Item já registrado. `alerta_id=None` = reprovado no estágio 1. Sem `sessao`,
    cada chamada é uma sessão nova (uma pessoa diferente)."""
    item = ItemGerado(
        categoria=categoria,
        grupo=grupo,
        variacao="campo_extra" if categoria == "invalido" else None,
        norte_metros=0.0,
        leste_metros=0.0,
        payload={"tipo": tipo, "sessao_id": sessao or str(uuid4())},
    )
    aceito = alerta_id is not None
    return ItemRegistrado(
        item=item,
        resultado=ResultadoEntrada(
            aceito=aceito,
            id=alerta_id,
            status="bruto" if aceito else None,
            motivo_descarte=None,
        ),
    )


def _agrupado(barreira_id: int) -> EstadoAlerta:
    return EstadoAlerta(status="agrupado", motivo_descarte=None, barreira_id=barreira_id)


_RUIDO = EstadoAlerta(status="ruido_isolado", motivo_descarte=None, barreira_id=None)
_FORA = EstadoAlerta(status="descartado", motivo_descarte="fora_da_area", barreira_id=None)


def _cenario_perfeito() -> tuple[list[ItemRegistrado], EstadoFinal]:
    """Um aglomerado (alertas 1–3), uma sessão repetida (4–5), um ruído (6), um
    fora da área (7) e um inválido: cada um no destino esperado."""
    registrados = [
        _registrado(1, "aglomerado", 0),
        _registrado(2, "aglomerado", 0),
        _registrado(3, "aglomerado", 0),
        _registrado(4, "sessao_repetida", 0, sessao="uma-pessoa-so"),
        _registrado(5, "sessao_repetida", 0, sessao="uma-pessoa-so"),
        _registrado(6, "ruido"),
        _registrado(7, "fora_da_area"),
        _registrado(None, "invalido"),
    ]
    estado = EstadoFinal(
        alertas={
            1: _agrupado(10),
            2: _agrupado(10),
            3: _agrupado(10),
            4: _agrupado(11),
            5: _agrupado(11),
            6: _RUIDO,
            7: _FORA,
        },
        barreiras={10: "confirmada", 11: "pendente"},
    )
    return registrados, estado


def test_avaliar_cenario_perfeito_acerta_tudo() -> None:
    avaliacao = avaliar(*_cenario_perfeito(), min_confirmacoes=3)

    assert {c: r.taxa for c, r in avaliacao.por_categoria.items()} == {
        categoria: 1.0 for categoria in _CONTROLE
    } | {"sequencia": None}
    assert avaliacao.por_categoria["aglomerado"].esperado == 1
    assert avaliacao.por_categoria["aglomerado"].unidade == "grupos"
    assert avaliacao.por_categoria["ruido"].unidade == "alertas"
    assert avaliacao.barreiras_esperadas == {"confirmada": 1, "pendente": 1}
    assert avaliacao.barreiras_obtidas == {"confirmada": 1, "pendente": 1}
    assert avaliacao.barreiras_corretas == {"confirmada": 1, "pendente": 1}
    assert (avaliacao.grupos_fragmentados, avaliacao.fusoes_indevidas) == (0, 0)
    assert avaliacao.ruido_em_barreira == 0


def test_avaliar_monta_a_matriz_categoria_para_destino_final() -> None:
    avaliacao = avaliar(*_cenario_perfeito(), min_confirmacoes=3)

    assert avaliacao.confusao == {
        "aglomerado": {"barreira_confirmada": 3},
        "sessao_repetida": {"barreira_pendente": 2},
        "ruido": {"ruido_isolado": 1},
        "fora_da_area": {"descartado:fora_da_area": 1},
        "invalido": {"rejeitado_schema": 1},
        "sequencia": {},
    }


def test_avaliar_fusao_de_dois_grupos_nao_conta_acerto() -> None:
    registrados = [
        _registrado(1, "aglomerado", 0),
        _registrado(2, "aglomerado", 0),
        _registrado(3, "aglomerado", 1),
        _registrado(4, "aglomerado", 1),
    ]
    estado = EstadoFinal(
        alertas={i: _agrupado(10) for i in (1, 2, 3, 4)}, barreiras={10: "confirmada"}
    )

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    assert avaliacao.por_categoria["aglomerado"].obtido == 0
    assert avaliacao.fusoes_indevidas == 1
    assert avaliacao.grupos_fragmentados == 0


def test_avaliar_grupo_fragmentado_nao_conta_acerto() -> None:
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2, 3, 4)]
    estado = EstadoFinal(
        alertas={1: _agrupado(10), 2: _agrupado(10), 3: _agrupado(11), 4: _RUIDO},
        barreiras={10: "pendente", 11: "pendente"},
    )

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    assert avaliacao.por_categoria["aglomerado"].obtido == 0
    assert avaliacao.grupos_fragmentados == 1
    assert avaliacao.fusoes_indevidas == 0


def test_avaliar_barreira_com_status_errado_nao_conta_acerto() -> None:
    """Três sessões com min_confirmacoes = 3: deveria ser confirmada."""
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2, 3)]
    estado = EstadoFinal(alertas={i: _agrupado(10) for i in (1, 2, 3)}, barreiras={10: "pendente"})

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    assert avaliacao.por_categoria["aglomerado"].obtido == 0
    assert avaliacao.barreiras_obtidas == {"confirmada": 0, "pendente": 1}
    assert avaliacao.barreiras_corretas == {"confirmada": 0, "pendente": 0}


@pytest.mark.parametrize(
    ("min_confirmacoes", "status_esperado", "acerta"),
    [(2, "confirmada", False), (3, "pendente", True)],
)
def test_avaliar_status_esperado_segue_a_regra_das_sessoes(
    min_confirmacoes: int, status_esperado: str, acerta: bool
) -> None:
    """Um aglomerado de 2 sessões distintas numa barreira pendente só dele: com
    min_confirmacoes = 2 deveria estar confirmado (erro); com 3, pendente (acerto)."""
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2)]
    estado = EstadoFinal(alertas={1: _agrupado(10), 2: _agrupado(10)}, barreiras={10: "pendente"})

    avaliacao = avaliar(registrados, estado, min_confirmacoes=min_confirmacoes)

    assert avaliacao.por_categoria["aglomerado"].obtido == (1 if acerta else 0)
    esperadas = {"confirmada": 0, "pendente": 0} | {status_esperado: 1}
    assert avaliacao.barreiras_esperadas == esperadas


def test_avaliar_barreira_com_alerta_estranho_ao_grupo_nao_conta_acerto() -> None:
    """O alerta 99 não foi gerado nesta execução (sobra de outra, por exemplo): a
    barreira não é só do grupo, então o grupo não foi recuperado sozinho."""
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2)]
    estado = EstadoFinal(
        alertas={1: _agrupado(10), 2: _agrupado(10), 99: _agrupado(10)},
        barreiras={10: "confirmada"},
    )

    assert avaliar(registrados, estado, min_confirmacoes=3).por_categoria["aglomerado"].obtido == 0


def test_avaliar_alerta_ausente_do_banco_conta_como_grupo_incompleto() -> None:
    """Um alerta do grupo sumiu do banco (apagado por fora entre a geração e a
    leitura): o grupo não foi recuperado inteiro, e a avaliação não quebra."""
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2)]
    estado = EstadoFinal(alertas={1: _agrupado(10)}, barreiras={10: "confirmada"})

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    assert avaliacao.por_categoria["aglomerado"].obtido == 0
    assert (avaliacao.grupos_incompletos, avaliacao.grupos_fragmentados) == (1, 0)
    assert avaliacao.confusao["aglomerado"] == {"barreira_confirmada": 1, "ausente": 1}


def test_avaliar_grupo_com_um_relato_reprovado_na_entrada_nao_conta_acerto() -> None:
    """Três relatos aceitos numa barreira só deles, com o status certo, e um quarto
    reprovado no estágio 1: o grupo gerado tinha quatro relatos, então não foi
    recuperado inteiro. Contar só os aceitos daria 1 de 1 = 100%."""
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2, 3)]
    registrados.append(_registrado(None, "aglomerado", 0))
    estado = EstadoFinal(
        alertas={i: _agrupado(10) for i in (1, 2, 3)}, barreiras={10: "confirmada"}
    )

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    resultado = avaliacao.por_categoria["aglomerado"]
    assert (resultado.esperado, resultado.obtido) == (1, 0)
    assert (avaliacao.grupos_incompletos, avaliacao.grupos_fragmentados) == (1, 0)


def test_avaliar_grupo_todo_reprovado_continua_no_esperado() -> None:
    """Um grupo inteiro reprovado na entrada não some do denominador: é um grupo
    gerado que não virou barreira."""
    registrados = [_registrado(None, "aglomerado", 0) for _ in range(4)]
    registrados += [_registrado(None, "sessao_repetida", 0, sessao="s") for _ in range(2)]

    avaliacao = avaliar(registrados, EstadoFinal(alertas={}, barreiras={}), min_confirmacoes=3)

    for categoria in ("aglomerado", "sessao_repetida"):
        resultado = avaliacao.por_categoria[categoria]
        assert (resultado.esperado, resultado.obtido) == (1, 0)
    assert avaliacao.barreiras_esperadas == {"confirmada": 1, "pendente": 1}
    assert avaliacao.barreiras_obtidas == {"confirmada": 0, "pendente": 0}
    assert avaliacao.grupos_incompletos == 2


def test_avaliar_conta_so_as_barreiras_que_tocam_os_itens_avaliados() -> None:
    """A barreira 11 só tem o alerta 99, que não está entre os itens avaliados (outra
    população ou sobra de outra execução): não entra nas obtidas. É o que permite
    avaliar o controle e as sequências separadamente, no mesmo banco."""
    registrados = [_registrado(i, "aglomerado", 0) for i in (1, 2, 3)]
    estado = EstadoFinal(
        alertas={1: _agrupado(10), 2: _agrupado(10), 3: _agrupado(10), 99: _agrupado(11)},
        barreiras={10: "confirmada", 11: "confirmada"},
    )

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    assert avaliacao.barreiras_obtidas == {"confirmada": 1, "pendente": 0}
    assert avaliacao.por_categoria["aglomerado"].obtido == 1


def test_avaliar_ruido_agrupado_conta_como_ruido_em_barreira() -> None:
    registrados = [_registrado(1, "ruido"), _registrado(2, "ruido"), _registrado(3, "ruido")]
    estado = EstadoFinal(
        alertas={1: _agrupado(10), 2: _agrupado(10), 3: _RUIDO}, barreiras={10: "pendente"}
    )

    avaliacao = avaliar(registrados, estado, min_confirmacoes=3)

    assert avaliacao.ruido_em_barreira == 2
    assert avaliacao.por_categoria["ruido"].obtido == 1
    assert avaliacao.por_categoria["ruido"].taxa == pytest.approx(1 / 3)


def test_avaliar_categoria_vazia_tem_taxa_indefinida() -> None:
    avaliacao = avaliar(
        [_registrado(1, "ruido")],
        EstadoFinal(alertas={1: _RUIDO}, barreiras={}),
        min_confirmacoes=3,
    )

    assert avaliacao.por_categoria["aglomerado"].esperado == 0
    assert avaliacao.por_categoria["aglomerado"].taxa is None


# --- teste de eficácia ponta a ponta (banco de teste) ---


def test_ponta_a_ponta_pequena_acerta_100_por_cento_em_cada_categoria(
    conexao: psycopg.Connection,
) -> None:
    """Gerar → registrar (estágios 1 e 2) → pipeline (3 e 4) → avaliar, numa
    configuração pequena e bem separada: cada categoria acerta 100%."""
    config = obter_configuracoes()
    itens = gerar_populacoes(
        _OPCOES_PEQUENAS, tipos=ler_tipos_ativos(conexao), eps_metros=_EPS_METROS
    )

    registrados = registrar_populacoes(conexao, itens, config=config)
    resumo = executar_pipeline(
        conexao,
        origem="simulacao",
        eps_metros=_EPS_METROS,
        min_pontos=_MIN_PONTOS,
        min_confirmacoes=_MIN_CONFIRMACOES,
        srid_calculo=_SRID_CALCULO,
        srid_armazenamento=_SRID_ARMAZENAMENTO,
    )
    avaliacao = avaliar(registrados, ler_estado_final(conexao), min_confirmacoes=_MIN_CONFIRMACOES)

    assert {c: r.taxa for c, r in avaliacao.por_categoria.items()} == {
        categoria: 1.0 for categoria in _CONTROLE
    } | {"sequencia": None}
    assert avaliacao.barreiras_obtidas == {"confirmada": 3, "pendente": 2}
    assert (resumo.barreiras_confirmadas, resumo.barreiras_pendentes) == (3, 2)
    assert resumo.ruido_isolado == 5
    origens = conexao.execute("SELECT DISTINCT origem FROM alertas").fetchall()
    assert origens == [("simulacao",)]


# --- análise de sensibilidade ---


def test_analisar_grade_desfaz_cada_rodada_e_mede_cada_combinacao(
    conexao: psycopg.Connection,
) -> None:
    config = obter_configuracoes()
    registrados = registrar_populacoes(conexao, _gerar(_OPCOES_PEQUENAS), config=config)

    rodadas = analisar_grade(
        conexao,
        registrados,
        grade_eps_metros=(2, 8),
        grade_min_confirmacoes=(3, 5),
        min_pontos=_MIN_PONTOS,
        srid_calculo=_SRID_CALCULO,
        srid_armazenamento=_SRID_ARMAZENAMENTO,
    )

    assert [(r.eps_metros, r.min_confirmacoes) for r in rodadas] == [
        (2, 3),
        (2, 5),
        (8, 3),
        (8, 5),
    ]
    rodada_padrao = rodadas[2].controle
    assert rodada_padrao.por_categoria["aglomerado"].taxa == 1.0
    # min_confirmacoes = 5 com 4 sessões por aglomerado: nenhum se confirma, e é isso
    # que se esperava (a regra das sessões), então o acerto continua 100%.
    assert rodadas[3].controle.barreiras_obtidas == {"confirmada": 0, "pendente": 5}
    assert rodadas[3].controle.barreiras_esperadas == {"confirmada": 0, "pendente": 5}
    assert rodadas[3].controle.por_categoria["aglomerado"].taxa == 1.0
    # Nada ficou gravado: cada rodada foi desfeita.
    assert conexao.execute(
        "SELECT count(*) FROM barreiras WHERE origem = 'simulacao'"
    ).fetchone() == (0,)
    assert conexao.execute("SELECT count(*) FROM execucoes_pipeline").fetchone() == (0,)
    assert conexao.execute(
        "SELECT DISTINCT status FROM alertas WHERE origem = 'simulacao' ORDER BY 1"
    ).fetchall() == [("bruto",), ("descartado",)]


def test_analisar_grade_mede_as_sequencias_a_parte_e_elas_se_fundem_com_eps_grande(
    conexao: psycopg.Connection,
) -> None:
    """Sequências a 15 m com dispersão de até 3 m: barreiras vizinhas ficam entre
    9 e 21 m. Com eps = 8 m nenhuma se funde (100% separadas); com eps = 25 m cada
    sequência inteira vira UMA barreira. O controle não é afetado."""
    config = obter_configuracoes()
    opcoes = OpcoesGeracao(
        semente=7,
        aglomerados=3,
        sessao_repetida=1,
        ruido=3,
        fora_da_area=0,
        invalidos=0,
        sequencias=2,
        barreiras_por_sequencia=3,
    )
    itens = gerar_populacoes(opcoes, tipos=_TIPOS, eps_metros=_EPS_METROS, eps_maximo_metros=25)
    registrados = registrar_populacoes(conexao, itens, config=config)

    eps_8, eps_25 = analisar_grade(
        conexao,
        registrados,
        grade_eps_metros=(8, 25),
        grade_min_confirmacoes=(3,),
        min_pontos=_MIN_PONTOS,
        srid_calculo=_SRID_CALCULO,
        srid_armazenamento=_SRID_ARMAZENAMENTO,
    )

    separadas = eps_8.sequencia
    assert separadas.por_categoria["sequencia"].esperado == 6
    assert separadas.por_categoria["sequencia"].taxa == 1.0
    assert (sum(separadas.barreiras_obtidas.values()), separadas.fusoes_indevidas) == (6, 0)
    fundidas = eps_25.sequencia
    assert fundidas.por_categoria["sequencia"].obtido == 0
    assert (sum(fundidas.barreiras_obtidas.values()), fundidas.fusoes_indevidas) == (2, 2)
    assert eps_25.controle.por_categoria["aglomerado"].esperado == 3
    assert eps_25.controle.por_categoria["sequencia"].esperado == 0

    linha = linha_csv(eps_25, opcoes, config, distancias_de_referencia(itens), eps_maximo_metros=25)
    assert list(linha) == list(COLUNAS_CSV)
    assert linha["rotulo"] == "SIMULAÇÃO — dados sintéticos"
    assert linha["espacamento_sequencia_metros"] == 15
    assert linha["isolamento_sequencia_metros"] == 100
    assert linha["menor_entre_barreiras_da_sequencia_metros"] is not None


def _fotografia_do_banco(conexao: psycopg.Connection) -> dict[str, list[tuple]]:
    """Todas as linhas que a análise poderia tocar, com as colunas que importam
    (status, ligações, geometria), em ordem de id."""
    consultas = {
        "alertas": "SELECT id, origem, status, motivo_descarte, barreira_id, sessao_hash, "
        "tipo_id, geom FROM alertas ORDER BY id",
        "barreiras": "SELECT id, origem, status, confirmacoes, tipo_id, geom, criado_em "
        "FROM barreiras ORDER BY id",
        "alertas_rejeitados": "SELECT id, origem, payload, erros FROM alertas_rejeitados "
        "ORDER BY id",
        "execucoes_pipeline": "SELECT origem, eps_metros, min_pontos, min_confirmacoes, "
        "srid_calculo, executado_em FROM execucoes_pipeline ORDER BY origem",
    }
    return {tabela: conexao.execute(sql).fetchall() for tabela, sql in consultas.items()}


def test_executar_analise_nao_deixa_nenhum_rastro_no_banco(conexao: psycopg.Connection) -> None:
    """R18: a análise de sensibilidade inteira (limpar, gerar, cada rodada da grade)
    roda numa transação desfeita. Uma população canônica já processada, com a sua
    linha em execucoes_pipeline, e os dados reais ficam idênticos, linha a linha.

    A análise usa OUTRA população (com sequências) e OUTROS parâmetros (eps 12,
    min_confirmacoes 2) que a execução existente (eps 8, min_confirmacoes 3): se algo
    vazasse da transação, as linhas e a execução registrada mudariam."""
    config = obter_configuracoes()
    registrar_populacoes(conexao, _gerar(_OPCOES_PEQUENAS), config=config)
    inserir_alerta(conexao, origem="real")
    for origem in ("simulacao", "real"):
        executar_pipeline(
            conexao,
            origem=origem,
            eps_metros=_EPS_METROS,
            min_pontos=_MIN_PONTOS,
            min_confirmacoes=_MIN_CONFIRMACOES,
            srid_calculo=_SRID_CALCULO,
            srid_armazenamento=_SRID_ARMAZENAMENTO,
        )
    antes = _fotografia_do_banco(conexao)
    assert len(antes["barreiras"]) == 5 and len(antes["execucoes_pipeline"]) == 2

    resultado = executar_analise(
        conexao,
        OpcoesGeracao(semente=3, aglomerados=4, ruido=4, sequencias=1, sessoes_variaveis=True),
        config=config,
        grade_eps_metros=(12,),
        grade_min_confirmacoes=(2,),
    )

    assert _fotografia_do_banco(conexao) == antes
    assert resultado.alertas_de_simulacao_antes == 3 * 4 + 2 * 4 + 5 + 3
    (rodada,) = resultado.rodadas
    assert (rodada.eps_metros, rodada.min_confirmacoes) == (12, 2)
    assert rodada.controle.por_categoria["aglomerado"].esperado == 4
    assert rodada.sequencia.por_categoria["sequencia"].esperado == 4


def test_distancias_de_referencia_explicam_fragmentacao_e_fusao() -> None:
    """Com minpoints = 2, um grupo continua inteiro enquanto eps cobre o maior salto
    da sua árvore geradora mínima (0 → 4 → 8: salto 4, embora os extremos distem 8);
    a primeira fusão possível no controle é a menor distância entre grupos do mesmo
    tipo; o primeiro ruído a ganhar vizinho é o mais próximo de outro ponto do mesmo
    tipo. Nas sequências: a menor distância entre barreiras da MESMA sequência (eps
    em que elas começam a se fundir) e a menor distância de uma sequência ao resto."""

    def item(
        categoria: str,
        grupo: int | None,
        norte_metros: float,
        tipo: str = "degrau",
        sequencia: int | None = None,
    ) -> ItemGerado:
        return ItemGerado(
            categoria=categoria,
            grupo=grupo,
            variacao=None,
            norte_metros=norte_metros,
            leste_metros=0.0,
            payload={"tipo": tipo},
            sequencia=sequencia,
        )

    itens = [
        item("aglomerado", 0, 8.0),
        item("aglomerado", 0, 0.0),
        item("aglomerado", 0, 4.0),
        item("aglomerado", 1, 40.0),
        item("sessao_repetida", 0, 46.0),
        item("sessao_repetida", 0, 47.0),
        item("ruido", None, 100.0),
        item("ruido", None, 60.0, tipo="obstaculo"),  # sozinho no tipo: não conta
        item("fora_da_area", None, 48.0),  # descartado no geofence: não conta
        item("sequencia", 0, 300.0, sequencia=0),
        item("sequencia", 1, 312.0, sequencia=0),
        item("sequencia", 2, 326.0, sequencia=0),
        item("sequencia", 3, 400.0, sequencia=1),
    ]

    referencias = distancias_de_referencia(itens)

    assert referencias.maior_salto_dentro_de_grupo_metros == pytest.approx(4.0)
    assert referencias.menor_entre_grupos_metros == pytest.approx(6.0)
    assert referencias.menor_do_ruido_metros == pytest.approx(53.0)
    assert referencias.menor_entre_barreiras_da_sequencia_metros == pytest.approx(12.0)
    assert referencias.menor_da_sequencia_ao_resto_metros == pytest.approx(74.0)


def test_distancias_de_referencia_sem_pares_ficam_indefinidas() -> None:
    referencias = distancias_de_referencia([])

    assert referencias.maior_salto_dentro_de_grupo_metros is None
    assert referencias.menor_entre_grupos_metros is None
    assert referencias.menor_do_ruido_metros is None
    assert referencias.menor_entre_barreiras_da_sequencia_metros is None
    assert referencias.menor_da_sequencia_ao_resto_metros is None


def _referencias() -> DistanciasDeReferencia:
    return DistanciasDeReferencia(4.3, 44.9, 39.3, 10.3, 81.0)


def test_formatar_referencias_mostra_o_minpoints_da_configuracao() -> None:
    texto = formatar_referencias(_referencias(), min_pontos=2)

    assert "minpoints = 2" in texto
    assert "maior salto dentro de um grupo: 4,3 m" in texto


def test_formatar_referencias_com_minpoints_diferente_de_2_avisa_e_pula_a_arvore() -> None:
    """A leitura pela árvore geradora mínima só é exata com minpoints = 2."""
    texto = formatar_referencias(_referencias(), min_pontos=3)

    assert "minpoints = 3" in texto
    assert "AVISO" in texto
    assert "maior salto" not in texto


def test_sufixo_das_opcoes_so_aparece_fora_dos_padroes() -> None:
    """O nome do CSV/JSON leva as opções que diferem dos padrões do script, para que
    uma rodada exploratória nunca sobrescreva o arquivo canônico."""
    assert sufixo_das_opcoes(PADRAO_SENSIBILIDADE, PADRAO_SENSIBILIDADE) == ""
    assert sufixo_das_opcoes(OpcoesGeracao(), OpcoesGeracao()) == ""
    assert (
        sufixo_das_opcoes(
            OpcoesGeracao(dispersao_metros=10, sessoes_variaveis=True, sequencias=5, semente=7),
            PADRAO_SENSIBILIDADE,
        )
        == "-dispersao-metros-10"
    )
    assert (
        sufixo_das_opcoes(OpcoesGeracao(sequencias=5, ruido=60), OpcoesGeracao())
        == "-ruido-60-sequencias-5"
    )
    assert sufixo_das_opcoes(OpcoesGeracao(), PADRAO_SENSIBILIDADE) == (
        "-sessoes-variaveis-nao-sequencias-0"
    )


# --- figura do funil (só a montagem dos estágios; o matplotlib não é testado) ---


def _estatisticas(parametros: dict | None) -> dict:
    return {
        "origem": "simulacao",
        "rotulo": "SIMULAÇÃO — dados sintéticos",
        "alertas": {
            "recebidos": 180,
            "rejeitados_schema": 10,
            "descartados": {"fora_da_area": 30},
            "aguardando_pipeline": 0,
            "ruido_isolado": 40,
            "agrupados": 100,
        },
        "barreiras": {"total": 25, "pendentes": 5, "confirmadas": 20},
        "parametros": parametros,
        "executado_em": None if parametros is None else "2026-09-29T03:00:00+00:00",
        "gerado_em": "2026-09-29T03:05:00+00:00",
    }


def test_funil_recusa_origem_nunca_processada() -> None:
    with pytest.raises(OrigemNaoProcessada, match="rode o pipeline antes"):
        montar_funil(_estatisticas(None))


def test_funil_monta_os_estagios_com_a_unidade_de_cada_um() -> None:
    funil = montar_funil(_estatisticas({"eps_metros": 8.0, "min_pontos": 2, "min_confirmacoes": 3}))

    # O primeiro estágio conta RELATOS: inclui os reprovados no schema, que nunca
    # viram alerta. Ele fica no painel dos alertas, mas o rótulo diz "relatos".
    assert [(e.valor, e.unidade, e.unidade_do_valor) for e in funil.estagios] == [
        (180, "alertas", "relatos"),
        (170, "alertas", "alertas"),
        (140, "alertas", "alertas"),
        (100, "alertas", "alertas"),
        (25, "barreiras", "barreiras"),
        (20, "barreiras", "barreiras"),
    ]
    assert funil.estagios[0].rotulo == "Relatos recebidos"
    assert "estágios 3 e 4" in funil.legenda
    assert "SIMULAÇÃO" in funil.titulo
    assert "eps = 8 m" in funil.legenda
    assert "min_confirmacoes = 3" in funil.legenda
    assert "2026-09-29" in funil.legenda
