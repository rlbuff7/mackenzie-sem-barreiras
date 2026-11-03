/**
 * O mapa Leaflet é referência visual (tudo o que ele mostra também está em texto), então:
 * - o contêiner não entra na ordem de foco nem captura as setas (`keyboard: false`): para o leitor
 *   de tela não haveria nada a fazer ali, e quem enxerga usa os botões de zoom, que continuam focáveis;
 * - os botões de zoom e a atribuição têm nome em português (o padrão do Leaflet é em inglês);
 * - o contêiner no HTML é `role="region"` com `aria-label` descritivo.
 */
export const OPCOES_DE_FOCO_DO_MAPA = { keyboard: false } as const;

export const OPCOES_DO_ZOOM = {
  zoomInTitle: "Aproximar o mapa",
  zoomOutTitle: "Afastar o mapa",
} as const;

/** Prefixo da atribuição (o link "Leaflet"), com o título em português. */
export const PREFIXO_DA_ATRIBUICAO = '<a href="https://leafletjs.com" title="Biblioteca de mapas Leaflet">Leaflet</a>';
