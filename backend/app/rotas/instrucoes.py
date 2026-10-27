"""Instruções em texto para uma rota, curva a curva (decisão do Rodrigo, 27/10/2026).

Antes só havia tipo de trecho + distância. Para quem não enxerga isso não orienta, então
a rota (sequência de trechos com geometria) é percorrida por inteiro e cada mudança de
rumo vira uma frase: "Siga em frente por cerca de 40 metros (uns 40 segundos). Depois,
vire à direita."

ATENÇÃO (decisão provisória, a validar com a orientadora): a regra antiga "trecho não
conferido a pé não gera instrução de direção" está SUSPENSA na v0. Os rumos saem do mapa
aberto (OpenStreetMap), sem conferência a pé; por isso a resposta leva o aviso de rota
provisória (ver `routers/rotas.py`). Nada aqui guarda a posição de quem navega.

Regras:
- rumo de cada pedaço da polilinha em metros (projeção plana local: dentro de um campus
  difere do SRID 31983 em menos de 0,1%; sem dependência nova, CLAUDE.md §5);
- pedaços consecutivos com mudança de rumo < 25° viram um "siga em frente"; pedaços de
  caminho < 8 m não contam para o rumo (zigue-zague curto não gera curva fantasma);
- Δ de 25 a 60° "levemente", 60 a 135° curva, acima de 135° retorno (positivo = direita);
- distância em múltiplos de 5 m (mínimo 5); tempo a 1,0 m/s em múltiplos de 5 s, em
  minutos acima de 90 s;
- escada e travessia são anunciadas ANTES; no máximo 2 pontos de interesse por instrução;
- o primeiro passo não diz "direita/esquerda" (não se sabe para onde a pessoa está virada).
"""

import math

from app.rotas.modelos import Trecho

MAX_REFERENCIAS_POR_INSTRUCAO = 2
LIMITE_CURVA_GRAUS = 25.0
LIMITE_CURVA_FORTE_GRAUS = 60.0
LIMITE_RETORNO_GRAUS = 135.0
ZIGUE_ZAGUE_METROS = 8.0
VELOCIDADE_METROS_POR_SEGUNDO = 1.0
VELOCIDADE_ESCADA_METROS_POR_SEGUNDO = 0.5
LIMITE_SEGUNDOS_PARA_MINUTOS = 90

# Metros por grau perto de São Paulo (lat -23,5): suficiente para rumo e comprimento relativo.
_METROS_POR_GRAU_LAT = 110_600.0
_METROS_POR_GRAU_LON_NO_EQUADOR = 111_320.0

AVISO_ROTA_PROVISORIA = (
    "Rota provisória: direções calculadas pelo mapa aberto. Confira com a bengala."
)


def arredondar_metros(metros: float) -> int:
    """Múltiplo de 5 mais próximo (meio sobe: 7,5 vira 10), nunca menos que 5."""
    return max(5, int(metros / 5 + 0.5) * 5)


def _duracao_em_texto(metros: int, velocidade: float = VELOCIDADE_METROS_POR_SEGUNDO) -> str:
    segundos = arredondar_metros(metros / velocidade)
    if segundos <= LIMITE_SEGUNDOS_PARA_MINUTOS:
        return f"uns {segundos} segundos"
    minutos = round(segundos / 60 * 2) / 2
    inteiros = int(minutos)
    if minutos == inteiros:
        return f"cerca de {inteiros} minutos"
    return (
        f"cerca de {inteiros} minuto e meio"
        if inteiros == 1
        else (f"cerca de {inteiros} minutos e meio")
    )


def _diferenca_de_rumo(novo: float, antigo: float) -> float:
    """Δ em graus no intervalo (-180, 180]; positivo = para a direita (horário)."""
    delta = (novo - antigo + 540.0) % 360.0 - 180.0
    return 180.0 if delta == -180.0 else delta


def _frase_da_curva(delta: float) -> str:
    lado = "direita" if delta > 0 else "esquerda"
    modulo = abs(delta)
    if modulo > LIMITE_RETORNO_GRAUS:
        return "faça o retorno"
    if modulo < LIMITE_CURVA_FORTE_GRAUS:
        return f"vire levemente à {lado}"
    return f"vire à {lado}"


PREFIXO_ENTRADA_APROXIMADA = "Entrada aproximada:"
LIMITE_CURVAS_SEGUIDAS_METROS = 25.0


def _artigo(preposicao: str, nome: str) -> str:
    """'de'/'a'/'por' + nome com o artigo certo, por heurística (feminino termina em 'a').

    Só no texto falado: "Entrada aproximada: X" vira "a lateral da X" (o nome no banco
    e em GET /pontos-interesse não muda)."""
    if nome.startswith(PREFIXO_ENTRADA_APROXIMADA):
        resto = nome[len(PREFIXO_ENTRADA_APROXIMADA) :].strip()
        lateral = {"de": "da", "a": "à", "por": "pela"}[preposicao]
        artigo_de = "da" if resto.split(" ", 1)[0].lower().endswith("a") else "do"
        return f"{lateral} lateral {artigo_de} {resto}"
    nome = nome[:1].lower() + nome[1:]
    primeira = nome.split(" ", 1)[0].lower()
    feminino = primeira.endswith("a")
    artigo = {
        "de": ("da", "do"),
        "a": ("à", "ao"),
        "por": ("pela", "pelo"),
    }[preposicao][0 if feminino else 1]
    return f"{artigo} {nome}"


