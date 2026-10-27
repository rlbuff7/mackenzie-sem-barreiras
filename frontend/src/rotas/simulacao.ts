/**
 * Modo demonstração "Simular caminhada": lógica pura (sem DOM) para andar uma bolinha pela rota.
 * A posição é imaginária, não é o GPS. Coordenadas do GeoJSON: [longitude, latitude]; unidades no nome.
 */
export type Curva = "direita" | "esquerda" | "leve_direita" | "leve_esquerda" | "retorno" | "escada";

export interface InstrucaoSimulada {
  ordem?: number;
  texto: string;
  /** Metros ao longo da geometria onde a instrução começa (opcional: sem ele, divide-se igualmente). */
  inicio_m?: number | null;
  /** O que acontece no FIM da instrução (opcional). */
  curva?: Curva | null;
}

export const ANTECEDENCIA_CURVA_M = 10;
export const VELOCIDADE_BASE_M_POR_S = 1.0;
export const PASSO_S = 0.25;
export const FATORES_SIMULACAO = [5, 10] as const;
export const FATOR_PADRAO = 10;
export const VIBRACAO_CHEGADA = [200, 100, 200];
export const ROTULO_SIMULACAO = "Simulação: a posição é imaginária, não é o GPS.";

const RAIO_TERRA_M = 6371008.8;

/** Distância equiretangular em metros entre dois pontos [lon, lat] (suficiente em escala de campus). */
export function distanciaEntre_m(a: readonly [number, number], b: readonly [number, number]): number {
  const rad = Math.PI / 180;
  const x = (b[0] - a[0]) * rad * Math.cos(((a[1] + b[1]) / 2) * rad);
  const y = (b[1] - a[1]) * rad;
  return Math.sqrt(x * x + y * y) * RAIO_TERRA_M;
}

export function comprimentoTotal_m(geometria: readonly (readonly [number, number])[]): number {
  let total = 0;
  for (let i = 1; i < geometria.length; i++) total += distanciaEntre_m(geometria[i - 1]!, geometria[i]!);
  return total;
}

/** Ponto [lon, lat] a `metros` do início da linha (limitado a 0 e ao comprimento total). Linha vazia: null. */
export function pontoNaDistancia(
  geometria0: readonly (readonly [number, number])[],
  metros: number,
): [number, number] | null {
  const geometria = geometria0 as readonly (readonly [number, number])[];
  const g = (i: number): readonly [number, number] => geometria[i] as readonly [number, number];
  if (geometria.length === 0) return null;
  if (geometria.length === 1 || !(metros > 0)) return [g(0)[0], g(0)[1]];
  let restante = metros;
  for (let i = 1; i < geometria.length; i++) {
    const trecho = distanciaEntre_m(g(i - 1), g(i));
    if (restante <= trecho && trecho > 0) {
      const t = restante / trecho;
      return [
        g(i - 1)[0] + (g(i)[0] - g(i - 1)[0]) * t,
        g(i - 1)[1] + (g(i)[1] - g(i - 1)[1]) * t,
      ];
    }
    restante -= trecho;
  }
  const ultimo = g(geometria.length - 1);
  return [ultimo[0], ultimo[1]];
}

export interface InstrucaoNormalizada {
  texto: string;
  inicio_m: number;
  fim_m: number;
  curva: Curva | null;
}

/** Preenche inicio_m/fim_m. Se algum inicio_m faltar, distribui igualmente e ignora a curva (não vibra). */
export function normalizarInstrucoes(instrucoes: readonly InstrucaoSimulada[], total_m: number): InstrucaoNormalizada[] {
  const n = instrucoes.length;
  const completo = instrucoes.every((i) => typeof i.inicio_m === "number" && Number.isFinite(i.inicio_m));
  return instrucoes.map((i, idx) => {
    const inicio_m = completo ? (i.inicio_m as number) : (total_m * idx) / n;
    const fim_m = idx + 1 < n ? (completo ? (instrucoes[idx + 1]!.inicio_m as number) : (total_m * (idx + 1)) / n) : total_m;
    return { texto: i.texto, inicio_m, fim_m, curva: completo ? (i.curva ?? null) : null };
  });
}

const TEXTO_CURVA: Record<Curva, string> = {
  direita: "Em 10 metros, vire à direita.",
  esquerda: "Em 10 metros, vire à esquerda.",
  leve_direita: "Em 10 metros, vire levemente à direita.",
  leve_esquerda: "Em 10 metros, vire levemente à esquerda.",
  retorno: "Em 10 metros, faça o retorno.",
  escada: "Em 10 metros, há uma escada.",
};

export function textoDaCurva(curva: Curva): string {
  return TEXTO_CURVA[curva];
}

export function padraoDeVibracao(curva: Curva | null | undefined): number[] {
  switch (curva) {
    case "direita": return [80, 80, 80];
    case "esquerda": return [300];
    case "leve_direita":
    case "leve_esquerda": return [80];
    case "retorno": return [300, 100, 300];
    case "escada": return [80, 60, 80, 60, 80];
    default: return [];
  }
}

export interface FalaDevida {
  /** Chave para marcar como já falada: "i:<índice>" (instrução) ou "c:<índice>" (aviso de curva). */
  chave: string;
  texto: string;
  /** Só nos avisos de curva. */
  curva: Curva | null;
}

/**
 * A próxima fala que já deveria ter acontecido em `metrosPercorridos` e ainda não está em `jaFaladas`
 * (ordem: instrução i, depois aviso da curva de i). Quem chama repete até receber null e adiciona a chave.
 */
export function proximaFala(
  instrucoes: readonly InstrucaoSimulada[],
  metrosPercorridos: number,
  jaFaladas: ReadonlySet<string>,
  total_m?: number,
): FalaDevida | null {
  const lista = normalizarInstrucoes(instrucoes, total_m ?? ultimoInicio(instrucoes));
  for (let i = 0; i < lista.length; i++) {
    const it = lista[i]!;
    if (metrosPercorridos >= it.inicio_m && !jaFaladas.has(`i:${i}`)) return { chave: `i:${i}`, texto: it.texto, curva: null };
    if (it.curva) {
      const ponto = Math.max(it.inicio_m, it.fim_m - ANTECEDENCIA_CURVA_M);
      if (metrosPercorridos >= ponto && !jaFaladas.has(`c:${i}`)) return { chave: `c:${i}`, texto: textoDaCurva(it.curva), curva: it.curva };
    }
  }
  return null;
}

function ultimoInicio(instrucoes: readonly InstrucaoSimulada[]): number {
  const ultimo = instrucoes[instrucoes.length - 1]?.inicio_m;
  return typeof ultimo === "number" ? ultimo : 0;
}

export function fatorValido(v: unknown): number {
  const n = Number(v);
  return (FATORES_SIMULACAO as readonly number[]).includes(n) ? n : FATOR_PADRAO;
}

/** Metros avançados em um passo do timer. */
export function metrosPorPasso(fator: number): number {
  return VELOCIDADE_BASE_M_POR_S * fator * PASSO_S;
}
