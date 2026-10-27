/*
 * Camada "Já feito" (referência visual): onde a equipe já andou, caminhos da v0 (mapa aberto,
 * provisório) e pontos de controle já medidos. Dados em ja-mapeado.json. Lógica pura.
 * Nada aqui é medição: é só para a equipe saber o que já foi coberto.
 */

export type TipoJaMapeado = "trajeto_equipe" | "caminho_v0" | "ponto_controle";

export interface FeicaoJaMapeado {
  type: "Feature";
  geometry: { type: string; coordinates: unknown };
  properties: { tipo?: string; subtipo?: string; codigo?: string; nome?: string; medicoes?: number };
}

export interface ColecaoJaMapeado {
  type: "FeatureCollection";
  features: FeicaoJaMapeado[];
}

export interface EstiloJaMapeado {
  className: string;
  weight: number;
  dashArray?: string;
  interactive: false;
}

export function filtrarJaMapeado(colecao: ColecaoJaMapeado, tipo: TipoJaMapeado): FeicaoJaMapeado[] {
  return colecao.features.filter((f) => f.properties.tipo === tipo);
}

/** Estilo Leaflet das linhas. Cor e transparência vêm do CSS (className): var() não vale em atributo SVG. */
export function estiloJaMapeado(tipo: string | undefined, subtipo?: string): EstiloJaMapeado {
  if (tipo === "trajeto_equipe") return { className: "mapa-trajeto-equipe", weight: 2, interactive: false };
  if (tipo === "caminho_v0" && subtipo === "escada") {
    return { className: "mapa-caminho-escada", weight: 5, dashArray: "8 6", interactive: false };
  }
  if (tipo === "caminho_v0") return { className: "mapa-caminho-calcada", weight: 4, interactive: false };
  return { className: "", weight: 0, interactive: false };
}

/** Trajeto desta sessão, no aparelho: mesma família do trajeto da equipe, porém sólido e mais forte. */
export const ESTILO_TRAJETO_AO_VIVO: EstiloJaMapeado = {
  className: "mapa-trajeto-vivo",
  weight: 4,
  interactive: false,
};

export function tituloPontoControle(codigo: string, nome: string | undefined, medicoes: number): string {
  const qtd = medicoes === 1 ? "1 medição" : `${medicoes} medições`;
  return [codigo, nome, qtd].filter(Boolean).join(" · ");
}

export interface ItemLegenda {
  amostra: string; // nome da classe da amostra visual
  texto: string;
}

/** Itens da legenda, na ordem de exibição. Cada um tem amostra visual e texto (nada só por cor). */
export const ITENS_LEGENDA: ItemLegenda[] = [
  { amostra: "area", texto: "Amarelo: área sem caminho mapeado" },
  { amostra: "letra", texto: "Letra: prédio sem entrada mapeada" },
  { amostra: "limite", texto: "Linha tracejada fina: limite do campus" },
  { amostra: "equipe", texto: "Linha escura fina: onde a equipe já andou (até 26/10 21:30)" },
  { amostra: "vivo", texto: "Linha escura forte: o seu trajeto agora" },
  { amostra: "calcada", texto: "Linha azul: caminho da v0 (mapa aberto, provisório)" },
  { amostra: "escada", texto: "Laranja tracejado: escada" },
  { amostra: "controle", texto: "Losango vazado: ponto de controle já medido" },
  { amostra: "referencia", texto: "◆ sólido: referência do ponto atual" },
];

const SVG_AMOSTRA: Record<string, string> = {
  area: '<rect x="2" y="4" width="26" height="12" class="mapa-lacuna-area"/>',
  letra: '<text x="15" y="15" text-anchor="middle" font-size="13" font-weight="700" class="legenda__letra">A</text>',
  limite: '<line x1="2" y1="10" x2="28" y2="10" class="mapa-limite-campus" stroke-width="1.5" stroke-dasharray="6 6"/>',
  equipe: '<line x1="2" y1="10" x2="28" y2="10" class="mapa-trajeto-equipe" stroke-width="2"/>',
  vivo: '<line x1="2" y1="10" x2="28" y2="10" class="mapa-trajeto-vivo" stroke-width="4"/>',
  calcada: '<line x1="2" y1="10" x2="28" y2="10" class="mapa-caminho-calcada" stroke-width="4"/>',
  escada: '<line x1="2" y1="10" x2="28" y2="10" class="mapa-caminho-escada" stroke-width="5" stroke-dasharray="8 6"/>',
  controle: '<path d="M15 3 L24 10 L15 17 L6 10 Z" fill="none" class="mapa-controle-losango" stroke-width="2"/>',
  referencia: '<path d="M15 2 L23 10 L15 18 L7 10 Z" class="legenda__referencia"/>',
};

export function htmlAmostra(amostra: string): string {
  return `<svg class="legenda__amostra" width="30" height="20" viewBox="0 0 30 20" aria-hidden="true" focusable="false">${SVG_AMOSTRA[amostra] ?? ""}</svg>`;
}

/** HTML estático (sem entrada de usuário) da lista da legenda. */
export function htmlLegenda(): string {
  return ITENS_LEGENDA.map((i) => `<li class="legenda__item">${htmlAmostra(i.amostra)}<span>${i.texto}</span></li>`).join("");
}
