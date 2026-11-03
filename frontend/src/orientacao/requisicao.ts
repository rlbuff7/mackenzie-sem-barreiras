/**
 * Pedido de POST /api/orientacoes (contrato em docs/api.md) e leitura da bússola, sem DOM e sem rede.
 *
 * Regras: campo ausente é OMITIDO (nunca -1, null nem NaN em número); a bússola só vai se for absoluta
 * (aponta para o norte) e estável o bastante para medir a oscilação; a posição só vai para este endereço
 * e não é guardada em lugar nenhum (nem aqui, nem no navegador).
 */
import { oscilacaoBussola } from "../medicao/medicao.ts";
import type { Perfil } from "../rotas/tipos.ts";
import { fixValido, type Fix, type MensagemRecente, type PontoDaTrilha } from "./trilha.ts";

export const URL_ORIENTACOES = "/api/orientacoes";
/** Intervalo entre pedidos (provisório). */
export const INTERVALO_ENVIO_MS = 2500;
/** Posição mais velha que isto não se envia: o GPS sumiu e a última posição já não vale (silêncio). */
export const IDADE_MAXIMA_FIX_MS = 10_000;
/** Janela curta para medir a oscilação da bússola. */
export const JANELA_OSCILACAO_MS = 2000;
/** Menos leituras que isto na janela: oscilação não se mede, a bússola é omitida. */
export const MINIMO_LEITURAS_BUSSOLA = 3;

export interface Bussola {
  rumo_graus: number;
  oscilacao_graus: number;
}

export interface DadosDoPedido {
  origem_id: number;
  destino_id: number;
  perfil: Perfil;
  fix: Fix;
  bussola: Bussola | null;
  trilha: readonly PontoDaTrilha[];
  recentes: readonly MensagemRecente[];
}

const arredondar = (n: number, casas: number): number => {
  const f = 10 ** casas;
  return Math.round(n * f) / f;
};
const finito = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** Corpo do pedido; null se a posição não presta (nesse caso não se envia nada). */
export function montarCorpo(d: DadosDoPedido): Record<string, unknown> | null {
  if (!fixValido(d.fix) || !Number.isInteger(d.origem_id) || !Number.isInteger(d.destino_id)) return null;
  const posicao: Record<string, number> = {
    lat: arredondar(d.fix.lat, 6),
    lon: arredondar(d.fix.lon, 6),
    precisao_m: arredondar(d.fix.precisao_m, 1),
  };
  const b = d.bussola;
  if (b && finito(b.rumo_graus) && finito(b.oscilacao_graus) && b.oscilacao_graus >= 0 && b.oscilacao_graus <= 360) {
    posicao.rumo_bussola_graus = arredondar(((b.rumo_graus % 360) + 360) % 360, 1);
    posicao.rumo_bussola_oscilacao_graus = arredondar(b.oscilacao_graus, 1);
  }
  const corpo: Record<string, unknown> = { origem_id: d.origem_id, destino_id: d.destino_id, perfil: d.perfil, posicao };
  const trilha = d.trilha.filter((p) => finito(p.lat) && finito(p.lon) && finito(p.precisao_m) && finito(p.ha_segundos) && p.ha_segundos > 0 && p.precisao_m >= 0);
  if (trilha.length > 0) {
    corpo.trilha = trilha.map((p) => ({ lat: arredondar(p.lat, 6), lon: arredondar(p.lon, 6), precisao_m: arredondar(p.precisao_m, 1), ha_segundos: p.ha_segundos }));
  }
  const recentes = d.recentes.filter((r) => typeof r.chave === "string" && r.chave !== "" && finito(r.ha_segundos) && r.ha_segundos >= 0);
  if (recentes.length > 0) corpo.recentes = recentes.map((r) => ({ chave: r.chave, ha_segundos: r.ha_segundos }));
  return corpo;
}

