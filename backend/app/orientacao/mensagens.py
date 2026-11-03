"""Escolha da mensagem falada (RF12, RNF05): UMA frase curta ou nenhuma.

Funções puras: recebem a avaliação da posição, a direção, as instruções e os obstáculos da
rota e o histórico recente enviado pelo cliente; nada é gravado (RNF04) e o servidor não
guarda estado entre chamadas (o cliente reenvia `recentes`).

Prioridade (a primeira aplicável decide; se ela estiver suprimida pela anti-repetição, o
resultado é silêncio, nunca uma mensagem de menor prioridade por cima):
  1. `perigo`: escada ou travessia a menos de `distancia_perigo_m` à frente. Só com
     `na_rota`: com a pessoa fora da rota o progresso projetado não é confiável, e avisar
     de um obstáculo "à frente" de um ponto onde ela talvez nem esteja seria palpite.
  2. `fora_da_rota` / `precisao_insuficiente` ("alta"): manda parar e esperar. NUNCA dá
     direção para voltar (a confiança é sempre baixa nesses estados).
  3. curva iminente ("media"), sem confiança baixa.
  4. chegada ("media").
  5. confirmação periódica "Siga em frente." ("baixa"): só com direção "frente" e
     confiança não baixa, isto é, quando a bússola confirma que a pessoa está alinhada.

Nenhuma frase manda ir para a via, para escada não anunciada ou para fora do grafo: só
avisa, manda parar ou descreve a própria rota. Textos curtos, metros sempre com unidade.
Intervalos e distâncias PROVISÓRIOS, do `.env` (`ParametrosMensagens.de_configuracoes`).
"""

from dataclasses import dataclass
from typing import Literal

from app.config import Configuracoes
from app.orientacao.posicao import Avaliacao
from app.orientacao.rumo import Direcao
from app.rotas.instrucoes import arredondar_metros

Prioridade = Literal["perigo", "alta", "media", "baixa"]

TEXTO_FORA_DA_ROTA = "Você saiu da rota. Pare e aguarde."
TEXTO_SEM_POSICAO = "Não sei onde você está agora. Fique parado por alguns segundos."
TEXTO_CONFIRMACAO = "Siga em frente."

_FRASE_DA_CURVA = {
    "direita": "vire à direita",
    "esquerda": "vire à esquerda",
    "leve_direita": "vire levemente à direita",
    "leve_esquerda": "vire levemente à esquerda",
    "retorno": "faça o retorno",
}
_NOME_DO_OBSTACULO = {"escada": "escada", "travessia": "travessia de rua"}


@dataclass(frozen=True)
class ParametrosMensagens:
    intervalo_repeticao_s: float
    intervalo_repeticao_perigo_s: float
    distancia_perigo_m: float
    distancia_curva_iminente_m: float

    @classmethod
    def de_configuracoes(cls, config: Configuracoes) -> "ParametrosMensagens":
        return cls(
            intervalo_repeticao_s=config.intervalo_repeticao_segundos,
            intervalo_repeticao_perigo_s=config.intervalo_repeticao_perigo_segundos,
            distancia_perigo_m=config.distancia_perigo_metros,
            distancia_curva_iminente_m=config.distancia_curva_iminente_metros,
        )


@dataclass(frozen=True)
class ObstaculoNaRota:
    """Trecho de escada ou travessia, em metros ao longo da rota (do início dela)."""

    tipo: str  # "escada" | "travessia"
    inicio_m: float
    fim_m: float


@dataclass(frozen=True)
class Recente:
    """Mensagem que o cliente já falou: a chave e há quantos segundos."""

    chave: str
    ha_segundos: float


@dataclass(frozen=True)
class Mensagem:
    chave: str
    texto: str
    prioridade: Prioridade


def obstaculos_dos_trechos(trechos: list[dict]) -> list[ObstaculoNaRota]:
    """Escadas e travessias da rota (`trechos` de `POST /rotas`: `tipo`, `comprimento_m`),
    com a posição acumulada. Soma de comprimentos, a mesma medida de `inicio_m` das
    instruções."""
    obstaculos = []
    acumulado = 0.0
    for trecho in trechos:
        fim = acumulado + float(trecho["comprimento_m"])
        if trecho["tipo"] in _NOME_DO_OBSTACULO:
            obstaculos.append(ObstaculoNaRota(trecho["tipo"], round(acumulado, 1), round(fim, 1)))
        acumulado = fim
    return obstaculos