def _categoria(tipo: str) -> str:
    return tipo if tipo in ("escada", "travessia") else "andar"


class _Pedaco:
    """Um segmento reto da polilinha da rota, já com o comprimento ajustado ao do trecho."""

    def __init__(self, categoria: str, comprimento_m: float, rumo: float | None):
        self.categoria = categoria
        self.comprimento_m = comprimento_m
        self.rumo = rumo


class _Perna:
    """Pedaços seguidos tratados como um 'siga em frente' (ou uma escada, ou uma travessia)."""

    def __init__(self, categoria: str, inicio: str | None):
        self.categoria = categoria
        self.inicio = inicio  # None na primeira; "categoria" ou "deriva" nas demais
        self.comprimento_m = 0.0
        self.fim_acumulado_m = 0.0
        self.rumo_inicial: float | None = None
        self.rumo_final: float | None = None
        self._rumo_reserva: float | None = None
        self.curva_graus: float | None = None  # mudança de rumo no fim desta perna


def _pedacos_da_rota(trechos: list[Trecho]) -> list[_Pedaco]:
    ponto_ref = next((c for t in trechos for c in t.coordenadas[:1]), None)
    if ponto_ref is None:
        return [_Pedaco(_categoria(t.tipo), t.comprimento_m, None) for t in trechos]
    lon0, lat0 = ponto_ref[0], ponto_ref[1]
    metros_por_grau_lon = _METROS_POR_GRAU_LON_NO_EQUADOR * math.cos(math.radians(lat0))

    def plano(coord: list[float]) -> tuple[float, float]:
        return (coord[0] - lon0) * metros_por_grau_lon, (coord[1] - lat0) * _METROS_POR_GRAU_LAT

    pedacos: list[_Pedaco] = []
    for trecho in trechos:
        categoria = _categoria(trecho.tipo)
        retos = []
        for a, b in zip(trecho.coordenadas, trecho.coordenadas[1:], strict=False):
            (xa, ya), (xb, yb) = plano(a), plano(b)
            dx, dy = xb - xa, yb - ya
            comprimento = math.hypot(dx, dy)
            if comprimento > 0:
                retos.append((comprimento, math.degrees(math.atan2(dx, dy)) % 360.0))
        soma = sum(c for c, _ in retos)
        if not retos:
            pedacos.append(_Pedaco(categoria, trecho.comprimento_m, None))
            continue
        # o comprimento do banco (SRID 31983) manda; a geometria só dá a direção
        escala = trecho.comprimento_m / soma
        pedacos.extend(_Pedaco(categoria, c * escala, rumo) for c, rumo in retos)
    return pedacos


def _pernas_da_rota(pedacos: list[_Pedaco]) -> list[_Perna]:
    pernas: list[_Perna] = []
    acumulado = 0.0
    for p in pedacos:
        acumulado += p.comprimento_m
        significativo = p.rumo is not None and (
            p.categoria != "andar" or p.comprimento_m >= ZIGUE_ZAGUE_METROS
        )
        atual = pernas[-1] if pernas else None
        if atual is None or atual.categoria != p.categoria:
            pernas.append(_Perna(p.categoria, None if atual is None else "categoria"))
        elif (
            p.categoria == "andar"
            and significativo
            and atual.rumo_inicial is not None
            and abs(_diferenca_de_rumo(p.rumo, atual.rumo_inicial)) >= LIMITE_CURVA_GRAUS
        ):
            pernas.append(_Perna(p.categoria, "deriva"))
        perna = pernas[-1]
        perna.comprimento_m += p.comprimento_m
        perna.fim_acumulado_m = acumulado
        if significativo:
            if perna.rumo_inicial is None:
                perna.rumo_inicial = p.rumo
            perna.rumo_final = p.rumo
        elif p.rumo is not None and perna._rumo_reserva is None:
            perna._rumo_reserva = p.rumo
    for perna in pernas:
        if perna.rumo_inicial is None:
            perna.rumo_inicial = perna._rumo_reserva
            perna.rumo_final = perna._rumo_reserva
    for perna, proxima in zip(pernas, pernas[1:], strict=False):
        if proxima.inicio == "deriva":
            antigo = perna.rumo_inicial  # a curva é medida contra o rumo em que a perna começou
        else:
            antigo = perna.rumo_final
        if antigo is None or proxima.rumo_inicial is None:
            continue
        delta = _diferenca_de_rumo(proxima.rumo_inicial, antigo)
        if abs(delta) >= LIMITE_CURVA_GRAUS:
            perna.curva_graus = delta
    return _juntar_curvas_leves_seguidas(pernas)


