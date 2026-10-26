"""Teste ponta a ponta (E2E) do Mackenzie sem Barreiras, inteiramente por HTTP.

Roda contra uma pilha ISOLADA subida por `scripts/ponta-a-ponta.sh`
(`COMPOSE_PROJECT_NAME=msb-e2e`), nunca contra a pilha principal. Os alertas
criados aqui são `origem="real"` (o mesmo caminho de `POST /alertas` de um
voluntário de verdade — a API sempre grava `real` por HTTP, D2), mas a pilha
inteira é derrubada com `down -v` ao final pelo script chamador: nada disso
fica gravado além da duração do teste, então não há conflito com a regra de
honestidade acadêmica (CLAUDE.md §9, G10), que é sobre dado SINTÉTICO
apresentado como coleta real — aqui não há coleta nem apresentação, só teste
de integração.

Uso (a partir de `backend/`):

    uv run python -m scripts.ponta_a_ponta http://localhost:58000 http://localhost:58080

Cada verificação é impressa em português com o prefixo `[OK]` ou `[FALHA]`; o
processo sai com código 1 se alguma falhar (0 se todas passarem).

Variável de depuração: `ESPERADO_BARREIRAS_CONFIRMADAS` força o número
esperado de barreiras confirmadas (padrão 1) — existe só para provar, sem
editar código, que uma falha deliberada faz o script sair com código != 0 e
mesmo assim `scripts/ponta-a-ponta.sh` derruba a pilha isolada.

Medição de GPS (`POST /api/medicoes`, `GET /api/medicoes/resumo` e `/analise`): pelo proxy do
frontend. Desligada por padrão (503); com `MEDICAO_CODIGO_EQUIPE` definido confere
o contrato inteiro (`_verificar_medicoes`).

R19: além de bater direto na API, o teste também passa PELO FRONTEND
(`GET {url_frontend}/api/saude` e um `POST {url_frontend}/api/alertas`), a
mesma origem que `frontend/nginx.conf` encaminha para o serviço `api` — se o
proxy quebrar (por exemplo, uma mudança que troque o nome do serviço `api`
no compose), esses dois passos falham mesmo que a API direta esteja saudável.
"""

import argparse
import base64
import json
import math
import os
import sys
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

# Mesmo centroide usado pelo seed da área de estudo
# (db/seeds/002_area_estudo.sql: círculo de 500 m) e pelo gerador de dados
# sintéticos (backend/scripts/gerar_dados_sinteticos.py).
CENTRO_LATITUDE = -23.5471938
CENTRO_LONGITUDE = -46.6524631

# Raio médio da Terra (WGS84), para converter metros em graus por uma
# aproximação equirretangular — suficiente para os deslocamentos deste script
# (poucos metros a ~1 km). Não precisa do rigor de
# `gerar_dados_sinteticos.py::deslocar_ponto` (raios de curvatura + teste de
# erro contra `geography`), que existe para SIMULAÇÃO em larga escala.
_RAIO_TERRA_METROS = 6_371_000.0

_CAMINHOS_DOCS = ("/docs", "/redoc", "/openapi.json")

TIPO_DE_TESTE = "degrau"
DESCRICAO_DE_TESTE = "[teste e2e] gerado por scripts/ponta_a_ponta.py — não é coleta real."


def deslocar_metros(
    latitude: float, longitude: float, norte_metros: float, leste_metros: float
) -> tuple[float, float]:
    """Desloca `(latitude, longitude)` por METROS ao norte/leste.

    Unidade explícita no nome dos parâmetros (CLAUDE.md §5): o SRID de
    armazenamento é 4326 (graus), então todo deslocamento em metros precisa
    ser convertido antes de virar um payload de `POST /alertas`.
    """
    nova_latitude = latitude + (norte_metros / _RAIO_TERRA_METROS) * (180 / math.pi)
    raio_paralelo_metros = _RAIO_TERRA_METROS * math.cos(math.radians(latitude))
    nova_longitude = longitude + (leste_metros / raio_paralelo_metros) * (180 / math.pi)
    return nova_latitude, nova_longitude