def _suprimida(mensagem: Mensagem, recentes: list[Recente], parametros: ParametrosMensagens):
    intervalo = (
        parametros.intervalo_repeticao_perigo_s
        if mensagem.prioridade == "perigo"
        else parametros.intervalo_repeticao_s
    )
    return any(r.chave == mensagem.chave and r.ha_segundos < intervalo for r in recentes)


def _perigo(
    obstaculos: list[ObstaculoNaRota], progresso_m: float, parametros: ParametrosMensagens
) -> Mensagem | None:
    """O obstáculo mais próximo a menos de `distancia_perigo_m` à frente (ou sob os pés)."""
    candidatos = [
        (max(0.0, o.inicio_m - progresso_m), indice, o)
        for indice, o in enumerate(obstaculos)
        if progresso_m < o.fim_m and o.inicio_m - progresso_m <= parametros.distancia_perigo_m
    ]
    if not candidatos:
        return None
    distancia, indice, obstaculo = min(candidatos, key=lambda c: c[0])
    nome = _NOME_DO_OBSTACULO[obstaculo.tipo]
    if distancia < 2.5:
        texto = f"Atenção: {nome} logo à frente."
    else:
        texto = f"Atenção: {nome} em {arredondar_metros(distancia)} metros."
    return Mensagem(f"perigo_{obstaculo.tipo}_{indice}", texto, "perigo")


def _curva_iminente(
    instrucoes: list[dict], progresso_m: float, parametros: ParametrosMensagens
) -> Mensagem | None:
    """A curva no FIM da instrução i fica onde começa a instrução i+1."""
    for i, (instrucao, seguinte) in enumerate(zip(instrucoes, instrucoes[1:], strict=False)):
        frase = _FRASE_DA_CURVA.get(instrucao.get("curva") or "")
        distancia = seguinte["inicio_m"] - progresso_m
        if frase and 0.0 <= distancia <= parametros.distancia_curva_iminente_m:
            return Mensagem(
                f"curva_{i}", f"Em {arredondar_metros(distancia)} metros, {frase}.", "media"
            )
    return None


def _candidata(
    avaliacao: Avaliacao,
    direcao: Direcao | None,
    instrucoes: list[dict],
    obstaculos: list[ObstaculoNaRota],
    parametros: ParametrosMensagens,
) -> Mensagem | None:
    if avaliacao.estado == "precisao_insuficiente" or avaliacao.projecao is None:
        return Mensagem("sem_posicao", TEXTO_SEM_POSICAO, "alta")
    progresso = avaliacao.projecao.distancia_percorrida_m
    if avaliacao.estado == "na_rota":
        perigo = _perigo(obstaculos, progresso, parametros)
        if perigo is not None:
            return perigo
    if avaliacao.estado == "fora_da_rota":
        return Mensagem("fora_da_rota", TEXTO_FORA_DA_ROTA, "alta")
    if avaliacao.estado == "chegou":
        texto = instrucoes[-1]["texto"] if instrucoes else "Você chegou ao destino."
        return Mensagem("chegada", texto, "media")
    if avaliacao.confianca == "baixa":
        return None
    curva = _curva_iminente(instrucoes, progresso, parametros)
    if curva is not None:
        return curva
    if direcao == "frente":
        return Mensagem("siga_em_frente", TEXTO_CONFIRMACAO, "baixa")
    return None


def decidir_mensagem(
    avaliacao: Avaliacao,
    *,
    direcao: Direcao | None,
    instrucoes: list[dict],
    obstaculos: list[ObstaculoNaRota],
    recentes: list[Recente],
    parametros: ParametrosMensagens,
) -> Mensagem | None:
    """A única mensagem a falar agora, ou `None` (silêncio)."""
    mensagem = _candidata(avaliacao, direcao, instrucoes, obstaculos, parametros)
    if mensagem is None or _suprimida(mensagem, recentes, parametros):
        return None
    return mensagem