def _leve(delta: float | None) -> bool:
    return delta is not None and LIMITE_CURVA_GRAUS <= abs(delta) < LIMITE_CURVA_FORTE_GRAUS


def _juntar_curvas_leves_seguidas(pernas: list[_Perna]) -> list[_Perna]:
    """Duas curvas leves a menos de 25 m uma da outra viram uma só, pela soma dos ângulos.

    A perna do meio (curta) é juntada à seguinte; se a soma ficar abaixo de 25° não há
    curva e as três pernas viram um "siga em frente"."""
    i = 0
    while i + 2 < len(pernas):
        a, meio, c = pernas[i], pernas[i + 1], pernas[i + 2]
        if (
            a.categoria == meio.categoria == c.categoria == "andar"
            and _leve(a.curva_graus)
            and _leve(meio.curva_graus)
            and meio.comprimento_m < LIMITE_CURVAS_SEGUIDAS_METROS
        ):
            soma = (a.curva_graus or 0.0) + (meio.curva_graus or 0.0)
            if abs(soma) < LIMITE_CURVA_GRAUS:
                a.comprimento_m += meio.comprimento_m + c.comprimento_m
                a.fim_acumulado_m = c.fim_acumulado_m
                a.curva_graus = c.curva_graus
                del pernas[i + 1 : i + 3]
            else:
                c.comprimento_m += meio.comprimento_m
                a.curva_graus = soma
                del pernas[i + 1]
            continue
        i += 1
    return pernas


def _referencias_por_perna(
    trechos: list[Trecho], pernas: list[_Perna], referencias_por_no: dict[int, str]
) -> list[list[str]]:
    """Nomes de pontos de interesse do MEIO da rota, na perna em que o caminho passa por eles."""
    por_perna: list[list[str]] = [[] for _ in pernas]
    acumulado = 0.0
    for trecho in trechos[:-1]:
        acumulado += trecho.comprimento_m
        nome = referencias_por_no.get(trecho.no_para)
        if not nome:
            continue
        indice = next(
            (i for i, p in enumerate(pernas) if p.fim_acumulado_m >= acumulado - 1e-6),
            len(pernas) - 1,
        )
        if nome not in por_perna[indice]:
            por_perna[indice].append(nome)
    return por_perna


def _distancia_em_texto(comprimento_m: float) -> str:
    metros = arredondar_metros(comprimento_m)
    return f"cerca de {metros} metros ({_duracao_em_texto(metros)})"


def montar_instrucoes(
    trechos: list[Trecho],
    referencias_por_no: dict[int, str],
    destino_nome: str,
    origem_nome: str = "",
) -> list[str]:
    """`referencias_por_no`: nome do ponto de interesse (entrada) por id de nó. Só os nós
    do MEIO do caminho são citados (origem e destino não)."""
    pernas = _pernas_da_rota(_pedacos_da_rota(trechos))
    mencoes = _referencias_por_perna(trechos, pernas, referencias_por_no)
    todas = [n for lista in mencoes for n in lista]
    proxima_referencia = todas[0] if todas else destino_nome

    instrucoes: list[str] = []
    for i, perna in enumerate(pernas):
        seguinte = pernas[i + 1] if i + 1 < len(pernas) else None
        metros = arredondar_metros(perna.comprimento_m)
        distancia = _distancia_em_texto(perna.comprimento_m)
        if perna.categoria == "escada":
            tempo = _duracao_em_texto(metros, VELOCIDADE_ESCADA_METROS_POR_SEGUNDO)
            texto = f"Escada, cerca de {metros} metros ({tempo}). Use o corrimão se houver."
        elif i == 0:
            saindo = f"Saindo {_artigo('de', origem_nome)}, siga" if origem_nome else "Siga"
            texto = f"{saindo} pelo caminho em direção {_artigo('a', proxima_referencia)}"
            texto += f", por {distancia}."
        else:
            texto = f"Siga em frente por {distancia}."
        if i == 0 and perna.categoria == "travessia":
            texto = f"Atenção: travessia. {texto}"
        citadas = [n for n in mencoes[i] if not (i == 0 and n == proxima_referencia)]
        citadas = citadas[:MAX_REFERENCIAS_POR_INSTRUCAO]
        if citadas:
            texto += " Você passa " + " e ".join(_artigo("por", n) for n in citadas) + "."
        if perna.curva_graus is not None:
            texto += f" Depois, {_frase_da_curva(perna.curva_graus)}."
        if seguinte is not None and seguinte.categoria == "escada":
            if perna.curva_graus is not None:
                texto += " Logo em seguida, escada."
            else:
                texto += f" Em cerca de {metros} metros, escada."
        elif seguinte is not None and seguinte.categoria == "travessia":
            texto += " Atenção: travessia."
        instrucoes.append(texto)
    instrucoes.append(f"Você chegou {_artigo('a', destino_nome)}.")
    return instrucoes