def montar_payload_alerta(
    *, norte_metros: float, leste_metros: float, severidade: int | None = 2
) -> dict[str, Any]:
    """Corpo de `POST /alertas` (Contrato da API) num ponto a `norte_metros`/
    `leste_metros` do centroide do campus."""
    latitude, longitude = deslocar_metros(
        CENTRO_LATITUDE, CENTRO_LONGITUDE, norte_metros, leste_metros
    )
    return {
        "latitude": latitude,
        "longitude": longitude,
        "tipo": TIPO_DE_TESTE,
        "severidade": severidade,
        "descricao": DESCRICAO_DE_TESTE,
        "sessao_id": str(uuid.uuid4()),
    }


class _RespostaIndisponivel:
    """Substituto de `httpx.Response` quando a requisição nem chega a sair
    (conexão recusada, timeout): permite que o código de verificação leia
    `.status_code`/`.json()` sem precisar de um `try` em cada chamada."""

    status_code: int | None = None

    def __init__(self, detalhe: str) -> None:
        self.text = detalhe

    def json(self) -> dict[str, Any]:
        return {}


def pedir(cliente: httpx.Client, metodo: str, caminho: str, **kwargs: Any) -> Any:
    """`cliente.request`, mas nunca levanta: falha de rede vira uma resposta
    com `status_code=None`, que toda comparação abaixo (`== 200`, `== 201`)
    já trata como reprovada."""
    try:
        return cliente.request(metodo, caminho, **kwargs)
    except httpx.HTTPError as erro:
        return _RespostaIndisponivel(str(erro))


def json_seguro(resposta: Any) -> dict[str, Any]:
    """`.json()` de uma resposta que pode não ser JSON (ex.: erro HTML de proxy)."""
    try:
        dados = resposta.json()
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


class Verificador:
    """Acumula o resultado de cada verificação e imprime cada uma, na hora,
    em português (`[OK]`/`[FALHA]`) — é o que o brief pede para o operador
    acompanhar o teste ponta a ponta em tempo real."""

    def __init__(self) -> None:
        self.falhas: list[str] = []

    def checar(self, descricao: str, ok: bool, detalhe: str = "") -> bool:
        if ok:
            print(f"[OK] {descricao}")
        else:
            self.falhas.append(descricao)
            sufixo = f": {detalhe}" if detalhe else ""
            print(f"[FALHA] {descricao}{sufixo}")
        return ok

    @property
    def passou(self) -> bool:
        return not self.falhas


