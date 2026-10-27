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

export const ANTECEDENCIA_CURVA_S = 3;
export const ANTECEDENCIA_MINIMA_M = 5;
export const FOLGA_FALA_INSTRUCAO_S = 4;
export const CURVA_IMEDIATA_S = 1.5;
export const VELOCIDADE_BASE_M_POR_S = 1.0;
export const PASSO_S = 0.25;
export const FATORES_SIMULACAO = [2, 5, 10] as const;
export const FATOR_PADRAO = 5;
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

const TEXTO_AVISO: Record<Curva, (n: number) => string> = {
  direita: (n) => `Em ${n} metros, vire à direita.`,
  esquerda: (n) => `Em ${n} metros, vire à esquerda.`,
  leve_direita: (n) => `Em ${n} metros, vire levemente à direita.`,
  leve_esquerda: (n) => `Em ${n} metros, vire levemente à esquerda.`,
  retorno: (n) => `Em ${n} metros, faça o retorno.`,
  escada: (n) => `Em ${n} metros, há uma escada.`,
};

const TEXTO_AGORA: Record<Curva, string> = {
  direita: "Vire à direita agora.",
  esquerda: "Vire à esquerda agora.",
  leve_direita: "Vire levemente à direita agora.",
  leve_esquerda: "Vire levemente à esquerda agora.",
  retorno: "Faça o retorno agora.",
  escada: "Escada agora. Use o corrimão se houver.",
};

/** Aviso antecipado; `distancia_m` é a distância real restante (arredondada a 5 m, mínimo 5). */
export function textoDaCurva(curva: Curva, distancia_m = 10): string {
  const n = Math.max(5, Math.round(distancia_m / 5) * 5);
  return TEXTO_AVISO[curva](n);
}

export function textoDaCurvaAgora(curva: Curva): string {
  return TEXTO_AGORA[curva];
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

export interface EventoDeFala {
  /** Metros percorridos a partir dos quais a fala é devida. */
  m: number;
  texto: string;
  /** "alta" cancela o que estiver falando (curva agora); "normal" entra na fila. */
  prioridade: "alta" | "normal";
  /** Padrão de vibração (vazio = não vibra). Só a fala "agora" vibra. */
  vibrar: number[];
  /** Chave única: "i:<n>" instrução, "a:<n>" aviso, "c:<n>" curva agora. */
  chave: string;
}

/** Velocidade simulada em m/s para o fator escolhido. */
export function velocidadeSimulada_m_s(fator: number): number {
  return VELOCIDADE_BASE_M_POR_S * fator;
}

function primeiraFrase(texto: string): string {
  const i = texto.indexOf(".");
  return (i >= 0 ? texto.slice(0, i + 1) : texto).trim();
}

/**
 * Roteiro completo das falas, ordenado por metro. O aviso de curva sai quando faltam <= 3 s de
 * reprodução (distância <= velocidade_simulada x 3, mínimo 5 m); a fala "agora" sai ao fim da instrução
 * e tem prioridade. A fala de início da instrução é encurtada (1ª frase) se a curva está a < 4 s,
 * e pulada se estiver a < 1,5 s.
 */
export function planejarFalas(instrucoes: readonly InstrucaoSimulada[], total_m: number, fator: number): EventoDeFala[] {
  const v = velocidadeSimulada_m_s(fator);
  const antecedencia_m = Math.max(ANTECEDENCIA_MINIMA_M, v * ANTECEDENCIA_CURVA_S);
  const lista = normalizarInstrucoes(instrucoes, total_m);
  const eventos: EventoDeFala[] = [];
  lista.forEach((it, i) => {
    let texto: string | null = it.texto;
    if (it.curva) {
      const segundos = (it.fim_m - it.inicio_m) / v;
      if (segundos < CURVA_IMEDIATA_S) texto = null;
      else if (segundos < FOLGA_FALA_INSTRUCAO_S) texto = primeiraFrase(it.texto);
    }
    if (texto) eventos.push({ m: it.inicio_m, texto, prioridade: "normal", vibrar: [], chave: `i:${i}` });
    if (it.curva) {
      const m = Math.max(it.inicio_m, it.fim_m - antecedencia_m);
      eventos.push({ m, texto: textoDaCurva(it.curva, it.fim_m - m), prioridade: "normal", vibrar: [], chave: `a:${i}` });
      eventos.push({ m: it.fim_m, texto: textoDaCurvaAgora(it.curva), prioridade: "alta", vibrar: padraoDeVibracao(it.curva), chave: `c:${i}` });
    }
  });
  // Estável: no mesmo metro a ordem de inserção (a "agora" da anterior vem antes da instrução seguinte).
  return eventos
    .map((e, idx) => ({ e, idx }))
    .sort((x, y) => x.e.m - y.e.m || x.idx - y.idx)
    .map((x) => x.e);
}

/** Próximo evento já devido em `metrosPercorridos` e ainda não falado; null se não há. */
export function proximoEvento(eventos: readonly EventoDeFala[], metrosPercorridos: number, jaFaladas: ReadonlySet<string>): EventoDeFala | null {
  for (const e of eventos) {
    if (e.m > metrosPercorridos) break;
    if (!jaFaladas.has(e.chave)) return e;
  }
  return null;
}

export function fatorValido(v: unknown): number {
  const n = Number(v);
  return (FATORES_SIMULACAO as readonly number[]).includes(n) ? n : FATOR_PADRAO;
}

/** Metros avançados em um passo do timer. */
export function metrosPorPasso(fator: number): number {
  return VELOCIDADE_BASE_M_POR_S * fator * PASSO_S;
}
