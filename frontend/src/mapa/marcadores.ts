/*
 * HTML dos marcadores do mapa (aprovados no canvas de 14/10/2026), sem DOM e sem Leaflet para poder
 * ser testado. As classes ficam em estilos.css e usam só tokens mapa-*, que não mudam com o tema
 * (os tiles do OpenStreetMap são sempre claros). Os marcadores são decorativos (aria-hidden):
 * a informação do mapa está sempre também em texto na página.
 *
 * - Você está aqui: BOLA de 22 px com borda branca; halo da precisão é um L.circle à parte.
 * - Seta de direção: só quando o rumo é conhecido (ver rumo.ts). Sem rumo, só a bola.
 * - Entrada acessível: PINO (gota), para não se confundir com a bola de posição.
 * - Referência do ponto de controle: LOSANGO (estimativa por satélite, nunca a posição medida).
 */

export const TAMANHO_ICONE_POSICAO_PX = 60;
export const TAMANHO_ICONE_PINO_PX = 26;
export const TAMANHO_ICONE_LOSANGO_PX = 26;
/** Alvo de toque dos marcadores de entrada escolhíveis (WCAG 2.5.8 pede 24; o projeto usa 44). */
export const TAMANHO_ALVO_MARCADOR_PX = 44;

/** Rumo em graus ou null. A seta só existe no HTML quando há rumo. */
export function htmlMarcadorPosicao(rumo_graus: number | null): string {
  const seta =
    rumo_graus === null
      ? ""
      : `<span class="mapa-seta" style="transform: rotate(${rumo_graus}deg)"></span>`;
  return `<span class="mapa-posicao" aria-hidden="true">${seta}<span class="mapa-bola"></span></span>`;
}

export function htmlPinoEntradaAcessivel(): string {
  return '<span class="mapa-pino" aria-hidden="true"></span>';
}

/** Referência do ponto de controle: LOSANGO (◆), outra forma que a bola de posição e o pino. */
export function htmlMarcadorReferencia(): string {
  return '<span class="mapa-losango" aria-hidden="true"></span>';
}

/**
 * Entrada escolhível como destino: o pino dentro de um alvo de 44 px. O próprio Leaflet põe nome, papel
 * de botão e foco no elemento do marcador (rota-tela.ts); aqui o HTML interno é só visual (aria-hidden).
 * Escolhida: anel e traço grosso ao redor, para não depender só da cor.
 */
export function htmlAlvoEntrada(escolhida: boolean): string {
  return `<span class="mapa-alvo${escolhida ? " mapa-alvo--escolhido" : ""}" aria-hidden="true">${htmlPinoEntradaAcessivel()}</span>`;
}
