"""Testes HTTP de `POST /medicoes` e `GET /medicoes/resumo` (contrato de 14/10/2026).

A medição de GPS é dado DA EQUIPE (os celulares dela nos pontos de controle). O
envio é em lote, idempotente por `id_cliente`, e protegido pelo header
`X-Codigo-Equipe`. Os testes batem no PostGIS real (G8).
"""

import json
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import obter_configuracoes
from app.main import app
from tests.auxiliares import LATITUDE_CAMPUS, LONGITUDE_CAMPUS

_CODIGO = "codigo-da-equipe-de-teste"
_TOKEN_ADMIN = "token-admin-de-teste"
_CABECALHO = {"X-Codigo-Equipe": _CODIGO}
_MEDIDO_EM = "2026-10-14T10:30:00-03:00"


@pytest.fixture
def configurar() -> Iterator[Callable[..., None]]:
    """Sobrescreve a configuração vista pelas rotas (`Depends(obter_configuracoes)`)."""

    def _configurar(**sobrescritas: object) -> None:
        padrao: dict[str, object] = {"medicao_codigo_equipe": _CODIGO, "token_admin": ""}
        config = obter_configuracoes().model_copy(update={**padrao, **sobrescritas})
        app.dependency_overrides[obter_configuracoes] = lambda: config

    try:
        yield _configurar
    finally:
        app.dependency_overrides.pop(obter_configuracoes, None)


def _ponto(**sobrescritas: Any) -> dict[str, Any]:
    """Uma medição válida de tipo `ponto`; `None` num argumento remove o campo."""
    medicao: dict[str, Any] = {
        "id_cliente": str(uuid4()),
        "tipo": "ponto",
        "medido_em": _MEDIDO_EM,
        "aparelho": "Galaxy A54",
        "ponto": 3,
        "condicao": "ceu_aberto",
        "latitude": LATITUDE_CAMPUS,
        "longitude": LONGITUDE_CAMPUS,
        "precisao_m": 4.5,
    }
    medicao.update(sobrescritas)
    return {chave: valor for chave, valor in medicao.items() if valor is not None}


def _trajeto(**sobrescritas: Any) -> dict[str, Any]:
    medicao: dict[str, Any] = {
        "id_cliente": str(uuid4()),
        "tipo": "trajeto",
        "medido_em": _MEDIDO_EM,
        "aparelho": "Galaxy A54",
        "latitude": LATITUDE_CAMPUS,
        "longitude": LONGITUDE_CAMPUS,
        "precisao_m": 6.0,
        "velocidade_ms": 1.2,
        "rumo_gps_graus": 90.0,
    }
    medicao.update(sobrescritas)
    return {chave: valor for chave, valor in medicao.items() if valor is not None}


def _enviar(
    cliente: TestClient, medicoes: list[dict[str, Any]], cabecalhos: dict[str, str] | None = None
) -> Any:
    return cliente.post(
        "/medicoes",
        json={"medicoes": medicoes},
        headers=_CABECALHO if cabecalhos is None else cabecalhos,
    )


def _contar(conexao: psycopg.Connection) -> int:
    return conexao.execute("SELECT count(*) FROM medicoes_gps").fetchone()[0]


def _campos(resposta: Any) -> dict[str, str]:
    """`{campo: erro}` do 422."""
    return {erro["campo"]: erro["erro"] for erro in resposta.json()["erros"]}


# --- POST /medicoes: sucesso ---