def rodar_verificacoes(v: Verificador, url_api: str, url_frontend: str) -> None:
    token_admin = os.environ.get("TOKEN_ADMIN", "")
    esperado_confirmadas = int(os.environ.get("ESPERADO_BARREIRAS_CONFIRMADAS", "1"))

    with (
        httpx.Client(base_url=url_api, timeout=10.0) as api,
        httpx.Client(base_url=url_frontend, timeout=10.0) as frontend,
    ):
        resposta = pedir(api, "GET", "/saude")
        saude_ok = resposta.status_code == 200 and json_seguro(resposta) == {
            "status": "ok",
            "banco": "ok",
        }
        v.checar(
            "GET /saude responde 200 com o banco ok",
            saude_ok,
            f"HTTP {resposta.status_code}: {resposta.text}",
        )

        # R19: a mesma checagem, mas pela origem do FRONTEND (`/api/saude`) —
        # prova que `frontend/nginx.conf` encaminha para o serviço `api` de
        # verdade, não só que a API responde direto.
        resposta = pedir(frontend, "GET", "/api/saude")
        saude_via_proxy_ok = resposta.status_code == 200 and json_seguro(resposta) == {
            "status": "ok",
            "banco": "ok",
        }
        v.checar(
            "GET /api/saude pelo proxy do frontend responde 200 com o banco ok",
            saude_via_proxy_ok,
            f"HTTP {resposta.status_code}: {resposta.text}",
        )

        resposta = pedir(api, "GET", "/tipos-barreira")
        tipos = resposta.json() if resposta.status_code == 200 else []
        codigos = {tipo["codigo"] for tipo in tipos} if isinstance(tipos, list) else set()
        v.checar(
            f"GET /tipos-barreira devolve a taxonomia com '{TIPO_DE_TESTE}' ativo",
            resposta.status_code == 200 and TIPO_DE_TESTE in codigos,
            f"HTTP {resposta.status_code}: {resposta.text}",
        )

        # 3 alertas reais, de 3 sessões distintas, a ≤ 3 m entre si (diagonal
        # ≈ 2,83 m), direto na API + 1 alerta a mais (mesma vizinhança) PELA
        # ORIGEM DO FRONTEND: os 4 devem virar um único cluster (eps/min_pontos
        # do .env), e o quarto prova que o proxy aceita POST com corpo JSON
        # (R19) — não só GET.
        pontos_do_aglomerado = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)]  # (norte_m, leste_m)
        ponto_via_proxy = (1.0, 1.0)  # ainda a ≤ 3 m dos três acima
        total_aglomerado = len(pontos_do_aglomerado) + 1

        aceitos = 0
        for norte_m, leste_m in pontos_do_aglomerado:
            payload = montar_payload_alerta(norte_metros=norte_m, leste_metros=leste_m)
            resposta = pedir(api, "POST", "/alertas", json=payload)
            if resposta.status_code == 201 and json_seguro(resposta).get("status") == "bruto":
                aceitos += 1
        v.checar(
            f"POST /alertas aceita os {len(pontos_do_aglomerado)} relatos diretos do "
            "aglomerado (sessões distintas, status bruto)",
            aceitos == len(pontos_do_aglomerado),
            f"{aceitos} de {len(pontos_do_aglomerado)} aceitos como bruto",
        )

        payload_via_proxy = montar_payload_alerta(
            norte_metros=ponto_via_proxy[0], leste_metros=ponto_via_proxy[1]
        )
        resposta = pedir(frontend, "POST", "/api/alertas", json=payload_via_proxy)
        v.checar(
            "POST /api/alertas pelo proxy do frontend aceita o relato extra do aglomerado "
            "(status bruto)",
            resposta.status_code == 201 and json_seguro(resposta).get("status") == "bruto",
            f"HTTP {resposta.status_code}: {resposta.text}",
        )

        # 1 alerta válido, porém fora do círculo de 500 m da área de estudo.
        payload_fora = montar_payload_alerta(norte_metros=1000.0, leste_metros=0.0)
        resposta = pedir(api, "POST", "/alertas", json=payload_fora)
        dados = json_seguro(resposta)
        v.checar(
            "POST /alertas descarta um relato fora da área (motivo_descarte=fora_da_area)",
            resposta.status_code == 201
            and dados.get("status") == "descartado"
            and dados.get("motivo_descarte") == "fora_da_area",
            f"HTTP {resposta.status_code}: {resposta.text}",
        )

        # 1 alerta inválido no estágio 1 (schema): latitude fora de [-90, 90].
        payload_invalido = montar_payload_alerta(norte_metros=0.0, leste_metros=0.0)
        payload_invalido["latitude"] = 200.0
        resposta = pedir(api, "POST", "/alertas", json=payload_invalido)
        v.checar(
            "POST /alertas rejeita um payload inválido (422, latitude fora da faixa)",
            resposta.status_code == 422,
            f"HTTP {resposta.status_code}: {resposta.text}",
        )

        # Com TOKEN_ADMIN definido (D7), sem o header a execução é recusada.
        # Prova que o token chegou ao container da API, e não só a este script.
        if token_admin:
            resposta = pedir(api, "POST", "/validacao/executar", params={"origem": "real"})
            v.checar(
                "POST /validacao/executar sem X-Token-Admin é recusado (401, TOKEN_ADMIN definido)",
                resposta.status_code == 401,
                f"HTTP {resposta.status_code}: {resposta.text}",
            )

        # Estágios 3 e 4 em lote.
        cabecalhos = {"X-Token-Admin": token_admin} if token_admin else {}
        resposta = pedir(
            api, "POST", "/validacao/executar", params={"origem": "real"}, headers=cabecalhos
        )
        resumo = json_seguro(resposta)
        v.checar(
            "POST /validacao/executar roda o pipeline sobre origem=real (200)",
            resposta.status_code == 200,
            f"HTTP {resposta.status_code}: {resposta.text}",
        )
        v.checar(
            f"POST /validacao/executar agrupa os {total_aglomerado} relatos do aglomerado "
            "(diretos + via proxy) num único cluster",
            resumo.get("agrupados") == total_aglomerado,
            f"agrupados={resumo.get('agrupados')!r}",
        )
        v.checar(
            f"POST /validacao/executar confirma {esperado_confirmadas} barreira(s)",
            resumo.get("barreiras_confirmadas") == esperado_confirmadas,
            f"barreiras_confirmadas={resumo.get('barreiras_confirmadas')!r}",
        )

        # GET /barreiras no bbox do campus (± 0,02° ≈ 2,2 km, folga generosa
        # sobre o círculo de 500 m e o aglomerado de poucos metros).
        bbox = ",".join(
            str(coordenada)
            for coordenada in (
                CENTRO_LONGITUDE - 0.02,
                CENTRO_LATITUDE - 0.02,
                CENTRO_LONGITUDE + 0.02,
                CENTRO_LATITUDE + 0.02,
            )
        )
        resposta = pedir(api, "GET", "/barreiras", params={"bbox": bbox, "origem": "real"})
        colecao = json_seguro(resposta)
        features = colecao.get("features", []) if isinstance(colecao, dict) else []
        confirmadas = [
            feicao
            for feicao in features
            if feicao.get("properties", {}).get("status") == "confirmada"
        ]
        v.checar(
            f"GET /barreiras no bbox do campus devolve {esperado_confirmadas} barreira(s) "
            "confirmada(s)",
            resposta.status_code == 200 and len(confirmadas) == esperado_confirmadas,
            f"HTTP {resposta.status_code}, {len(features)} feature(s), "
            f"{len(confirmadas)} confirmada(s)",
        )

        # GET /validacao/estatisticas: o funil inteiro, num único snapshot.
        resposta = pedir(api, "GET", "/validacao/estatisticas", params={"origem": "real"})
        stats = json_seguro(resposta)
        alertas_obtidos = stats.get("alertas", {})
        barreiras_obtidas = stats.get("barreiras", {})
        alertas_esperados = {
            "recebidos": total_aglomerado + 2,  # + fora_da_area + inválido
            "rejeitados_schema": 1,
            "descartados": {"fora_da_area": 1},
            "aguardando_pipeline": 0,
            "ruido_isolado": 0,
            "agrupados": total_aglomerado,
        }
        barreiras_esperadas = {"total": 1, "pendentes": 0, "confirmadas": esperado_confirmadas}
        v.checar(
            "GET /validacao/estatisticas bate com o funil esperado (bloco alertas)",
            resposta.status_code == 200 and alertas_obtidos == alertas_esperados,
            f"obtido={alertas_obtidos!r}, esperado={alertas_esperados!r}",
        )
        v.checar(
            "GET /validacao/estatisticas bate com o funil esperado (bloco barreiras)",
            resposta.status_code == 200 and barreiras_obtidas == barreiras_esperadas,
            f"obtido={barreiras_obtidas!r}, esperado={barreiras_esperadas!r}",
        )

        resposta = pedir(frontend, "GET", "/")
        v.checar(
            "GET / do frontend devolve a página inicial do escopo novo (200)",
            resposta.status_code == 200
            and "Navegação Acessível no Campus" in resposta.text
            and "Aviso de segurança" in resposta.text
            and "Relatar barreira" not in resposta.text
            and resposta.headers.get("cache-control") == "no-cache",
            f"HTTP {resposta.status_code}, cache-control={resposta.headers.get('cache-control')!r}",
        )

        resposta = pedir(frontend, "GET", "/medicao.html")
        v.checar(
            "GET /medicao.html devolve a página de medição de GPS (200, sem cache)",
            resposta.status_code == 200
            and "<title>Medição de GPS — Mackenzie</title>" in resposta.text
            and "Registrar agora" in resposta.text
            and "<title>Navegação Acessível no Campus Mackenzie</title>" not in resposta.text
            and resposta.headers.get("cache-control") == "no-cache",
            f"HTTP {resposta.status_code}, cache-control={resposta.headers.get('cache-control')!r}",
        )

        _verificar_rotas(v, frontend)
        _verificar_medicoes(v, frontend, token_admin)
        _verificar_endurecimento(v, api, frontend)


