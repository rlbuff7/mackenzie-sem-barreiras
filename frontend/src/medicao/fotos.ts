/*
 * Foto do ponto de controle (contrato `contrato-fotos.md`, seção "App"). Módulo puro: sem DOM e sem
 * fetch global. A tela (pagina.ts) faz o canvas e o input; aqui ficam as contas e a leitura das
 * respostas da API, para o node:test cobrir.
 */

export const URL_FOTOS = "/api/medicoes/fotos";
export const LADO_MAX_PX = 1280;
/** Acima disso o app comprime de novo (qualidade menor); a API aceita até 1 048 576. */
export const MAX_BYTES_ALVO = 1_000_000;
/** Qualidades tentadas em ordem (toBlob "image/jpeg"). */
export const QUALIDADES_JPEG: readonly number[] = [0.8, 0.6];
export const MAX_APARELHO_FOTO = 80;
export const FRASE_ENQUADRE = "Enquadre só o lugar, sem pessoas.";
export const MOTIVO_SEM_GUARDA = "não foi possível guardar a foto sem sinal";

/** Lado maior <= 1280 px, mantendo a proporção; foto menor não é ampliada. Nunca devolve 0. */
export function dimensoesReduzidas(
  largura_px: number,
  altura_px: number,
  lado_max_px: number = LADO_MAX_PX,
): { largura_px: number; altura_px: number } {
  const l = Math.max(1, Math.round(largura_px));
  const a = Math.max(1, Math.round(altura_px));
  const maior = Math.max(l, a);
  if (maior <= lado_max_px) return { largura_px: l, altura_px: a };
  const k = lado_max_px / maior;
  return { largura_px: Math.max(1, Math.round(l * k)), altura_px: Math.max(1, Math.round(a * k)) };
}

export interface ParametrosFoto {
  id_cliente: string;
  ponto: number;
  aparelho: string;
  tirada_em: string;
  largura_px?: number;
  altura_px?: number;
  observacao?: string;
}

/** URL do POST com a query montada (todos os textos passam por encodeURIComponent). */
export function urlDaFoto(p: ParametrosFoto, base: string = URL_FOTOS): string {
  const q: string[] = [
    `id_cliente=${encodeURIComponent(p.id_cliente)}`,
    `ponto=${encodeURIComponent(String(p.ponto))}`,
    `aparelho=${encodeURIComponent(p.aparelho.trim().slice(0, MAX_APARELHO_FOTO))}`,
    `tirada_em=${encodeURIComponent(p.tirada_em)}`,
  ];
  if (p.largura_px !== undefined) q.push(`largura_px=${encodeURIComponent(String(p.largura_px))}`);
  if (p.altura_px !== undefined) q.push(`altura_px=${encodeURIComponent(String(p.altura_px))}`);
  const obs = p.observacao?.trim();
  if (obs) q.push(`observacao=${encodeURIComponent(obs.slice(0, 500))}`);
  return `${base}?${q.join("&")}`;
}

export type ResultadoFoto =
  | { tipo: "enviada"; repetida: boolean }
  | { tipo: "codigo_errado" }
  | { tipo: "recusada"; motivo: string }
  | { tipo: "fila"; motivo: string };

const corta = (t: string, max: number): string => (t.length > max ? t.slice(0, max) : t);

function mensagemDoCorpo(corpo: unknown): string | null {
  const c = corpo && typeof corpo === "object" ? (corpo as Record<string, unknown>) : null;
  if (!c) return null;
  if (typeof c.mensagem === "string" && c.mensagem.trim()) return corta(c.mensagem.trim(), 200);
  if (typeof c.detail === "string" && c.detail.trim()) return corta(c.detail.trim(), 200);
  return null;
}

/**
 * Lê a resposta do POST. 200 = gravada (ou repetida: o servidor já tinha); 401 = código errado;
 * 413/415/422 = recusada, com motivo; qualquer outra coisa (503, 429, 5xx, resposta estranha) = fica na fila.
 * `status` null = falha de rede.
 */
export function interpretarRespostaFoto(status: number | null, corpo: unknown): ResultadoFoto {
  if (status === null) return { tipo: "fila", motivo: "sem sinal" };
  if (status === 200) {
    const c = corpo && typeof corpo === "object" ? (corpo as Record<string, unknown>) : null;
    if (c && typeof c.gravada === "boolean") return { tipo: "enviada", repetida: !c.gravada };
    return { tipo: "fila", motivo: "resposta inesperada do servidor" };
  }
  if (status === 401) return { tipo: "codigo_errado" };
  if (status === 413) return { tipo: "recusada", motivo: "foto grande demais" };
  if (status === 415) return { tipo: "recusada", motivo: mensagemDoCorpo(corpo) ?? "formato não aceito (só JPEG)" };
  if (status === 422) return { tipo: "recusada", motivo: mensagemDoCorpo(corpo) ?? "dados da foto inválidos" };
  if (status === 503) return { tipo: "fila", motivo: "servidor sem envio ligado" };
  return { tipo: "fila", motivo: `erro ${status} do servidor` };
}

export type EstadoFoto = "enviada" | "na_fila" | "recusada";

/** "Foto do P03: enviada ✓" / "Foto do P03: na fila, sem sinal" / "Foto do P03: recusada: motivo". */
export function textoEstadoFoto(codigoPonto: string, estado: EstadoFoto, motivo: string | null): string {
  const base = `Foto do ${codigoPonto}: `;
  if (estado === "enviada") return `${base}enviada ✓`;
  if (estado === "recusada") return `${base}recusada: ${motivo ?? "motivo não informado"}`;
  return `${base}na fila, ${motivo && motivo !== "sem sinal" ? motivo : "sem sinal"}`;
}

/** Texto alternativo da miniatura. */
export function altDaFoto(codigoPonto: string): string {
  return `Foto do ponto ${codigoPonto}`;
}