def test_ponto_e_gravado_com_a_geometria_em_4326(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    medicao = _ponto(
        altitude_m=760.5,
        altitude_precisao_m=8.0,
        observacao="  perto do portão  ",
        user_agent="Mozilla/5.0 (teste)",
    )

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 200
    assert resposta.json() == {"gravadas": 1, "repetidas": 0}
    linha = conexao.execute(
        """
        SELECT tipo, ponto, condicao, aparelho, precisao_m, altitude_m, altitude_precisao_m,
               observacao, user_agent, ST_SRID(geom), ST_Y(geom), ST_X(geom),
               medido_em = '2026-10-14T13:30:00Z'::timestamptz, recebido_em IS NOT NULL
        FROM medicoes_gps WHERE id_cliente = %s
        """,
        (medicao["id_cliente"],),
    ).fetchone()
    assert linha == (
        "ponto",
        3,
        "ceu_aberto",
        "Galaxy A54",
        4.5,
        760.5,
        8.0,
        "perto do portão",
        "Mozilla/5.0 (teste)",
        4326,
        pytest.approx(LATITUDE_CAMPUS),
        pytest.approx(LONGITUDE_CAMPUS),
        True,
        True,
    )


def test_trajeto_em_lote_grava_todos_os_pontos(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    lote = [_trajeto(latitude=LATITUDE_CAMPUS + i * 0.00001) for i in range(10)]

    resposta = _enviar(cliente, lote)

    assert resposta.status_code == 200
    assert resposta.json() == {"gravadas": 10, "repetidas": 0}
    assert _contar(conexao) == 10
    velocidade, rumo = conexao.execute(
        "SELECT velocidade_ms, rumo_gps_graus FROM medicoes_gps LIMIT 1"
    ).fetchone()
    assert (velocidade, rumo) == (1.2, 90.0)


def test_bussola_sem_geometria_e_gravada(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    medicao = {
        "id_cliente": str(uuid4()),
        "tipo": "bussola",
        "medido_em": _MEDIDO_EM,
        "aparelho": "iPhone 13",
        "ponto": 7,
        "bussola_graus": 359.5,
        "bussola_fonte": "webkitCompassHeading",
        "bussola_oscilacao_graus": 3.2,
    }

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 200
    assert resposta.json() == {"gravadas": 1, "repetidas": 0}
    linha = conexao.execute(
        "SELECT bussola_graus, bussola_fonte, bussola_oscilacao_graus, geom FROM medicoes_gps"
    ).fetchone()
    assert linha == (359.5, "webkitCompassHeading", 3.2, None)


def test_vibracao_e_gravada(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    medicao = {
        "id_cliente": str(uuid4()),
        "tipo": "vibracao",
        "medido_em": _MEDIDO_EM,
        "aparelho": "iPhone 13",
        "vibracao_suportada": False,
    }

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 200
    assert resposta.json() == {"gravadas": 1, "repetidas": 0}
    assert conexao.execute("SELECT vibracao_suportada FROM medicoes_gps").fetchone() == (False,)


def test_coordenada_inteira_e_aceita(cliente: TestClient, configurar: Callable[..., None]) -> None:
    """Como em `POST /alertas`: `-23` (inteiro JSON) é um número válido."""
    configurar()

    resposta = _enviar(cliente, [_ponto(latitude=-23, longitude=-46)])

    assert resposta.status_code == 200


# --- POST /medicoes: idempotência ---


def test_reenviar_o_mesmo_lote_nao_duplica(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    lote = [_trajeto(latitude=LATITUDE_CAMPUS + i * 0.00001) for i in range(5)]

    primeira = _enviar(cliente, lote)
    segunda = _enviar(cliente, lote)

    assert primeira.json() == {"gravadas": 5, "repetidas": 0}
    assert segunda.status_code == 200
    assert segunda.json() == {"gravadas": 0, "repetidas": 5}
    assert _contar(conexao) == 5


def test_lote_misto_conta_gravadas_e_repetidas(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    velha = _ponto()
    _enviar(cliente, [velha])

    resposta = _enviar(cliente, [velha, _ponto(), _ponto()])

    assert resposta.json() == {"gravadas": 2, "repetidas": 1}
    assert _contar(conexao) == 3


def test_id_cliente_repetido_dentro_do_mesmo_lote_conta_como_repetido(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()
    medicao = _ponto()

    resposta = _enviar(cliente, [medicao, medicao])

    assert resposta.status_code == 200
    assert resposta.json() == {"gravadas": 1, "repetidas": 1}
    assert _contar(conexao) == 1


# --- POST /medicoes: 422 ---


def test_lote_com_um_item_invalido_nao_grava_nenhum(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto(), _ponto(precisao_m=None)])

    assert resposta.status_code == 422
    assert _contar(conexao) == 0


def test_campo_extra_e_recusado(cliente: TestClient, configurar: Callable[..., None]) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto(nome_da_pessoa="Fulano")])

    assert resposta.status_code == 422
    assert resposta.json()["mensagem"] == "Medição inválida."
    assert "Campo desconhecido" in _campos(resposta)["medicoes.0.nome_da_pessoa"]


def test_campo_extra_no_topo_do_corpo_e_recusado(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()

    resposta = cliente.post(
        "/medicoes", json={"medicoes": [_ponto()], "extra": 1}, headers=_CABECALHO
    )

    assert resposta.status_code == 422
    assert "extra" in _campos(resposta)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("precisao_m", "5"),
        ("precisao_m", True),
        ("latitude", "-23.5"),
        ("longitude", True),
        ("ponto", 3.0),
        ("ponto", "3"),
        ("aparelho", 42),
        ("vibracao_suportada", "sim"),
        ("medido_em", 1760448600),
        ("id_cliente", "isto-nao-e-um-uuid"),
    ],
)
def test_tipo_errado_e_recusado_sem_conversao(
    cliente: TestClient, configurar: Callable[..., None], campo: str, valor: object
) -> None:
    configurar()
    medicao = _ponto()
    medicao[campo] = valor
    if campo == "vibracao_suportada":
        medicao["tipo"] = "vibracao"
        medicao.pop("ponto")

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 422, resposta.text
    assert f"medicoes.0.{campo}" in _campos(resposta)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("latitude", 91),
        ("latitude", -90.0001),
        ("longitude", 180.5),
        ("precisao_m", -0.1),
        ("ponto", 0),
        ("ponto", 13),
        ("tipo", "nada"),
        ("condicao", "ceu_fechado"),
        ("bussola_graus", 360),
        ("bussola_graus", -1),
        ("bussola_fonte", "giroscopio"),
        ("bussola_oscilacao_graus", -2),
        ("aparelho", "   "),
        ("aparelho", "a" * 81),
        ("observacao", "a" * 501),
        ("user_agent", "a" * 301),
    ],
)
def test_valor_fora_da_faixa_e_recusado(
    cliente: TestClient, configurar: Callable[..., None], campo: str, valor: object
) -> None:
    configurar()
    medicao = _ponto()
    medicao[campo] = valor

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 422, resposta.text
    assert f"medicoes.0.{campo}" in _campos(resposta)


def test_ponto_sem_numero_de_ponto_e_recusado(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto(ponto=None)])

    assert resposta.status_code == 422
    assert "medicoes.0.ponto" in _campos(resposta)


