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

R19: além de bater direto na API, o teste também passa PELO FRONTEND
(`GET {url_frontend}/api/saude` e um `POST {url_frontend}/api/alertas`), a
mesma origem que `frontend/nginx.conf` encaminha para o serviço `api` — se o
proxy quebrar (por exemplo, uma mudança que troque o nome do serviço `api`
no compose), esses dois passos falham mesmo que a API direta esteja saudável.
"""

import argparse
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
            "GET / do frontend devolve o index.html (200)",
            resposta.status_code == 200 and "Mackenzie sem Barreiras" in resposta.text,
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