export interface RequisicaoHttp {
  url: string;
  init: { method: "POST"; headers: Record<string, string>; body: string };
}

export function montarRequisicao(d: DadosDoPedido): RequisicaoHttp | null {
  const corpo = montarCorpo(d);
  if (!corpo) return null;
  return { url: URL_ORIENTACOES, init: { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) } };
}

/** Hora de mandar outro pedido? Só com posição recente, nenhum pedido em voo e o intervalo cumprido. */
export function deveEnviar(e: { agora_ms: number; ultimoEnvio_ms: number | null; emVoo: boolean; fix: Fix | null }): boolean {
  if (e.emVoo || !fixValido(e.fix)) return false;
  if (e.agora_ms - e.fix.instante_ms > IDADE_MAXIMA_FIX_MS) return false;
  return e.ultimoEnvio_ms === null || e.agora_ms - e.ultimoEnvio_ms >= INTERVALO_ENVIO_MS;
}

/** A posição está velha demais para valer (GPS sumiu)? */
export function gpsPerdido(fix: Fix | null, agora_ms: number): boolean {
  return !fixValido(fix) || agora_ms - fix.instante_ms > IDADE_MAXIMA_FIX_MS;
}

// ---------- bússola ----------

export interface EventoDeOrientacao {
  webkitCompassHeading?: number | null;
  alpha?: number | null;
  absolute?: boolean | null;
}

export interface LeituraDeBussola {
  rumo_graus: number;
  fonte: "webkitCompassHeading" | "alpha_absoluto";
}

const normalizar360 = (g: number): number => ((g % 360) + 360) % 360;

/**
 * iPhone: webkitCompassHeading (já em relação ao norte). Android: alpha só quando `absolute` (evento
 * deviceorientationabsolute); alpha relativo NÃO aponta para o norte e é descartado (silêncio, nunca palpite).
 */
export function lerEventoDeOrientacao(ev: EventoDeOrientacao): LeituraDeBussola | null {
  if (finito(ev.webkitCompassHeading)) return { rumo_graus: normalizar360(ev.webkitCompassHeading), fonte: "webkitCompassHeading" };
  if (finito(ev.alpha) && ev.absolute === true) return { rumo_graus: normalizar360(360 - ev.alpha), fonte: "alpha_absoluto" };
  return null;
}

/** Leituras recentes da bússola (só na memória). */
export class JanelaDeBussola {
  private amostras: { instante_ms: number; rumo_graus: number }[] = [];

  adicionar(rumo_graus: number, instante_ms: number): void {
    if (!finito(rumo_graus) || !finito(instante_ms)) return;
    this.amostras.push({ instante_ms, rumo_graus: normalizar360(rumo_graus) });
    this.amostras = this.amostras.filter((a) => instante_ms - a.instante_ms <= JANELA_OSCILACAO_MS);
  }

  /** Rumo médio (circular) e oscilação nos últimos ~2 s; null se há leituras de menos para medir. */
  resumo(agora_ms: number): Bussola | null {
    const recentes = this.amostras.filter((a) => agora_ms - a.instante_ms <= JANELA_OSCILACAO_MS && a.instante_ms <= agora_ms);
    if (recentes.length < MINIMO_LEITURAS_BUSSOLA) return null;
    const osc = oscilacaoBussola(recentes, agora_ms, JANELA_OSCILACAO_MS);
    if (!osc) return null;
    const rad = (g: number): number => (g * Math.PI) / 180;
    const seno = recentes.reduce((s, a) => s + Math.sin(rad(a.rumo_graus)), 0);
    const cosseno = recentes.reduce((s, a) => s + Math.cos(rad(a.rumo_graus)), 0);
    const media = normalizar360((Math.atan2(seno, cosseno) * 180) / Math.PI);
    return { rumo_graus: arredondar(media, 1), oscilacao_graus: osc.oscilacao_graus };
  }

  limpar(): void {
    this.amostras = [];
  }
}