@pytest.mark.parametrize("tipo", ["ponto", "trajeto"])
@pytest.mark.parametrize("campo", ["latitude", "longitude"])
def test_tipo_com_geometria_sem_coordenada_e_recusado(
    cliente: TestClient, configurar: Callable[..., None], tipo: str, campo: str
) -> None:
    configurar()
    base = _ponto if tipo == "ponto" else _trajeto

    resposta = _enviar(cliente, [base(**{campo: None})])

    assert resposta.status_code == 422
    assert f"medicoes.0.{campo}" in _campos(resposta)


@pytest.mark.parametrize("tipo", ["ponto", "trajeto"])
def test_geometria_sem_precisao_e_recusada(
    cliente: TestClient, configurar: Callable[..., None], tipo: str
) -> None:
    configurar()
    medicao = _ponto(precisao_m=None) if tipo == "ponto" else _trajeto(precisao_m=None)

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 422
    assert "medicoes.0.precisao_m" in _campos(resposta)


@pytest.mark.parametrize("tipo", ["bussola", "vibracao"])
def test_geometria_sem_precisao_e_recusada_em_qualquer_tipo(
    cliente: TestClient, configurar: Callable[..., None], tipo: str
) -> None:
    """O banco exige `precisao_m` sempre que há `geom`, mesmo fora de ponto/trajeto:
    422 aqui, nunca 500 do CHECK."""
    configurar()
    medicao = {
        "id_cliente": str(uuid4()),
        "tipo": tipo,
        "medido_em": _MEDIDO_EM,
        "aparelho": "Galaxy A54",
        "latitude": LATITUDE_CAMPUS,
        "longitude": LONGITUDE_CAMPUS,
    }

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 422
    assert "medicoes.0.precisao_m" in _campos(resposta)


