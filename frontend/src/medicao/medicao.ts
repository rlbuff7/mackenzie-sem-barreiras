/*
 * Lógica pura da página de medição de GPS (CLAUDE.md §11): montagem do registro,
 * CSV, contagem por ponto, limite de 1 posição por segundo e oscilação da bússola.
 * Sem DOM, sem navigator: tudo recebe os dados por parâmetro para poder ser testado
 * no node:test. A tela (pagina.ts) só liga isto às APIs do navegador.
 */

export type TipoRegistro = "ponto" | "trajeto" | "bussola" | "vibracao";
export type Condicao = "ceu_aberto" | "entre_predios" | "coberto";

export const ROTULO_CONDICAO: Record<Condicao, string> = {
  ceu_aberto: "Céu aberto",
  entre_predios: "Entre prédios",
  coberto: "Coberto",
};

/** Registro achatado: uma linha do CSV. Campo que o aparelho não deu fica null (vazio no CSV). */
export interface Registro {
  tipo: TipoRegistro;
  horario_iso: string;
  horario_local: string;
  ponto: number | null;
  aparelho: string;
  condicao: Condicao | null;
  observacao: string;
  latitude: number | null;
  longitude: number | null;
  precisao_m: number | null;
  altitude_m: number | null;
  precisao_altitude_m: number | null;
  velocidade_ms: number | null;
  rumo_graus: number | null;
  bussola_rumo_graus: number | null;
  bussola_oscilacao_graus: number | null;
  bussola_minimo_graus: number | null;
  bussola_maximo_graus: number | null;
  bussola_fonte: string | null;
  vibracao_existe: boolean | null;
  vibracao_retorno: boolean | null;
  user_agent: string;
}

export const CABECALHO_CSV: readonly (keyof Registro)[] = [
  "tipo",
  "horario_iso",
  "horario_local",
  "ponto",
  "aparelho",
  "condicao",
  "observacao",
  "latitude",
  "longitude",
  "precisao_m",
  "altitude_m",
  "precisao_altitude_m",
  "velocidade_ms",
  "rumo_graus",
  "bussola_rumo_graus",
  "bussola_oscilacao_graus",
  "bussola_minimo_graus",
  "bussola_maximo_graus",
  "bussola_fonte",
  "vibracao_existe",
  "vibracao_retorno",
  "user_agent",
];

export interface PosicaoMedida {
  latitude: number;
  longitude: number;
  accuracy: number;
  altitude: number | null;
  altitudeAccuracy: number | null;
  speed: number | null;
  heading: number | null;
}

const pad = (n: number): string => String(n).padStart(2, "0");

