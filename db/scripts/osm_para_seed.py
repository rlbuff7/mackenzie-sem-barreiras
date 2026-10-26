#!/usr/bin/env python3
"""Gera o seed PROVISÓRIO do grafo do campus a partir do OpenStreetMap.

Uso (precisa de internet; o CI e a AWS NÃO rodam isto, só aplicam o seed gerado):

    python3 db/scripts/osm_para_seed.py > db/seeds/004_campus_osm.sql
    python3 db/scripts/osm_para_seed.py --json cache.json   # sem rede, a partir de um download salvo
    python3 db/scripts/osm_para_seed.py --salvar-json cache.json > db/seeds/004_campus_osm.sql

Ferramenta de DESENVOLVIMENTO: existe até o mapeamento do Maurício (M2) chegar.
Dados © contribuidores do OpenStreetMap, licença ODbL (https://www.openstreetmap.org/copyright).

O que faz:
  1. baixa da Overpass API os caminhos de pedestre (highway = footway, path,
     pedestrian, steps, service, living_street) e as entradas (entrance = *) dentro do
     retângulo do campus; por padrão ficam de fora as calçadas de rua e as faixas de
     travessia (footway = sidewalk / crossing), porque o recorte é só o interior do campus;
  2. corta os caminhos no retângulo, cria nós nas interseções e nos extremos e uma aresta
     por trecho entre nós (curvas ficam como vértices da linha);
  3. fica só com a maior componente conexa (grafo desconexo não serve para rota);
  4. liga os pontos de interesse ao nó mais próximo (até DISTANCIA_MAXIMA_LIGACAO_M);
  5. escreve o SQL do seed: apaga e reinsere o grafo do campus com ids fixos (idempotente).

O comprimento NÃO é calculado aqui: o próprio seed o calcula no banco, em SRID 31983.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date

URL_OVERPASS = "https://overpass-api.de/api/interpreter"
URL_OVERPASS_ESPELHO = "https://overpass.kumi.systems/api/interpreter"
# A Overpass recusa (HTTP 406) pedidos sem User-Agent identificável.
USER_AGENT = "msb-tcc-mackenzie/1.0 (TCC Mackenzie sem Barreiras; script de desenvolvimento)"

# Retângulo do recorte (sul, oeste, norte, leste), em graus. Cobre os pontos de controle
# P01..P10 de docs/medicao-gps.md com folga e fica dentro da área_estudo provisória
# (círculo de 500 m em torno de -23.5471938, -46.6524631; seed 002).
RECORTE = (-23.5483, -46.6535, -23.5456, -46.6510)

TIPOS_DE_VIA = ("footway", "path", "pedestrian", "steps", "service", "living_street")
# Calçadas de rua e travessias: infraestrutura da rua, fora do interior do campus.
SUBTIPOS_FORA = ("sidewalk", "crossing")

DISTANCIA_MAXIMA_LIGACAO_M = 40.0  # ponto de interesse -> nó mais próximo
DISTANCIA_MAXIMA_PREDIO_M = 30.0   # prédio -> caminho, para gerar "entrada aproximada"
MIN_ARESTAS_GRAFO = 15  # abaixo disso o grafo é pequeno demais: cair no plano B2

MAPEADO_POR = "OpenStreetMap (contribuidores)"
FONTE_VERIFICACAO = "provisorio"

# Pontos de controle da equipe (docs/medicao-gps.md, coordenadas estimadas por satélite).
# (código, nome, tipo, latitude, longitude, descrição para a voz)
PONTOS_DE_CONTROLE = (
    ("P03", "Passagem entre os Prédios 6 e 24", "portao", -23.546915816255126, -46.65172517217903,
     "Passagem entre os Prédios 6 e 24, no alto do escadão perto do Starbucks."),
    ("P04", "Entrada do Prédio 29", "entrada", -23.54757664389376, -46.6516827262256,
     "Entrada principal do Prédio 29, em frente ao Prédio 31."),
    ("P05", "Entrada do Prédio 31", "entrada", -23.54744263607399, -46.65146814951144,
     "Entrada principal do Prédio 31, em frente ao MackGraphe."),
    ("P06", "Entrada do Auditório da Escola Americana", "entrada", -23.547747707942488,
     -46.652778943818376, "Entrada do Auditório da Escola Americana, perto da entrada da rua Piauí."),
    ("P02", "Entrada da Biblioteca Central", "entrada", -23.546013383953508, -46.65202165910552,
     "Área aberta junto à Biblioteca Central (Prédio 2), perto do Bosque das Fadas."),
)

# Nomes dados por nós às escadas do OSM (que vêm sem nome), pelo id do caminho no OSM.
NOMES_DE_ESCADA = {
    269125427: ("Escadão perto do Starbucks",
                "Escada com corrimão entre os Prédios 6 e 24, de concreto."),
}

# O OSM no entorno tem muitos edifícios residenciais; só viram ponto "predio" os que o nome
# mostra serem do campus (heurística de desenvolvimento).
PADRAO_PREDIO_DO_CAMPUS = re.compile(r"pr[eé]dio|escola|audit[oó]rio|mackenzie|biblioteca|ccbs", re.I)


# ---------------------------------------------------------------------------
# Geometria simples (aproximação plana, suficiente para distâncias de dezenas de metros)
# ---------------------------------------------------------------------------

def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em metros entre dois pontos (equiretangular; ok para <1 km)."""
    lat_media = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(lat_media) * 6371008.8
    dy = math.radians(lat2 - lat1) * 6371008.8
    return math.hypot(dx, dy)


