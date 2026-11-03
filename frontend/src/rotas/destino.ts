/**
 * Escolha do destino sem depender do mapa (RF03, RF04, RNF07): texto sem acento, filtro da busca,
 * contagem para o leitor de tela e a frase de "Destino escolhido". Tudo puro, sem DOM: o node:test confere.
 */
import type { PontoInteresse } from "./tipos.ts";

/** Espera depois da última tecla antes de anunciar a contagem (leitor de tela não é atropelado a cada letra). */
export const ESPERA_ANUNCIO_BUSCA_MS = 500;

/** Minúsculas, sem acento, espaços normalizados: "  Prédio   29 " e "predio 29" viram o mesmo texto. */
export function normalizarTexto(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Pontos cujo nome contém TODAS as palavras da consulta (em qualquer ordem). Consulta vazia: todos, na mesma ordem. */
export function filtrarPontos(pontos: PontoInteresse[], consulta: string): PontoInteresse[] {
  const palavras = normalizarTexto(consulta).split(" ").filter((p) => p !== "");
  if (palavras.length === 0) return pontos;
  return pontos.filter((p) => {
    const nome = normalizarTexto(p.nome);
    return palavras.every((palavra) => nome.includes(palavra));
  });
}

/** "3 lugares encontrados" (frase da região aria-live). */
export function textoContagem(quantidade: number): string {
  if (quantidade <= 0) return "Nenhum lugar encontrado";
  return quantidade === 1 ? "1 lugar encontrado" : `${quantidade} lugares encontrados`;
}

export interface EscolhaDeDestino {
  ponto: PontoInteresse;
  /** Frase visível e anunciada: "Destino escolhido: Entrada do Prédio 29". */
  confirmacao: string;
  /** Só quando "De" está vazio: oferece usar a mesma entrada como partida. */
  oferecerOrigem: boolean;
}

export function confirmacaoDeDestino(nome: string): string {
  return `Destino escolhido: ${nome}`;
}

export function confirmacaoDeOrigem(nome: string): string {
  return `Origem escolhida: ${nome}`;
}

export function rotuloDoMarcador(nome: string): string {
  return `${nome}. Tocar para escolher como destino`;
}

/** Destino pelo toque no mapa: só vale para ponto que está na lista de destinos (entrada ligada ao grafo). */
export function escolherDestino(destinos: PontoInteresse[], id: number, origemId: number | null): EscolhaDeDestino | null {
  const ponto = destinos.find((p) => p.id === id);
  if (!ponto) return null;
  return { ponto, confirmacao: confirmacaoDeDestino(ponto.nome), oferecerOrigem: origemId === null };
}

/** Debounce com agenda injetada (testável sem relógio). */
export function criarDebounce(
  acao: () => void,
  ms: number,
  agenda: { agendar: (fn: () => void, ms: number) => unknown; cancelar: (id: unknown) => void },
): { chamar(): void; cancelar(): void } {
  let id: unknown = null;
  const cancelar = (): void => {
    if (id !== null) agenda.cancelar(id);
    id = null;
  };
  return {
    chamar() {
      cancelar();
      id = agenda.agendar(() => {
        id = null;
        acao();
      }, ms);
    },
    cancelar,
  };
}