@pytest.mark.parametrize(
    ("presente", "mensagem"),
    [
        ("latitude", "Informe a longitude junto com a latitude."),
        ("longitude", "Informe a latitude junto com a longitude."),
    ],
)
def test_so_uma_das_coordenadas_e_recusada(
    cliente: TestClient, configurar: Callable[..., None], presente: str, mensagem: str
) -> None:
    """O erro sai sempre no campo `longitude` (os validadores só enxergam os campos
    anteriores); a mensagem diz qual das duas falta."""
    configurar()
    medicao = {
        "id_cliente": str(uuid4()),
        "tipo": "bussola",
        "medido_em": _MEDIDO_EM,
        "aparelho": "Galaxy A54",
        presente: -23.5,
        "precisao_m": 5.0,
    }

    resposta = _enviar(cliente, [medicao])

    assert resposta.status_code == 422
    assert _campos(resposta)["medicoes.0.longitude"] == mensagem


def test_lote_vazio_e_recusado(cliente: TestClient, configurar: Callable[..., None]) -> None:
    configurar()

    resposta = _enviar(cliente, [])

    assert resposta.status_code == 422
    assert "medicoes" in _campos(resposta)


def test_lote_de_50_e_aceito_e_de_51_e_recusado(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar(limite_corpo_bytes=1_000_000)

    com_51 = _enviar(cliente, [_trajeto() for _ in range(51)])
    assert com_51.status_code == 422
    assert "medicoes" in _campos(com_51)
    assert _contar(conexao) == 0

    com_50 = _enviar(cliente, [_trajeto() for _ in range(50)])
    assert com_50.status_code == 200
    assert com_50.json() == {"gravadas": 50, "repetidas": 0}


@pytest.mark.parametrize(
    "medido_em", ["2026-10-14T10:30:00", "2026-10-14", "ontem", "2026-13-45T10:30:00Z"]
)
def test_data_sem_fuso_ou_invalida_e_recusada(
    cliente: TestClient, configurar: Callable[..., None], medido_em: str
) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto(medido_em=medido_em)])

    assert resposta.status_code == 422
    assert "medicoes.0.medido_em" in _campos(resposta)


def test_data_com_z_e_aceita(cliente: TestClient, configurar: Callable[..., None]) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto(medido_em="2026-10-14T13:30:00.123Z")])

    assert resposta.status_code == 200


@pytest.mark.parametrize(
    "corpo",
    [
        b"",
        b"{nao e json",
        b"[]",
        b"null",
        b"42",
        b'{"medicoes": "x"}',
        b'{"medicoes": [1]}',
        b'{"medicoes": [{"precisao_m": NaN}]}',
        b"\xff\xfe\xfd",
        b'{"medicoes": ' + b"[" * 5000 + b"]" * 5000 + b"}",
    ],
)
def test_corpo_que_nao_e_um_lote_vira_422_nunca_500(
    cliente: TestClient, configurar: Callable[..., None], corpo: bytes
) -> None:
    configurar()

    resposta = cliente.post(
        "/medicoes", content=corpo, headers={**_CABECALHO, "Content-Type": "application/json"}
    )

    assert resposta.status_code == 422
    assert resposta.json()["mensagem"] == "Medição inválida."
    assert resposta.json()["erros"]


