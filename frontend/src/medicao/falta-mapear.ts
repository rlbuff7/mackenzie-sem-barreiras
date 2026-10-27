/*
 * Camada "Falta mapear" (referência visual): áreas do campus sem caminho mapeado, limite do campus
 * e prédios sem entrada mapeada. Dados em falta-mapear.json (OpenStreetMap, ODbL). Lógica pura.
 */

export type TipoCamada = "falta_mapear" | "limite_campus" | "predio_sem_entrada";

export interface FeicaoCamada {
  type: "Feature";
  geometry: { type: string; coordinates: unknown };
  properties: { tipo?: string; letra?: string; nome?: string; descricao?: string };
}

export interface ColecaoCamada {
  type: "FeatureCollection";
  features: FeicaoCamada[];
}

export interface EstiloLinha {
  stroke?: boolean;
  fill?: boolean;
  className?: string;
  fillOpacity?: number;
  color?: string;
  weight?: number;
  opacity?: number;
  dashArray?: string;
  interactive: false;
}

/** Só as feições do tipo pedido. */
export function filtrarPorTipo(colecao: ColecaoCamada, tipo: TipoCamada): FeicaoCamada[] {
  return colecao.features.filter((f) => f.properties.tipo === tipo);
}

/** Estilo Leaflet por tipo (cores só por tokens; `interactive: false` para não roubar o toque). */
export function estiloDaFeicao(tipo: string | undefined): EstiloLinha {
  if (tipo === "falta_mapear") {
    // A cor vem do token --mapa-lacuna via CSS (.mapa-lacuna-area): var() não vale em atributo SVG.
    return { stroke: false, fill: true, fillOpacity: 1, className: "mapa-lacuna-area", interactive: false };
  }
  if (tipo === "limite_campus") {
    return { fill: false, weight: 1.5, opacity: 0.8, dashArray: "6 6", className: "mapa-limite-campus", interactive: false };
  }
  return { stroke: false, fill: false, interactive: false };
}

export function tituloDoPredio(letra: string, nome: string | undefined): string {
  return nome ? `Prédio ${letra} (${nome}): sem entrada mapeada` : `Prédio ${letra}: sem entrada mapeada`;
}

export function htmlLetraPredio(letra: string): string {
  return `<span class="mapa-letra" aria-hidden="true">${letra.replace(/[^A-Za-z]/g, "").slice(0, 1)}</span>`;
}

export const TEXTO_LEGENDA_FALTA_MAPEAR =
  "Amarelo: área sem caminho mapeado. Letra: prédio sem entrada mapeada. Ande por lá com Iniciar trajeto ligado.";