export function dataLocal(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function horarioLocal(d: Date): string {
  return `${dataLocal(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** O navegador pode dar NaN em speed/heading; vira "sem valor". */
function numeroOuNulo(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function registroVazio(
  tipo: TipoRegistro,
  aparelho: string,
  userAgent: string,
  agora: Date,
): Registro {
  return {
    tipo,
    horario_iso: agora.toISOString(),
    horario_local: horarioLocal(agora),
    ponto: null,
    aparelho,
    condicao: null,
    observacao: "",
    latitude: null,
    longitude: null,
    precisao_m: null,
    altitude_m: null,
    precisao_altitude_m: null,
    velocidade_ms: null,
    rumo_graus: null,
    bussola_rumo_graus: null,
    bussola_oscilacao_graus: null,
    bussola_minimo_graus: null,
    bussola_maximo_graus: null,
    bussola_fonte: null,
    vibracao_existe: null,
    vibracao_retorno: null,
    user_agent: userAgent,
  };
}

export function montarRegistroPosicao(e: {
  tipo: "ponto" | "trajeto";
  posicao: PosicaoMedida;
  ponto: number | null;
  aparelho: string;
  condicao: Condicao | null;
  observacao: string;
  userAgent: string;
  agora: Date;
}): Registro {
  return {
    ...registroVazio(e.tipo, e.aparelho, e.userAgent, e.agora),
    ponto: e.ponto,
    condicao: e.condicao,
    observacao: e.observacao,
    latitude: numeroOuNulo(e.posicao.latitude),
    longitude: numeroOuNulo(e.posicao.longitude),
    precisao_m: numeroOuNulo(e.posicao.accuracy),
    altitude_m: numeroOuNulo(e.posicao.altitude),
    precisao_altitude_m: numeroOuNulo(e.posicao.altitudeAccuracy),
    velocidade_ms: numeroOuNulo(e.posicao.speed),
    rumo_graus: numeroOuNulo(e.posicao.heading),
  };
}

export interface OscilacaoBussola {
  minimo_graus: number;
  maximo_graus: number;
  oscilacao_graus: number;
  amostras: number;
}

export function montarRegistroBussola(e: {
  rumo_graus: number;
  fonte: string;
  oscilacao: OscilacaoBussola | null;
  aparelho: string;
  userAgent: string;
  agora: Date;
}): Registro {
  return {
    ...registroVazio("bussola", e.aparelho, e.userAgent, e.agora),
    bussola_rumo_graus: e.rumo_graus,
    bussola_fonte: e.fonte,
    bussola_oscilacao_graus: e.oscilacao?.oscilacao_graus ?? null,
    bussola_minimo_graus: e.oscilacao?.minimo_graus ?? null,
    bussola_maximo_graus: e.oscilacao?.maximo_graus ?? null,
  };
}

export function montarRegistroVibracao(e: {
  existe: boolean;
  retorno: boolean | null;
  aparelho: string;
  userAgent: string;
  agora: Date;
}): Registro {
  return {
    ...registroVazio("vibracao", e.aparelho, e.userAgent, e.agora),
    vibracao_existe: e.existe,
    vibracao_retorno: e.retorno,
  };
}

/** Quantas medições de ponto (tipo "ponto") já existem com aquele número, opcionalmente só do aparelho. */
export function contarPontoRegistrado(registros: readonly Registro[], ponto: number, aparelho?: string): number {
  return registros.filter(
    (r) => r.tipo === "ponto" && r.ponto === ponto && (aparelho === undefined || r.aparelho === aparelho),
  ).length;
}

export const INTERVALO_TRAJETO_MS = 1000;

/** No máximo uma posição por segundo. Relógio que voltou não grava. */
export function podeGravarTrajeto(
  ultimoGravado_ms: number | null,
  agora_ms: number,
  intervalo_ms: number = INTERVALO_TRAJETO_MS,
): boolean {
  if (ultimoGravado_ms === null) return true;
  return agora_ms - ultimoGravado_ms >= intervalo_ms;
}

export const JANELA_BUSSOLA_MS = 3000;

const normalizar360 = (g: number): number => ((g % 360) + 360) % 360;

/**
 * Oscilação do rumo nos últimos 3 s. Trabalha em círculo: os desvios são medidos em
 * relação à média circular, então 358, 1 e 4 oscilam 6 graus (não 359). Mínimo e
 * máximo saem em 0 a 360 (o mínimo pode ser maior que o máximo quando a faixa cruza o norte).
 */
export function oscilacaoBussola(
  amostras: readonly { instante_ms: number; rumo_graus: number }[],
  agora_ms: number,
  janela_ms: number = JANELA_BUSSOLA_MS,
): OscilacaoBussola | null {
  const na_janela = amostras.filter((a) => agora_ms - a.instante_ms <= janela_ms && a.instante_ms <= agora_ms);
  if (na_janela.length === 0) return null;
  const rad = (g: number): number => (g * Math.PI) / 180;
  const seno = na_janela.reduce((s, a) => s + Math.sin(rad(a.rumo_graus)), 0);
  const cosseno = na_janela.reduce((s, a) => s + Math.cos(rad(a.rumo_graus)), 0);
  const media_graus = (Math.atan2(seno, cosseno) * 180) / Math.PI;
  const desvios = na_janela.map((a) => {
    const d = normalizar360(a.rumo_graus - media_graus);
    return d > 180 ? d - 360 : d;
  });
  const menor = Math.min(...desvios);
  const maior = Math.max(...desvios);
  const arredonda = (n: number): number => Math.round(n * 100) / 100;
  return {
    minimo_graus: arredonda(normalizar360(media_graus + menor)),
    maximo_graus: arredonda(normalizar360(media_graus + maior)),
    oscilacao_graus: arredonda(maior - menor),
    amostras: na_janela.length,
  };
}

export function escaparCampoCsv(valor: string | number | boolean | null): string {
  if (valor === null) return "";
  const texto = String(valor);
  return /[",\r\n]/.test(texto) ? `"${texto.replaceAll('"', '""')}"` : texto;
}

export function gerarCsv(registros: readonly Registro[]): string {
  const linhas = [CABECALHO_CSV.join(",")];
  for (const r of registros) {
    linhas.push(CABECALHO_CSV.map((c) => escaparCampoCsv(r[c])).join(","));
  }
  return linhas.join("\n") + "\n";
}

export function nomeArquivoCsv(aparelho: string, agora: Date): string {
  const limpo = aparelho
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `medicao-gps-${limpo || "sem-aparelho"}-${dataLocal(agora)}.csv`;
}