# Recorte amplo em torno do campus (o mesmo que o frontend pede).
_BBOX_CAMPUS = "-46.6622,-23.5575,-46.6422,-23.5375"


def _verificar_rotas(v: Verificador, frontend: httpx.Client) -> None:
    """`GET /api/pontos-interesse` e `POST /api/rotas` pelo proxy do frontend, contra o
    seed REAL do campus (o `migrar` da pilha isolada o aplica). Não fixa ids: acha os
    pontos pelo `nome`."""
    resposta = pedir(frontend, "GET", f"/api/pontos-interesse?bbox={_BBOX_CAMPUS}")
    corpo = json_seguro(resposta)
    pontos = {
        f["properties"]["nome"]: f["properties"]
        for f in corpo.get("features", [])
        if "properties" in f
    }
    entradas = [p for p in pontos.values() if p["tipo"] == "entrada" and p["tem_no"]]
    v.checar(
        "GET /api/pontos-interesse devolve pelo menos 2 entradas ligadas ao mapa, com rótulo",
        resposta.status_code == 200 and len(entradas) >= 2 and bool(corpo.get("rotulo")),
        f"HTTP {resposta.status_code}, entradas com nó: {len(entradas)}",
    )
    resposta = pedir(frontend, "GET", "/api/pontos-interesse")
    v.checar(
        "GET /api/pontos-interesse sem bbox responde 422 (campo bbox)",
        resposta.status_code == 422
        and json_seguro(resposta).get("erros", [{}])[0].get("campo") == "bbox",
        f"HTTP {resposta.status_code}",
    )
    if len(entradas) < 2:
        return

    origem = pontos.get("Entrada do Prédio 31", entradas[0])
    destino = pontos.get("Entrada do Prédio 29", entradas[1])
    resposta = pedir(
        frontend,
        "POST",
        "/api/rotas",
        json={"origem_id": origem["id"], "destino_id": destino["id"]},
    )
    rota = json_seguro(resposta)
    instrucoes = rota.get("instrucoes") or [{}]
    v.checar(
        "POST /api/rotas entre duas entradas devolve LineString, distância, chegada e aviso",
        resposta.status_code == 200
        and rota.get("geometria", {}).get("type") == "LineString"
        and rota.get("distancia_m", 0) > 0
        and str(instrucoes[-1].get("texto", "")).startswith("Você chegou")
        and str(rota.get("aviso_seguranca", "")).startswith("Apoio à orientação")
        and bool(rota.get("rotulo")),
        f"HTTP {resposta.status_code}: {resposta.text[:200]}",
    )
    v.checar(
        "a rota do grafo provisório vem rotulada como provisória, com a atribuição do OSM",
        rota.get("provisorio") is True
        and "não conferidos a pé" in str(rota.get("rotulo"))
        and "OpenStreetMap" in str(rota.get("atribuicao")),
        f"provisorio={rota.get('provisorio')!r}, rotulo={rota.get('rotulo')!r}",
    )
    resposta = pedir(
        frontend,
        "POST",
        "/api/rotas",
        json={"origem_id": origem["id"], "destino_id": destino["id"], "perfil": "cadeirante"},
    )
    cadeirante = json_seguro(resposta)
    v.checar(
        "perfil cadeirante: 200 sem nenhum trecho de escada",
        resposta.status_code == 200
        and all(t.get("tipo") != "escada" for t in cadeirante.get("trechos", [])),
        f"HTTP {resposta.status_code}",
    )

    # Segurança: onde o único caminho tem escada, cadeirante não recebe rota.
    passagem = pontos.get("Passagem entre os Prédios 6 e 24")
    if passagem is not None:
        corpo_escada = {"origem_id": passagem["id"], "destino_id": destino["id"]}
        livre = pedir(frontend, "POST", "/api/rotas", json=corpo_escada)
        com_escada = any(t.get("tipo") == "escada" for t in json_seguro(livre).get("trechos", []))
        v.checar(
            "sem restrição: o único caminho pela escada devolve 200 com aviso de escada",
            livre.status_code == 200
            and com_escada
            and any("escada" in a for a in json_seguro(livre).get("avisos", [])),
            f"HTTP {livre.status_code}",
        )
        cad = pedir(frontend, "POST", "/api/rotas", json={**corpo_escada, "perfil": "cadeirante"})
        v.checar(
            "cadeirante onde só há escada: 404 com codigo sem_rota (nunca rota com escada)",
            cad.status_code == 404
            and json_seguro(cad).get("codigo") == "sem_rota"
            and "trechos" not in json_seguro(cad),
            f"HTTP {cad.status_code}: {cad.text[:200]}",
        )

    resposta = pedir(
        frontend, "POST", "/api/rotas", json={"origem_id": origem["id"], "destino_id": origem["id"]}
    )
    v.checar(
        "POST /api/rotas com origem igual ao destino responde 422",
        resposta.status_code == 422,
        f"HTTP {resposta.status_code}",
    )
    resposta = pedir(
        frontend, "POST", "/api/rotas", json={"origem_id": origem["id"], "destino_id": 999999999}
    )
    v.checar(
        "POST /api/rotas com ponto inexistente responde 404",
        resposta.status_code == 404,
        f"HTTP {resposta.status_code}",
    )
    resposta = pedir(frontend, "POST", "/api/rotas", content=" " * (20 * 1024))
    v.checar(
        "POST /api/rotas com corpo de 20 KiB é recusado (413)",
        resposta.status_code == 413,
        f"HTTP {resposta.status_code}",
    )