def test_caractere_nulo_que_o_banco_nao_grava_vira_422_nunca_500(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()
    corpo = json.dumps({"medicoes": [_ponto(observacao="a\u0000b")]})  # vai como \u0000

    resposta = cliente.post(
        "/medicoes", content=corpo, headers={**_CABECALHO, "Content-Type": "application/json"}
    )

    assert resposta.status_code == 422
    assert "medicoes.0.observacao" in _campos(resposta)


def test_substituto_utf16_isolado_vira_422_nunca_500(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()
    corpo = json.dumps({"medicoes": [_ponto(observacao="\ud800")]})  # vai como \ud800

    resposta = cliente.post(
        "/medicoes", content=corpo, headers={**_CABECALHO, "Content-Type": "application/json"}
    )

    assert resposta.status_code == 422


def test_numero_nao_finito_e_recusado(cliente: TestClient, configurar: Callable[..., None]) -> None:
    configurar()
    corpo = json.dumps({"medicoes": [_ponto(precisao_m=1e999)]})

    resposta = cliente.post(
        "/medicoes", content=corpo, headers={**_CABECALHO, "Content-Type": "application/json"}
    )

    assert resposta.status_code == 422


# --- POST /medicoes: autenticação ---


def test_sem_o_header_do_codigo_devolve_401(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto()], cabecalhos={})

    assert resposta.status_code == 401
    assert _contar(conexao) == 0


@pytest.mark.parametrize("codigo", ["errado", _CODIGO + "x", _CODIGO[:-1], ""])
def test_codigo_errado_devolve_401(
    cliente: TestClient,
    conexao: psycopg.Connection,
    configurar: Callable[..., None],
    codigo: str,
) -> None:
    configurar()

    resposta = _enviar(cliente, [_ponto()], cabecalhos={"X-Codigo-Equipe": codigo})

    assert resposta.status_code == 401
    assert _contar(conexao) == 0


def test_codigo_com_bytes_fora_do_ascii_devolve_401_nunca_500(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()
    corpo = json.dumps({"medicoes": [_ponto()]})

    resposta = cliente.post(
        "/medicoes",
        content=corpo,
        headers=[("x-codigo-equipe", "código-é".encode()), ("content-type", "application/json")],
    )

    assert resposta.status_code == 401


def test_401_vem_antes_da_validacao_do_corpo(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar()

    resposta = cliente.post("/medicoes", content=b"{lixo", headers={"X-Codigo-Equipe": "errado"})

    assert resposta.status_code == 401


# --- POST /medicoes: 503 (medição desligada) ---


@pytest.mark.parametrize("cabecalhos", [{}, {"X-Codigo-Equipe": ""}, _CABECALHO])
def test_sem_codigo_configurado_a_medicao_esta_desligada_503(
    cliente: TestClient,
    conexao: psycopg.Connection,
    configurar: Callable[..., None],
    cabecalhos: dict[str, str],
) -> None:
    configurar(medicao_codigo_equipe="")

    resposta = _enviar(cliente, [_ponto()], cabecalhos=cabecalhos)

    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "Medição desligada neste servidor."}
    assert _contar(conexao) == 0


def test_codigo_configurado_so_com_espacos_tambem_e_medicao_desligada(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(medicao_codigo_equipe="   ")

    resposta = _enviar(cliente, [_ponto()], cabecalhos={"X-Codigo-Equipe": "   "})

    assert resposta.status_code == 503


# --- POST /medicoes: 413 ---


def test_corpo_acima_do_limite_devolve_413_sem_gravar(
    cliente: TestClient, conexao: psycopg.Connection, configurar: Callable[..., None]
) -> None:
    configurar()  # limite_corpo_bytes padrão: 16 KiB
    corpo = json.dumps({"medicoes": [_ponto(observacao="a" * 17 * 1024)]})

    resposta = cliente.post("/medicoes", content=corpo, headers=_CABECALHO)

    assert resposta.status_code == 413
    assert resposta.json() == {"mensagem": "Corpo grande demais: o limite é 16 KiB."}
    assert _contar(conexao) == 0


def test_corpo_no_limite_e_aceito_e_um_byte_acima_e_recusado(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    corpo = json.dumps({"medicoes": [_ponto()]}).encode()
    configurar(limite_corpo_bytes=len(corpo))
    cabecalhos = {**_CABECALHO, "Content-Type": "application/json"}

    no_limite = cliente.post("/medicoes", content=corpo, headers=cabecalhos)
    um_acima = cliente.post("/medicoes", content=corpo + b" ", headers=cabecalhos)

    assert no_limite.status_code == 200
    assert um_acima.status_code == 413


def test_corpo_em_pedacos_sem_content_length_tambem_e_cortado(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(limite_corpo_bytes=1024)

    def pedacos() -> Iterator[bytes]:
        for _ in range(10):
            yield b" " * 512

    resposta = cliente.post("/medicoes", content=pedacos(), headers=_CABECALHO)

    assert resposta.status_code == 413


# --- GET /medicoes/resumo ---


def _gravar(cliente: TestClient, medicoes: list[dict[str, Any]]) -> None:
    assert _enviar(cliente, medicoes).status_code == 200


def test_resumo_sem_token_configurado_e_aberto_e_vazio_sem_dados(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin="")

    resposta = cliente.get("/medicoes/resumo")

    assert resposta.status_code == 200
    assert resposta.json() == {"total": 0, "por_aparelho": [], "por_ponto": []}


def test_resumo_com_token_configurado_sem_header_devolve_401(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN_ADMIN)

    sem_header = cliente.get("/medicoes/resumo")
    errado = cliente.get("/medicoes/resumo", headers={"X-Token-Admin": "errado"})

    assert sem_header.status_code == 401
    assert errado.status_code == 401


def test_resumo_nao_aceita_o_codigo_da_equipe_no_lugar_do_token_admin(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN_ADMIN)

    resposta = cliente.get("/medicoes/resumo", headers=_CABECALHO)

    assert resposta.status_code == 401


def test_resumo_agrupa_por_aparelho_e_por_ponto(
    cliente: TestClient, configurar: Callable[..., None]
) -> None:
    configurar(token_admin=_TOKEN_ADMIN)
    _gravar(
        cliente,
        [
            # Galaxy: ponto 1 (3, 5, 7: mediana 5, p90 6,6) e ponto 2 (10).
            _ponto(aparelho="Galaxy A54", ponto=1, precisao_m=3.0),
            _ponto(aparelho="Galaxy A54", ponto=1, precisao_m=5.0),
            _ponto(aparelho="Galaxy A54", ponto=1, precisao_m=7.0),
            _ponto(aparelho="Galaxy A54", ponto=2, precisao_m=10.0),
            # iPhone: ponto 1 (20) e uma bússola no ponto 3, sem precisão.
            _ponto(aparelho="iPhone 13", ponto=1, precisao_m=20.0),
            {
                "id_cliente": str(uuid4()),
                "tipo": "bussola",
                "medido_em": _MEDIDO_EM,
                "aparelho": "iPhone 13",
                "ponto": 3,
                "bussola_graus": 10.0,
                "bussola_fonte": "alpha_absoluto",
            },
            # Trajeto: sem ponto, entra no total e na precisão do aparelho.
            _trajeto(aparelho="iPhone 13", precisao_m=30.0),
        ],
    )

    resposta = cliente.get("/medicoes/resumo", headers={"X-Token-Admin": _TOKEN_ADMIN})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 7
    assert corpo["por_aparelho"] == [
        {"aparelho": "Galaxy A54", "pontos": 2, "medicoes": 4, "precisao_mediana_m": 6.0},
        {"aparelho": "iPhone 13", "pontos": 2, "medicoes": 3, "precisao_mediana_m": 25.0},
    ]
    assert corpo["por_ponto"] == [
        {"ponto": 1, "medicoes": 4, "precisao_mediana_m": 6.0, "precisao_p90_m": 16.1},
        {"ponto": 2, "medicoes": 1, "precisao_mediana_m": 10.0, "precisao_p90_m": 10.0},
        {"ponto": 3, "medicoes": 1, "precisao_mediana_m": None, "precisao_p90_m": None},
    ]
