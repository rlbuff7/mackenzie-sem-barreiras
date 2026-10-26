"""Instruções em texto para uma rota (E6): tipo de trecho + distância aproximada +
referências citáveis. SEM "vire à direita/esquerda" e sem "à sua frente": rumo é do M4
(`orientacao/rumo.py`), porque erro aí tem consequência física.

Regras (plano E6, B4):
- trechos consecutivos do mesmo tipo viram uma instrução;
- distância arredondada a múltiplos de 5 m, mínimo "cerca de 5 metros" (a imprecisão é
  honesta: não promete metragem exata);
- escada e travessia são anunciadas ANTES do trecho, nunca depois;
- no máximo 2 referências por instrução ("Citar tudo é tão ruim quanto não citar nada");
- a última instrução é sempre a chegada.
"""

from itertools import groupby

from app.rotas.modelos import Trecho

MAX_REFERENCIAS_POR_INSTRUCAO = 2


def arredondar_metros(metros: float) -> int:
    """Múltiplo de 5 mais próximo (meio sobe: 7,5 vira 10), nunca menos que 5."""
    return max(5, int(metros / 5 + 0.5) * 5)


def _frase_do_trecho(tipo: str, metros: int) -> str:
    if tipo == "escada":
        return f"Atenção: há uma escada no caminho, cerca de {metros} metros."
    if tipo == "travessia":
        return f"Atenção: você atravessa uma rua, cerca de {metros} metros."
    if tipo == "rampa":
        return f"Siga por uma rampa, cerca de {metros} metros."
    return f"Siga pelo caminho por cerca de {metros} metros."


def _minuscula_inicial(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def montar_instrucoes(
    trechos: list[Trecho], referencias_por_no: dict[int, str], destino_nome: str
) -> list[str]:
    """`referencias_por_no`: nome do ponto de interesse (entrada) por id de nó. Só os nós
    do MEIO do caminho são citados (origem e destino não)."""
    instrucoes: list[str] = []
    for tipo, grupo in groupby(trechos, key=lambda t: t.tipo):
        trechos_do_grupo = list(grupo)
        metros = arredondar_metros(sum(t.comprimento_m for t in trechos_do_grupo))
        texto = _frase_do_trecho(tipo, metros)
        # nós por onde passa dentro do grupo e na junção com o próximo (não o destino final)
        nos_do_meio = [t.no_para for t in trechos_do_grupo]
        if trechos and trechos_do_grupo[-1] is trechos[-1]:
            nos_do_meio = nos_do_meio[:-1]
        nomes = []
        for no in nos_do_meio:
            nome = referencias_por_no.get(no)
            if nome and nome not in nomes:
                nomes.append(nome)
        for nome in nomes[:MAX_REFERENCIAS_POR_INSTRUCAO]:
            texto += f" Você passa por: {nome}."
        instrucoes.append(texto)
    instrucoes.append(f"Você chegou à {_minuscula_inicial(destino_nome)}.")
    return instrucoes