def _medicao_de_teste(*, tipo: str = "ponto") -> dict[str, Any]:
    """Uma medição de GPS válida para `POST /medicoes` (celular da equipe, 1 ponto)."""
    return {
        "id_cliente": str(uuid.uuid4()),
        "tipo": tipo,
        "medido_em": "2026-10-14T10:30:00-03:00",
        "aparelho": "Aparelho de teste e2e",
        "ponto": 1,
        "condicao": "ceu_aberto",
        "latitude": CENTRO_LATITUDE,
        "longitude": CENTRO_LONGITUDE,
        "precisao_m": 5.0,
    }


def _verificar_medicoes(v: Verificador, frontend: httpx.Client, token_admin: str) -> None:
    """`POST /api/medicoes` e `GET /api/medicoes/resumo` pelo proxy do frontend.

    Sem `MEDICAO_CODIGO_EQUIPE` no ambiente (padrão do `.env.example`) a medição está
    DESLIGADA: 503. Com a variável definida (`MEDICAO_CODIGO_EQUIPE=x
    ./scripts/ponta-a-ponta.sh`; o docker-compose.yml a repassa à API) confere o
    contrato inteiro: 401, 200, idempotência, 422 e o resumo. Fica antes do
    endurecimento porque este deixa o nginx recusando POST por um tempo.
    """
    codigo = os.environ.get("MEDICAO_CODIGO_EQUIPE", "")
    lote = {"medicoes": [_medicao_de_teste()]}

    if not codigo:
        resposta = pedir(
            frontend, "POST", "/api/medicoes", json=lote, headers={"X-Codigo-Equipe": "x"}
        )
        v.checar(
            "POST /api/medicoes com a medição desligada (sem MEDICAO_CODIGO_EQUIPE) responde 503",
            resposta.status_code == 503
            and json_seguro(resposta).get("detail") == "Medição desligada neste servidor.",
            f"HTTP {resposta.status_code}: {resposta.text}",
        )
        return

    resposta = pedir(frontend, "POST", "/api/medicoes", json=lote)
    v.checar(
        "POST /api/medicoes sem X-Codigo-Equipe é recusado (401)",
        resposta.status_code == 401,
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    resposta = pedir(
        frontend, "POST", "/api/medicoes", json=lote, headers={"X-Codigo-Equipe": "errado"}
    )
    v.checar(
        "POST /api/medicoes com o código errado é recusado (401)",
        resposta.status_code == 401,
        f"HTTP {resposta.status_code}: {resposta.text}",
    )

    cabecalhos = {"X-Codigo-Equipe": codigo}
    trajeto = [_medicao_de_teste(tipo="trajeto") for _ in range(3)]
    for item in trajeto:
        item.pop("ponto")
    lote_completo = {"medicoes": [*lote["medicoes"], *trajeto]}
    resposta = pedir(frontend, "POST", "/api/medicoes", json=lote_completo, headers=cabecalhos)
    v.checar(
        "POST /api/medicoes grava um ponto e 3 pontos de trajeto (200, gravadas=4)",
        resposta.status_code == 200 and json_seguro(resposta) == {"gravadas": 4, "repetidas": 0},
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    resposta = pedir(frontend, "POST", "/api/medicoes", json=lote_completo, headers=cabecalhos)
    v.checar(
        "POST /api/medicoes é idempotente: o mesmo lote de novo dá gravadas=0, repetidas=4",
        resposta.status_code == 200 and json_seguro(resposta) == {"gravadas": 0, "repetidas": 4},
        f"HTTP {resposta.status_code}: {resposta.text}",
    )

    sem_precisao = _medicao_de_teste()
    del sem_precisao["precisao_m"]
    resposta = pedir(
        frontend, "POST", "/api/medicoes", json={"medicoes": [sem_precisao]}, headers=cabecalhos
    )
    campos = [erro.get("campo") for erro in json_seguro(resposta).get("erros", [])]
    v.checar(
        "POST /api/medicoes com posição sem precisao_m é recusado (422, medicoes.0.precisao_m)",
        resposta.status_code == 422 and "medicoes.0.precisao_m" in campos,
        f"HTTP {resposta.status_code}: {resposta.text}",
    )

    cabecalhos_admin = {"X-Token-Admin": token_admin} if token_admin else {}
    resposta = pedir(frontend, "GET", "/api/medicoes/resumo", headers=cabecalhos_admin)
    resumo = json_seguro(resposta)
    v.checar(
        "GET /api/medicoes/resumo conta as 4 medições gravadas (e a repetição não duplicou)",
        resposta.status_code == 200
        and resumo.get("total") == 4
        and [a.get("medicoes") for a in resumo.get("por_aparelho", [])] == [4],
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    resposta = pedir(frontend, "GET", "/api/medicoes/analise", headers=cabecalhos_admin)
    analise = json_seguro(resposta)
    v.checar(
        "GET /api/medicoes/analise responde 200 com aviso, total e as duas listas",
        resposta.status_code == 200
        and isinstance(analise.get("aviso"), str)
        and isinstance(analise.get("total_medicoes_analisadas"), int)
        and isinstance(analise.get("por_ponto_aparelho"), list)
        and isinstance(analise.get("por_condicao"), list),
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    if token_admin:
        resposta = pedir(frontend, "GET", "/api/medicoes/resumo")
        v.checar(
            "GET /api/medicoes/resumo sem X-Token-Admin é recusado (401, TOKEN_ADMIN definido)",
            resposta.status_code == 401,
            f"HTTP {resposta.status_code}: {resposta.text}",
        )
    _verificar_fotos(v, frontend, codigo, cabecalhos_admin)


# JPEG 1x1 válido, sem metadados (sem APP1/Exif).
_JPEG_MINIMO = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////"
    "////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def _verificar_fotos(
    v: Verificador, frontend: httpx.Client, codigo: str, cabecalhos_admin: dict[str, str]
) -> None:
    """`POST /api/medicoes/fotos` (corpo bruto image/jpeg) pelo proxy do frontend: 200,
    idempotência, 401 e o resumo. Só roda com o código da equipe definido, como as
    medições."""
    parametros = {
        "id_cliente": str(uuid.uuid4()),
        "ponto": 1,
        "aparelho": "Aparelho de teste e2e",
        "tirada_em": "2026-10-22T10:30:00-03:00",
        "largura_px": 1,
        "altura_px": 1,
    }
    jpeg = {"Content-Type": "image/jpeg"}
    resposta = pedir(
        frontend,
        "POST",
        "/api/medicoes/fotos",
        params=parametros,
        content=_JPEG_MINIMO,
        headers={**jpeg, "X-Codigo-Equipe": "errado"},
    )
    v.checar(
        "POST /api/medicoes/fotos com o código errado é recusado (401)",
        resposta.status_code == 401,
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    enviar = {
        "params": parametros,
        "content": _JPEG_MINIMO,
        "headers": {**jpeg, "X-Codigo-Equipe": codigo},
    }
    resposta = pedir(frontend, "POST", "/api/medicoes/fotos", **enviar)
    v.checar(
        "POST /api/medicoes/fotos grava um JPEG mínimo sem EXIF (200, gravada=true)",
        resposta.status_code == 200 and json_seguro(resposta) == {"gravada": True},
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    resposta = pedir(frontend, "POST", "/api/medicoes/fotos", **enviar)
    v.checar(
        "POST /api/medicoes/fotos é idempotente: o mesmo id_cliente dá gravada=false",
        resposta.status_code == 200 and json_seguro(resposta) == {"gravada": False},
        f"HTTP {resposta.status_code}: {resposta.text}",
    )
    resposta = pedir(frontend, "GET", "/api/medicoes/fotos/resumo", headers=cabecalhos_admin)
    itens = resposta.json() if resposta.status_code == 200 else []
    v.checar(
        "GET /api/medicoes/fotos/resumo mostra 1 foto do P01 do aparelho de teste",
        any(i.get("ponto_codigo") == "P01" and i.get("fotos") == 1 for i in itens),
        f"HTTP {resposta.status_code}: {resposta.text}",
    )


def _rejeitados_schema(api: httpx.Client) -> int | None:
    resposta = pedir(api, "GET", "/validacao/estatisticas", params={"origem": "real"})
    valor = json_seguro(resposta).get("alertas", {}).get("rejeitados_schema")
    return valor if isinstance(valor, int) else None


def _verificar_endurecimento(v: Verificador, api: httpx.Client, frontend: httpx.Client) -> None:
    """Task 8: validação estrita, limite de corpo, documentação desligável e limite
    de envios. Fica por ÚLTIMO de propósito: grava rejeitados (mudaria o funil
    conferido acima) e a inundação do limite de envios deixa o nginx recusando
    POST por um tempo."""
    antes = _rejeitados_schema(api)

    payload_booleano = montar_payload_alerta(norte_metros=0.0, leste_metros=0.0)
    payload_booleano["latitude"] = True
    resposta = pedir(api, "POST", "/alertas", json=payload_booleano)
    v.checar(
        "POST /alertas com latitude booleana é reprovado no estágio 1 (422), não vira fora da área",
        resposta.status_code == 422,
        f"HTTP {resposta.status_code}: {resposta.text}",
    )

    corpo_grande = json.dumps({"descricao": "a" * (17 * 1024)})
    resposta_api = pedir(api, "POST", "/alertas", content=corpo_grande)
    v.checar(
        "POST /alertas com corpo de 17 KiB é recusado pela API (413)",
        resposta_api.status_code == 413,
        f"HTTP {resposta_api.status_code}: {resposta_api.text}",
    )
    resposta_proxy = pedir(frontend, "POST", "/api/alertas", content=corpo_grande)
    v.checar(
        "POST /api/alertas com corpo de 17 KiB é recusado pelo nginx (413)",
        resposta_proxy.status_code == 413,
        f"HTTP {resposta_proxy.status_code}",
    )
    depois = _rejeitados_schema(api)
    v.checar(
        "só a latitude booleana entrou em alertas_rejeitados; os 413 não gravaram nada",
        antes is not None and depois == antes + 1,
        f"antes={antes!r}, depois={depois!r}",
    )

    if os.environ.get("EXPOR_DOCS", "true").lower() == "false":
        codigos = {caminho: pedir(api, "GET", caminho).status_code for caminho in _CAMINHOS_DOCS}
        v.checar(
            "com EXPOR_DOCS=false, /docs, /redoc e /openapi.json respondem 404",
            set(codigos.values()) == {404},
            f"{codigos}",
        )

    # Limite de envios (nginx: 30 r/min, burst 20, nodelay): 60 POSTs seguidos
    # passam de qualquer rajada aceita; o corpo `{}` é barato (422 da API).
    codigos_envio = [
        pedir(frontend, "POST", "/api/alertas", content="{}").status_code for _ in range(60)
    ]
    primeiro_429 = codigos_envio.index(429) if 429 in codigos_envio else None
    v.checar(
        "POST /api/alertas em rajada de 60: as primeiras passam e depois vem 429 do nginx",
        primeiro_429 is not None and primeiro_429 >= 20 and codigos_envio[0] == 422,
        f"primeiro 429 na posição {primeiro_429!r}, primeiro código {codigos_envio[0]!r}",
    )
    resposta = pedir(frontend, "GET", "/api/saude")
    v.checar(
        "durante o limite de envios, GET /api/saude continua 200 (só o POST é limitado)",
        resposta.status_code == 200,
        f"HTTP {resposta.status_code}",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.ponta_a_ponta",
        description=(
            "Teste ponta a ponta (E2E) por HTTP: passa pelo contrato inteiro da API "
            "(saúde, taxonomia, entrada de alertas, pipeline em lote, consulta de "
            "barreiras, estatísticas) e confere o frontend, tudo contra uma pilha isolada."
        ),
    )
    parser.add_argument("url_api", help="Base da API (ex.: http://localhost:58000)")
    parser.add_argument("url_frontend", help="Base do frontend (ex.: http://localhost:58080)")
    args = parser.parse_args(argv)

    print(f"== teste ponta a ponta (E2E) contra {args.url_api} / {args.url_frontend} ==\n")
    v = Verificador()
    rodar_verificacoes(v, args.url_api, args.url_frontend)

    print()
    if v.passou:
        print("== todas as verificações passaram ==")
        return 0
    print(f"== {len(v.falhas)} verificação(ões) falharam ==")
    for descricao in v.falhas:
        print(f"  - {descricao}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
