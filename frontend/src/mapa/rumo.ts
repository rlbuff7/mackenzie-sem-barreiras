/*
 * Decide se o marcador "você está aqui" mostra a seta de direção, e para onde ela aponta.
 * Regra do projeto (CLAUDE.md §1: silêncio é melhor que palpite): sem rumo conhecido, só a bola.
 * Rumo conhecido é um destes dois:
 *   1. heading do GPS, com o aparelho em movimento (parado, o navegador manda null ou NaN, e o
 *      valor com velocidade quase zero é ruído);
 *   2. bússola com fonte absoluta (referência: norte). "alpha_relativo" não aponta para o norte
 *      e nunca vira seta.
 * Sem DOM: só números, para o node:test.
 */

/** Abaixo disto o heading do GPS é ruído. Provisório: confirmar com os dados de campo. */
export const VELOCIDADE_MINIMA_RUMO_GPS_MS = 0.5;

/** Fontes de bússola que apontam para o norte (nomes gravados em medicao.ts). */
export const FONTES_BUSSOLA_ABSOLUTAS: readonly string[] = ["webkitCompassHeading", "alpha_absoluto"];

export interface EntradaRumo {
  rumo_gps_graus: number | null;
  velocidade_ms: number | null;
  bussola: { rumo_graus: number; fonte: string } | null;
}

const finito = (n: number | null | undefined): n is number => typeof n === "number" && Number.isFinite(n);

/** Leva qualquer ângulo para 0 <= x < 360 (e arredonda para 1 grau, que basta para uma seta). */
export function normalizarRumo_graus(graus: number): number {
  const n = ((Math.round(graus) % 360) + 360) % 360;
  return n;
}

/** Rumo em graus (0 = norte, sentido horário) para a seta, ou null quando não há rumo confiável. */
export function rumoParaSeta(e: EntradaRumo): number | null {
  if (finito(e.rumo_gps_graus) && finito(e.velocidade_ms) && e.velocidade_ms >= VELOCIDADE_MINIMA_RUMO_GPS_MS) {
    return normalizarRumo_graus(e.rumo_gps_graus);
  }
  if (e.bussola && finito(e.bussola.rumo_graus) && FONTES_BUSSOLA_ABSOLUTAS.includes(e.bussola.fonte)) {
    return normalizarRumo_graus(e.bussola.rumo_graus);
  }
  return null;
}