def dentro_do_recorte(lat: float, lon: float, recorte=RECORTE) -> bool:
    sul, oeste, norte, leste = recorte
    return sul <= lat <= norte and oeste <= lon <= leste


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def montar_consulta(recorte=RECORTE) -> str:
    bbox = ",".join(str(v) for v in recorte)
    vias = "|".join(TIPOS_DE_VIA)
    return (
        "[out:json][timeout:60];\n(\n"
        f'  way["highway"~"^({vias})$"]({bbox});\n'
        f'  node["entrance"]({bbox});\n'
        f'  way["building"]["name"]({bbox});\n'
        ");\nout body geom;\n"
    )


def baixar(recorte=RECORTE, urls=(URL_OVERPASS, URL_OVERPASS_ESPELHO), tentativas: int = 3) -> dict:
    """Baixa da Overpass; tenta de novo (e no espelho) porque ela devolve 502/504 com frequência."""
    corpo = urllib.parse.urlencode({"data": montar_consulta(recorte)}).encode()
    ultimo_erro = None
    for tentativa in range(tentativas):
        for url in urls:
            pedido = urllib.request.Request(url, data=corpo, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(pedido, timeout=90) as resposta:  # noqa: S310
                    return json.load(resposta)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
                ultimo_erro = erro
                print(f"aviso: {url} falhou ({erro})", file=sys.stderr)
        time.sleep(5 * (tentativa + 1))
    raise SystemExit(f"erro: não consegui baixar da Overpass API ({ultimo_erro}). "
                     "Use --json com um download salvo ou caia no plano B2 do plano E6.")


# ---------------------------------------------------------------------------
# Grafo
# ---------------------------------------------------------------------------

@dataclass
class Via:
    osm_id: int
    tags: dict
    pontos: list  # [(osm_node_id, lat, lon), ...] já cortado no recorte


@dataclass
class Grafo:
    nos: dict = field(default_factory=dict)       # id_sequencial -> (lat, lon)
    arestas: list = field(default_factory=list)   # dicts
    pontos: list = field(default_factory=list)    # dicts
    avisos: list = field(default_factory=list)
    descartadas: int = 0  # arestas fora da maior componente


def classificar(tags: dict) -> tuple[str, bool | None]:
    """Devolve (tipo da aresta, acessivel_cadeirante). None = não verificado."""
    cadeira = {"yes": True, "designated": True, "no": False}.get(tags.get("wheelchair"))
    if tags.get("highway") == "steps":
        return "escada", False
    if tags.get("footway") == "crossing":
        return "travessia", cadeira
    if tags.get("ramp") == "yes" or tags.get("incline") not in (None, "0", "0%"):
        return "rampa", cadeira
    return "calcada", cadeira


def vias_do_json(dados: dict, recorte=RECORTE, com_calcadas_de_rua: bool = False) -> list[Via]:
    """Vias de pedestre, cortadas no recorte (cada trecho contínuo dentro vira uma Via)."""
    vias: list[Via] = []
    for e in dados.get("elements", []):
        tags = e.get("tags", {})
        if e.get("type") != "way" or tags.get("highway") not in TIPOS_DE_VIA:
            continue
        if not com_calcadas_de_rua and tags.get("footway") in SUBTIPOS_FORA:
            continue
        if tags.get("access") in ("private", "no") and tags.get("foot") not in ("yes", "designated"):
            continue
        pontos = [(n, g["lat"], g["lon"]) for n, g in zip(e["nodes"], e["geometry"])]
        trecho: list = []
        trechos = []
        for p in pontos:
            if dentro_do_recorte(p[1], p[2], recorte):
                trecho.append(p)
            else:
                if len(trecho) >= 2:
                    trechos.append(trecho)
                trecho = []
        if len(trecho) >= 2:
            trechos.append(trecho)
        vias.extend(Via(e["id"], tags, t) for t in trechos)
    return vias


def construir_grafo(dados: dict, recorte=RECORTE, com_calcadas_de_rua: bool = False,
                    pontos_extra_para_ligar: list | None = None) -> Grafo:
    """Monta nós e arestas. `pontos_extra_para_ligar`: lista de (lat, lon) que precisam
    ficar sobre um nó (para ligar pontos de interesse); o vértice mais próximo vira nó."""
    vias = vias_do_json(dados, recorte, com_calcadas_de_rua)
    coord: dict[int, tuple[float, float]] = {}
    uso: defaultdict[int, int] = defaultdict(int)
    for v in vias:
        for i, (n, lat, lon) in enumerate(v.pontos):
            coord[n] = (lat, lon)
            # extremos e vértices repetidos contam como "ponta" (+2 para extremos)
            uso[n] += 2 if i in (0, len(v.pontos) - 1) else 1

    nos_osm = {n for n, u in uso.items() if u >= 2}  # interseção (em 2+ vias) ou extremo
    forcados: set[int] = set()
    for lat, lon in pontos_extra_para_ligar or []:
        if coord:
            melhor = min(coord, key=lambda n: distancia_m(lat, lon, *coord[n]))
            forcados.add(melhor)
    nos_osm |= forcados

    arestas_brutas = []
    for v in vias:
        inicio = 0
        for i in range(1, len(v.pontos)):
            if v.pontos[i][0] in nos_osm:
                seg = v.pontos[inicio:i + 1]
                if seg[0][0] != seg[-1][0] and len(seg) >= 2:
                    arestas_brutas.append((v, seg))
                inicio = i

    # Maior componente conexa (mão única não existe aqui: tudo mão dupla).
    vizinhos: defaultdict[int, set[int]] = defaultdict(set)
    for _, seg in arestas_brutas:
        a, b = seg[0][0], seg[-1][0]
        vizinhos[a].add(b)
        vizinhos[b].add(a)
    visto: set[int] = set()
    componentes = []
    for n in sorted(vizinhos):
        if n in visto:
            continue
        comp, fila = {n}, deque([n])
        visto.add(n)
        while fila:
            for m in vizinhos[fila.popleft()]:
                if m not in visto:
                    visto.add(m)
                    comp.add(m)
                    fila.append(m)
        componentes.append(comp)
    grafo = Grafo()
    if not componentes:
        return grafo
    maior = max(componentes, key=lambda c: (len(c), -min(c)))
    # Aresta duplicada (mesmo par de nós e mesma geometria) é descartada; paralelas
    # distintas ficam.
    usadas = set()
    id_no: dict[int, int] = {}
    for n in sorted(maior):
        id_no[n] = len(id_no) + 1
        grafo.nos[id_no[n]] = coord[n]
    for v, seg in sorted(arestas_brutas, key=lambda x: (x[0].osm_id, x[1][0][0], x[1][-1][0])):
        a, b = seg[0][0], seg[-1][0]
        if a not in maior:
            grafo.descartadas += 1
            continue
        chave = (a, b, tuple((p[1], p[2]) for p in seg))
        if chave in usadas:
            continue
        usadas.add(chave)
        tipo, cadeira = classificar(v.tags)
        grafo.arestas.append({
            "id": len(grafo.arestas) + 1, "osm_id": v.osm_id,
            "origem": id_no[a], "destino": id_no[b], "tipo": tipo, "acessivel_cadeirante": cadeira,
            "linha": [(p[2], p[1]) for p in seg],  # (lon, lat)
        })
    grafo.componentes_descartados = len(componentes) - 1  # type: ignore[attr-defined]
    return grafo


def no_mais_proximo(grafo: Grafo, lat: float, lon: float) -> tuple[int, float]:
    n = min(grafo.nos, key=lambda i: distancia_m(lat, lon, *grafo.nos[i]))
    return n, distancia_m(lat, lon, *grafo.nos[n])


def _ponto_medio(linha) -> tuple[float, float]:
    """(lat, lon) do meio da linha em vértices (aproximação, só para posicionar um rótulo)."""
    m = len(linha)
    if m % 2:
        lon, lat = linha[m // 2]
    else:
        lon = (linha[m // 2 - 1][0] + linha[m // 2][0]) / 2
        lat = (linha[m // 2 - 1][1] + linha[m // 2][1]) / 2
    return lat, lon


def centroide_de_predio(e: dict) -> tuple[float, float]:
    g = e["geometry"]
    return sum(p["lat"] for p in g) / len(g), sum(p["lon"] for p in g) / len(g)


def adicionar_pontos(grafo: Grafo, dados: dict, recorte=RECORTE) -> None:
    """Pontos de interesse e a ligação de cada um ao nó mais próximo.

    Cada ponto guarda `no` (id do nó) ou None. Só ficam com nó os que estão a até
    DISTANCIA_MAXIMA_LIGACAO_M do grafo.
    """
    nos_com_entrada: set[int] = set()

    def ligar(nome, tipo, lat, lon, descricao, acessivel=None):
        no, dist = no_mais_proximo(grafo, lat, lon)
        ligado = dist <= DISTANCIA_MAXIMA_LIGACAO_M
        if ligado and tipo in ("entrada", "portao"):
            if no in nos_com_entrada:  # um nó atende a um ponto só (nos.ponto_interesse_id)
                grafo.avisos.append(f"ponto '{nome}' cairia no nó {no}, já usado: ficou SEM nó")
                ligado = False
            else:
                nos_com_entrada.add(no)
        if not ligado and tipo in ("entrada", "escada", "portao"):
            grafo.avisos.append(f"ponto '{nome}' a {dist:.0f} m do grafo: ficou SEM nó")
        grafo.pontos.append({
            "id": len(grafo.pontos) + 1, "nome": nome, "tipo": tipo, "lat": lat, "lon": lon,
            "descricao": descricao, "acessivel": acessivel,
            "no": no if ligado else None, "distancia_ao_no_m": dist,
        })

    # Escadas do grafo (toda aresta escada precisa de um ponto escada perto).
    vistas = set()
    for a in grafo.arestas:
        if a["tipo"] != "escada" or a["osm_id"] in vistas:
            continue
        vistas.add(a["osm_id"])
        nome, desc = NOMES_DE_ESCADA.get(a["osm_id"], ("Escada do campus", "Escada com degraus."))
        lat, lon = _ponto_medio(a["linha"])
        ligar(nome, "escada", lat, lon, desc, acessivel=False)

    for _cod, nome, tipo, lat, lon, desc in PONTOS_DE_CONTROLE:
        ligar(nome, tipo, lat, lon, desc)

    # Entradas mapeadas no OSM dentro do recorte.
    for e in dados.get("elements", []):
        tags = e.get("tags", {})
        if e.get("type") == "node" and "entrance" in tags and tags.get("name") and \
                dentro_do_recorte(e["lat"], e["lon"], recorte):
            # Entrada sem nome no OSM não diz de quem é (pode ser de prédio vizinho): fica de fora.
            ligar(tags["name"], "entrada", e["lat"], e["lon"], "Entrada mapeada no OpenStreetMap.",
                  {"yes": True, "no": False}.get(tags.get("wheelchair")))

    # Prédios com nome no OSM dentro do recorte: ponto "predio" (sem nó, só referência).
    for e in dados.get("elements", []):
        tags = e.get("tags", {})
        if e.get("type") == "way" and "building" in tags and "geometry" in e \
                and PADRAO_PREDIO_DO_CAMPUS.search(tags.get("name", "")):
            lat, lon = centroide_de_predio(e)
            if dentro_do_recorte(lat, lon, recorte):
                ligar(tags["name"], "predio", lat, lon,
                      "Prédio mapeado no OpenStreetMap (sem entrada marcada).")
    # Prédio em si nunca é destino. Se o grafo passa a até DISTANCIA_MAXIMA_PREDIO_M dele,
    # nasce uma entrada APROXIMADA (o ponto do caminho mais próximo; a porta exata não está
    # no mapa aberto) e o texto diz isso.
    for p in [p for p in grafo.pontos if p["tipo"] == "predio"]:
        no, dist = no_mais_proximo(grafo, p["lat"], p["lon"])
        p["no"] = None
        if dist <= DISTANCIA_MAXIMA_PREDIO_M:
            lat, lon = grafo.nos[no]
            ligar("Entrada aproximada: " + p["nome"], "entrada", lat, lon,
                  "Ponto do caminho mais próximo deste prédio; a porta exata ainda não está "
                  "no mapa aberto.")


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

def aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def booleano_sql(v) -> str:
    return "NULL" if v is None else ("TRUE" if v else "FALSE")


def wkt_linha(linha) -> str:
    return "LINESTRING(" + ", ".join(f"{lon:.7f} {lat:.7f}" for lon, lat in linha) + ")"


def gerar_sql(grafo: Grafo, data_download: date, recorte=RECORTE) -> str:
    sul, oeste, norte, leste = recorte
    por_tipo = defaultdict(int)
    for a in grafo.arestas:
        por_tipo[a["tipo"]] += 1
    cab = [
        "-- 004: grafo PROVISÓRIO do campus, gerado do OpenStreetMap. NÃO EDITE À MÃO.",
        "--",
        "-- Regenerar:  python3 db/scripts/osm_para_seed.py > db/seeds/004_campus_osm.sql",
        "--",
        "-- Dados de mapa (c) contribuidores do OpenStreetMap, licença ODbL:",
        "--   https://www.openstreetmap.org/copyright",
        "-- Este arquivo é uma Base de Dados Derivada e continua sob a ODbL; quem a",
        "-- redistribuir deve manter esta atribuição.",
        "--",
        f"-- Baixado em {data_download.isoformat()} da Overpass API, retângulo (sul, oeste, norte, leste) "
        f"= {sul}, {oeste}, {norte}, {leste}.",
        f"-- {len(grafo.nos)} nós, {len(grafo.arestas)} arestas ({', '.join(f'{k}: {v}' for k, v in sorted(por_tipo.items()))}), "
        f"{len(grafo.pontos)} pontos de interesse.",
        "--",
        "-- PROVISÓRIO: não foi conferido a pé (fonte_verificacao = 'provisorio'). Vale só até o",
        "-- mapeamento do campus (M2) chegar. Aresta sem etiqueta de acessibilidade fica como",
        "-- 'não verificado' (NULL). Nenhuma mão única foi importada (tudo mão dupla).",
        "--",
        "-- Idempotente: apaga e reinsere o grafo do campus com ids fixos a cada `migrar`.",
        "-- comprimento_m e custo são calculados AQUI, no banco, em SRID 31983 (metro).",
        "",
        "DELETE FROM arestas;",
        "DELETE FROM nos;",
        "DELETE FROM pontos_interesse;",
        "",
    ]
    meta = f"{aspas(FONTE_VERIFICACAO)}, {aspas(MAPEADO_POR)}, DATE {aspas(data_download.isoformat())}"
    linhas = list(cab)
    if grafo.pontos:
        linhas.append("INSERT INTO pontos_interesse (id, geom, tipo, nome, descricao, acessivel, "
                      "fonte_verificacao, mapeado_por, mapeado_em) VALUES")
        linhas.append(",\n".join(
            f"({p['id']}, ST_SetSRID(ST_MakePoint({p['lon']:.7f}, {p['lat']:.7f}), 4326), "
            f"{aspas(p['tipo'])}, {aspas(p['nome'])}, {aspas(p['descricao'])}, "
            f"{booleano_sql(p['acessivel'])}, {meta})" for p in grafo.pontos) + ";")
        linhas.append("")
    # Um nó atende a um ponto só (o primeiro da lista, por ordem de id).
    ponto_do_no = {}
    for p in grafo.pontos:
        if p["no"] is not None and p["tipo"] in ("entrada", "portao") and p["no"] not in ponto_do_no:
            ponto_do_no[p["no"]] = p["id"]
    linhas.append("INSERT INTO nos (id, geom, ponto_interesse_id) VALUES")
    linhas.append(",\n".join(
        f"({i}, ST_SetSRID(ST_MakePoint({lon:.7f}, {lat:.7f}), 4326), "
        f"{ponto_do_no.get(i, 'NULL')})" for i, (lat, lon) in sorted(grafo.nos.items())) + ";")
    linhas.append("")
    linhas.append(
        "INSERT INTO arestas (id, geom, origem_id, destino_id, comprimento_m, tipo, "
        "acessivel_cadeirante, custo, custo_inverso, fonte_verificacao, mapeado_por, mapeado_em)\n"
        "SELECT id, geom, origem_id, destino_id, len, tipo, acessivel_cadeirante, len, len,\n"
        "       fonte_verificacao, mapeado_por, mapeado_em\n"
        "FROM (\n"
        "    SELECT v.id, v.origem_id, v.destino_id, v.tipo, v.acessivel_cadeirante,\n"
        "           v.fonte_verificacao, v.mapeado_por, v.mapeado_em, g.geom,\n"
        "           ST_Length(ST_Transform(g.geom, 31983)) AS len\n"
        "    FROM (VALUES")
    linhas.append(",\n".join(
        f"        ({a['id']}, {a['origem']}, {a['destino']}, {aspas(a['tipo'])}, "
        f"{booleano_sql(a['acessivel_cadeirante'])}, {aspas(wkt_linha(a['linha']))}, {meta})"
        for a in grafo.arestas))
    linhas.append(
        "    ) AS v(id, origem_id, destino_id, tipo, acessivel_cadeirante, wkt, fonte_verificacao, "
        "mapeado_por, mapeado_em)\n"
        "    CROSS JOIN LATERAL (SELECT ST_GeomFromText(v.wkt, 4326) AS geom) AS g\n"
        ") AS t;")
    linhas.append("")
    for tabela in ("pontos_interesse", "nos", "arestas"):
        linhas.append(f"SELECT setval(pg_get_serial_sequence('{tabela}', 'id'), "
                      f"GREATEST((SELECT max(id) FROM {tabela}), 1));")
    return "\n".join(linhas) + "\n"


def gerar(dados: dict, data_download: date, recorte=RECORTE,
          com_calcadas_de_rua: bool = False) -> tuple[str, Grafo]:
    # primeiro passa os pontos que precisam virar nó
    alvos = [(lat, lon) for _c, _n, _t, lat, lon, _d in PONTOS_DE_CONTROLE]
    alvos += [(e["lat"], e["lon"]) for e in dados.get("elements", [])
              if e.get("type") == "node" and e.get("tags", {}).get("name")
              and "entrance" in e.get("tags", {})
              and dentro_do_recorte(e["lat"], e["lon"], recorte)]
    grafo = construir_grafo(dados, recorte, com_calcadas_de_rua, alvos)
    if not grafo.arestas:
        raise SystemExit("erro: nenhum caminho no recorte.")
    adicionar_pontos(grafo, dados, recorte)
    return gerar_sql(grafo, data_download, recorte), grafo


def relatorio(grafo: Grafo) -> str:
    por_tipo = defaultdict(int)
    for a in grafo.arestas:
        por_tipo[a["tipo"]] += 1
    com_no = [p for p in grafo.pontos if p["no"] is not None]
    linhas = [f"nós: {len(grafo.nos)}; arestas: {len(grafo.arestas)} {dict(por_tipo)}; "
              f"pontos: {len(grafo.pontos)} ({len(com_no)} com nó); "
              f"arestas fora da maior componente: {grafo.descartadas}"]
    for p in grafo.pontos:
        linhas.append(f"  ponto {p['id']:>2} {p['tipo']:<8} {p['nome']}  "
                      f"(nó {p['no']}, {p['distancia_ao_no_m']:.0f} m do grafo)")
    linhas += [f"  AVISO: {a}" for a in grafo.avisos]
    return "\n".join(linhas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", help="usa um download já salvo em vez de chamar a Overpass")
    ap.add_argument("--salvar-json", help="grava a resposta bruta da Overpass neste arquivo")
    ap.add_argument("--com-calcadas-de-rua", action="store_true",
                    help="inclui footway=sidewalk e crossing (padrão: só o interior do campus)")
    ap.add_argument("--data", help="data do download (AAAA-MM-DD); padrão: hoje")
    args = ap.parse_args(argv)

    if args.json:
        with open(args.json, encoding="utf-8") as f:
            dados = json.load(f)
    else:
        dados = baixar()
        if args.salvar_json:
            with open(args.salvar_json, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
    data_download = date.fromisoformat(args.data) if args.data else date.today()
    sql, grafo = gerar(dados, data_download, com_calcadas_de_rua=args.com_calcadas_de_rua)
    print(relatorio(grafo), file=sys.stderr)
    if len(grafo.arestas) < MIN_ARESTAS_GRAFO:
        print(f"AVISO: só {len(grafo.arestas)} arestas conexas (< {MIN_ARESTAS_GRAFO}): "
              "considere o plano B2 (grafo esquemático à mão).", file=sys.stderr)
    sys.stdout.write(sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
