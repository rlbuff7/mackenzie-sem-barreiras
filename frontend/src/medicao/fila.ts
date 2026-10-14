/*
 * Fila de envio em tempo real das medições de GPS (contrato `contrato-medicoes.md`, seção "Celular").
 * Módulo puro: sem DOM, sem relógio global, sem fetch global. O armazenamento, o fetch e o gerador de
 * UUID entram por parâmetro, então o node:test usa um fetch simulado. A tela (pagina.ts) só agenda
 * os reenvios (a cada 10 s, no evento `online`) e desenha os estados.
 *
 * Cada registro ganha um `id_cliente` (UUID) e vira um ItemFila. O servidor trata o mesmo id_cliente
 * como repetido (200 com `repetidas`), então reenviar nunca duplica.
 *
 * Estados por registro:
 *   na_fila  - ainda não confirmado pelo servidor (sem sinal, servidor fora, sem código, aguardando);
 *   enviado  - o servidor respondeu 200 com {gravadas, repetidas};
 *   recusado - 401 (código errado; volta para a fila quando o código muda) ou 422 (campo inválido).
 */
import type { Registro } from "./medicao.ts";

export type EstadoEnvio = "na_fila" | "enviado" | "recusado";

export interface ItemFila {
  id_cliente: string;
  registro: Registro;
  estado: EstadoEnvio;
  /** Para recusado: o motivo. Para na_fila: o último problema do servidor (ex.: medição desligada). */
  motivo: string | null;
  /** Recusado por código errado (401): volta para a fila quando o código da equipe muda. */
  recusado_por_codigo: boolean;
  /** Depois de um 422 sem indicar qual item, os itens vão um por vez para achar o inválido. */
  isolar: boolean;
}

/** Corpo de cada medição, com os nomes exatos do contrato. */
export interface MedicaoApi {
  id_cliente: string;
  tipo: Registro["tipo"];
  medido_em: string;
  aparelho: string;
  ponto?: number;
  condicao?: string;
  latitude?: number;
  longitude?: number;
  precisao_m?: number;
  altitude_m?: number;
  altitude_precisao_m?: number;
  velocidade_ms?: number;
  rumo_gps_graus?: number;
  bussola_graus?: number;
  bussola_fonte?: string;
  bussola_oscilacao_graus?: number;
  vibracao_suportada?: boolean;
  observacao?: string;
  user_agent?: string;
}

export const URL_MEDICOES = "/api/medicoes";
export const CABECALHO_CODIGO = "X-Codigo-Equipe";
export const MAX_ITENS_LOTE = 50;
/** O nginx e a API cortam o corpo em 16 KiB (16384 bytes); o lote para antes disso. */
export const MAX_BYTES_LOTE = 14000;
export const INTERVALO_REENVIO_MS = 10_000;
export const ATRASOS_RECUO_MS: readonly number[] = [5_000, 10_000, 30_000, 60_000];
export const TIMEOUT_ENVIO_MS = 15_000;
export const MAX_APARELHO = 80;
export const MAX_OBSERVACAO = 500;
export const MAX_USER_AGENT = 300;

export const MOTIVO_CODIGO_ERRADO = "código da equipe errado";
export const MOTIVO_DESLIGADA = "medição desligada no servidor";

// ---------- conversão do registro para o corpo da API ----------

const corta = (t: string, max: number): string => (t.length > max ? t.slice(0, max) : t);

function numero(v: number | null): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

/** O banco aceita 0 <= x < 360: 359,999 arredondado para 360 volta a 0. */
function graus360(v: number | null): number | undefined {
  const n = numero(v);
  return n === undefined ? undefined : ((n % 360) + 360) % 360;
}

/** Campo ausente (undefined) sai do JSON; o contrato tem tudo isso como opcional. */
export function paraMedicaoApi(id_cliente: string, r: Registro): MedicaoApi {
  const obs = r.observacao.trim();
  const m: MedicaoApi = {
    id_cliente,
    tipo: r.tipo,
    medido_em: r.horario_iso,
    aparelho: corta(r.aparelho.trim(), MAX_APARELHO),
  };
  const opc: Partial<MedicaoApi> = {
    ponto: r.ponto ?? undefined,
    condicao: r.condicao ?? undefined,
    latitude: numero(r.latitude),
    longitude: numero(r.longitude),
    precisao_m: numero(r.precisao_m),
    altitude_m: numero(r.altitude_m),
    altitude_precisao_m: numero(r.precisao_altitude_m),
    velocidade_ms: numero(r.velocidade_ms),
    rumo_gps_graus: graus360(r.rumo_graus),
    bussola_graus: graus360(r.bussola_rumo_graus),
    bussola_fonte: r.bussola_fonte ?? undefined,
    bussola_oscilacao_graus: numero(r.bussola_oscilacao_graus),
    vibracao_suportada: r.vibracao_existe ?? undefined,
    observacao: obs ? corta(obs, MAX_OBSERVACAO) : undefined,
    user_agent: r.user_agent ? corta(r.user_agent, MAX_USER_AGENT) : undefined,
  };
  for (const [chave, valor] of Object.entries(opc)) {
    if (valor !== undefined) (m as unknown as Record<string, unknown>)[chave] = valor;
  }
  return m;
}

// ---------- UUID ----------

interface Cripto {
  randomUUID?: () => string;
  getRandomValues?: (a: Uint8Array) => Uint8Array;
}

/**
 * crypto.randomUUID() só existe em contexto seguro (HTTPS ou localhost). Em HTTP puro, cai para
 * getRandomValues (UUID v4); sem nenhum dos dois, Math.random (o id só precisa ser único, não secreto).
 */
export function novoUuid(cripto: Cripto | undefined = globalThis.crypto as Cripto | undefined): string {
  if (cripto && typeof cripto.randomUUID === "function") return cripto.randomUUID();
  const b = new Uint8Array(16);
  if (cripto && typeof cripto.getRandomValues === "function") cripto.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// ---------- lote e recuo ----------

const bytesDe = (texto: string): number => new TextEncoder().encode(texto).length;

/**
 * Primeiros itens na fila (na ordem), até `max_itens` e até `max_bytes` de corpo. Item marcado
 * `isolar` vai sozinho. Sempre devolve pelo menos 1 item quando há algum pendente.
 */
export function montarLote(
  pendentes: readonly ItemFila[],
  max_itens: number = MAX_ITENS_LOTE,
  max_bytes: number = MAX_BYTES_LOTE,
): ItemFila[] {
  const primeiro = pendentes[0];
  if (!primeiro) return [];
  if (primeiro.isolar || max_itens <= 1) return [primeiro];
  const lote: ItemFila[] = [];
  let bytes = bytesDe('{"medicoes":[]}');
  for (const item of pendentes) {
    if (item.isolar) break;
    if (lote.length >= max_itens) break;
    const tam = bytesDe(JSON.stringify(paraMedicaoApi(item.id_cliente, item.registro))) + 1;
    if (lote.length > 0 && bytes + tam > max_bytes) break;
    lote.push(item);
    bytes += tam;
  }
  return lote;
}

/** Espera até a próxima tentativa: 10 s sem erro; com erros 5 s, 10 s, 30 s e 60 s (para aí). */
export function atrasoReenvio_ms(falhasSeguidas: number): number {
  if (falhasSeguidas <= 0) return INTERVALO_REENVIO_MS;
  const i = Math.min(falhasSeguidas, ATRASOS_RECUO_MS.length) - 1;
  return ATRASOS_RECUO_MS[i]!;
}

// ---------- 422 ----------

export interface Erros422 {
  /** Motivo por posição do item no lote (loc: ["body","medicoes",<índice>,<campo>...]). */
  porIndice: Map<number, string>;
  /** Motivo quando o servidor não disse qual item. */
  geral: string;
}

/** Lê o corpo de um 422 no formato do FastAPI ({"detail":[{loc, msg}]}); tolera outros formatos. */
export function interpretar422(corpo: unknown): Erros422 {
  const porIndice = new Map<number, string>();
  let geral = "dados recusados pelo servidor (422)";
  const detalhe = corpo && typeof corpo === "object" ? (corpo as { detail?: unknown }).detail : undefined;
  if (typeof detalhe === "string" && detalhe.trim()) geral = corta(detalhe.trim(), 200);
  if (Array.isArray(detalhe)) {
    for (const e of detalhe) {
      if (!e || typeof e !== "object") continue;
      const { loc, msg } = e as { loc?: unknown; msg?: unknown };
      const texto = typeof msg === "string" ? msg : "valor inválido";
      const caminho = Array.isArray(loc) ? loc : [];
      const idx = caminho.findIndex((p) => typeof p === "number");
      const campo = caminho.slice(idx >= 0 ? idx + 1 : 0).filter((p) => p !== "body" && p !== "medicoes");
      const motivo = corta(campo.length ? `campo ${campo.join(".")}: ${texto}` : texto, 200);
      if (idx >= 0) {
        const n = caminho[idx] as number;
        if (!porIndice.has(n)) porIndice.set(n, motivo);
      } else {
        geral = motivo;
      }
    }
  }
  return { porIndice, geral };
}

// ---------- a fila ----------

export interface Armazenamento {
  ler(): string | null;
  gravar(valor: string): void;
}

export interface RespostaMinima {
  status: number;
  json(): Promise<unknown>;
}

export type FetchSimulavel = (
  url: string,
  init: { method: string; headers: Record<string, string>; body: string; signal?: AbortSignal },
) => Promise<RespostaMinima>;

export interface DependenciasFila {
  armazenamento: Armazenamento;
  fetch: FetchSimulavel;
  novoId?: () => string;
  /** Código da equipe atual (lido a cada rodada, pode mudar). Vazio: nada é enviado. */
  codigo: () => string;
  url?: string;
  timeout_ms?: number;
}

export type SituacaoRodada =
  | "nada" //          fila sem pendentes
  | "enviado" //       tudo o que estava pendente foi gravado
  | "sem_codigo" //    sem código da equipe: nada foi tentado
  | "codigo_errado" // 401
  | "desligada" //     503
  | "sem_sinal" //     falha de rede ou tempo esgotado
  | "erro_servidor" // 429, 5xx, resposta inesperada
  | "ocupado"; //      já há um envio em andamento

export interface ResultadoRodada {
  situacao: SituacaoRodada;
  gravadas: number;
  repetidas: number;
  mensagem: string | null;
}

export class FilaEnvio {
  private itensFila: ItemFila[] = [];
  private enviando = false;
  private falhas = 0;
  private maxItens = MAX_ITENS_LOTE;
  private armazenamentoOk = true;

  private readonly dep: DependenciasFila;

  constructor(dep: DependenciasFila) {
    this.dep = dep;
    this.itensFila = this.carregar();
  }

  get itens(): readonly ItemFila[] {
    return this.itensFila;
  }

  get armazenamentoFunciona(): boolean {
    return this.armazenamentoOk;
  }

  get falhasSeguidas(): number {
    return this.falhas;
  }

  get estaEnviando(): boolean {
    return this.enviando;
  }

  /** Espera até a próxima rodada de envio. */
  proximoAtraso_ms(): number {
    return atrasoReenvio_ms(this.falhas);
  }

  /** Todos os registros, enviados ou não, na ordem em que foram feitos (o CSV leva todos). */
  registros(): Registro[] {
    return this.itensFila.map((i) => i.registro);
  }

  contagem(): Record<EstadoEnvio, number> {
    const c: Record<EstadoEnvio, number> = { na_fila: 0, enviado: 0, recusado: 0 };
    for (const i of this.itensFila) c[i.estado] += 1;
    return c;
  }

  pendentes(): ItemFila[] {
    return this.itensFila.filter((i) => i.estado === "na_fila");
  }

  adicionar(registro: Registro): ItemFila {
    const item: ItemFila = {
      id_cliente: (this.dep.novoId ?? novoUuid)(),
      registro,
      estado: "na_fila",
      motivo: null,
      recusado_por_codigo: false,
      isolar: false,
    };
    this.itensFila.push(item);
    this.salvar();
    return item;
  }

  /** Registros de antes da fila (chave antiga do localStorage): entram na fila para não se perderem. */
  importarLegado(registros: readonly Registro[]): void {
    for (const r of registros) {
      this.itensFila.push({
        id_cliente: (this.dep.novoId ?? novoUuid)(),
        registro: r,
        estado: "na_fila",
        motivo: null,
        recusado_por_codigo: false,
        isolar: false,
      });
    }
    this.salvar();
  }

  apagarTudo(): void {
    this.itensFila = [];
    this.falhas = 0;
    this.salvar();
  }

  /** O código mudou: o que foi recusado por código errado volta para a fila, e o recuo zera. */
  reabrirRecusadosPorCodigo(): number {
    let n = 0;
    for (const i of this.itensFila) {
      if (i.estado === "recusado" && i.recusado_por_codigo) {
        i.estado = "na_fila";
        i.motivo = null;
        i.recusado_por_codigo = false;
        n += 1;
      }
    }
    this.falhas = 0;
    if (n > 0) this.salvar();
    return n;
  }

  /** Volta o recuo ao normal (a rede voltou: tenta já). */
  zerarRecuo(): void {
    this.falhas = 0;
  }

  /**
   * Envia tudo o que está pendente, em lotes, até acabar ou até um problema. Nunca roda duas vezes
   * ao mesmo tempo. Não lança erro: o resultado diz o que houve.
   */
  async descarregar(): Promise<ResultadoRodada> {
    if (this.enviando) return { situacao: "ocupado", gravadas: 0, repetidas: 0, mensagem: null };
    const codigo = this.dep.codigo().trim();
    if (!codigo) {
      return { situacao: "sem_codigo", gravadas: 0, repetidas: 0, mensagem: "falta o código da equipe" };
    }
    this.enviando = true;
    let gravadas = 0;
    let repetidas = 0;
    try {
      for (;;) {
        const lote = montarLote(this.pendentes(), this.maxItens);
        if (lote.length === 0) {
          const situacao = gravadas + repetidas > 0 ? "enviado" : "nada";
          return { situacao, gravadas, repetidas, mensagem: null };
        }
        const r = await this.enviarLote(lote, codigo);
        gravadas += r.gravadas;
        repetidas += r.repetidas;
        if (r.situacao !== "continua") {
          return { situacao: r.situacao, gravadas, repetidas, mensagem: r.mensagem };
        }
      }
    } finally {
      this.enviando = false;
    }
  }

  private async enviarLote(
    lote: ItemFila[],
    codigo: string,
  ): Promise<{ situacao: SituacaoRodada | "continua"; gravadas: number; repetidas: number; mensagem: string | null }> {
    const corpo = JSON.stringify({ medicoes: lote.map((i) => paraMedicaoApi(i.id_cliente, i.registro)) });
    const falha = (situacao: SituacaoRodada, mensagem: string | null, motivoItens: string | null) => {
      this.falhas += 1;
      for (const i of lote) i.motivo = motivoItens;
      this.salvar();
      return { situacao, gravadas: 0, repetidas: 0, mensagem };
    };

    let resposta: RespostaMinima;
    const controle = typeof AbortController === "function" ? new AbortController() : null;
    const relogio = controle ? setTimeout(() => controle.abort(), this.dep.timeout_ms ?? TIMEOUT_ENVIO_MS) : null;
    try {
      resposta = await this.dep.fetch(this.dep.url ?? URL_MEDICOES, {
        method: "POST",
        headers: { "Content-Type": "application/json", [CABECALHO_CODIGO]: codigo },
        body: corpo,
        ...(controle ? { signal: controle.signal } : {}),
      });
    } catch {
      return falha("sem_sinal", "sem sinal ou servidor inalcançável", null);
    } finally {
      if (relogio !== null) clearTimeout(relogio);
    }

    const lerJson = async (): Promise<unknown> => {
      try {
        return await resposta.json();
      } catch {
        return null;
      }
    };

    if (resposta.status === 200) {
      const j = (await lerJson()) as { gravadas?: unknown; repetidas?: unknown } | null;
      if (!j || typeof j.gravadas !== "number" || typeof j.repetidas !== "number") {
        // 200 que não é a resposta do contrato (ex.: página de erro de proxy): não conta como enviado.
        return falha("erro_servidor", "resposta inesperada do servidor", "resposta inesperada do servidor");
      }
      for (const i of lote) {
        i.estado = "enviado";
        i.motivo = null;
        i.isolar = false;
      }
      this.falhas = 0;
      this.salvar();
      return { situacao: "continua", gravadas: j.gravadas, repetidas: j.repetidas, mensagem: null };
    }

    if (resposta.status === 401) {
      // O código vale para todos: tudo o que está na fila é recusado até o código mudar.
      for (const i of this.pendentes()) {
        i.estado = "recusado";
        i.motivo = MOTIVO_CODIGO_ERRADO;
        i.recusado_por_codigo = true;
      }
      this.salvar();
      return { situacao: "codigo_errado", gravadas: 0, repetidas: 0, mensagem: MOTIVO_CODIGO_ERRADO };
    }

    if (resposta.status === 422) {
      const erros = interpretar422(await lerJson());
      let recusados = 0;
      lote.forEach((i, n) => {
        const motivo = erros.porIndice.get(n);
        if (motivo !== undefined) {
          i.estado = "recusado";
          i.motivo = motivo;
          recusados += 1;
        }
      });
      if (recusados === 0) {
        if (lote.length === 1) {
          const i = lote[0]!;
          i.estado = "recusado";
          i.motivo = erros.geral;
        } else {
          // O servidor não disse qual item: cada um vai sozinho, e o inválido aparece.
          for (const i of lote) i.isolar = true;
        }
      }
      this.salvar();
      return { situacao: "continua", gravadas: 0, repetidas: 0, mensagem: null };
    }

    if (resposta.status === 413) {
      if (lote.length > 1) {
        this.maxItens = Math.max(1, Math.floor(lote.length / 2));
        return { situacao: "continua", gravadas: 0, repetidas: 0, mensagem: null };
      }
      const i = lote[0]!;
      i.estado = "recusado";
      i.motivo = "registro grande demais para o servidor";
      this.salvar();
      return { situacao: "continua", gravadas: 0, repetidas: 0, mensagem: null };
    }

    if (resposta.status === 503) return falha("desligada", MOTIVO_DESLIGADA, MOTIVO_DESLIGADA);
    return falha("erro_servidor", `erro ${resposta.status} do servidor`, `erro ${resposta.status} do servidor`);
  }

  // ---------- armazenamento ----------

  private salvar(): void {
    try {
      this.dep.armazenamento.gravar(JSON.stringify({ versao: 1, itens: this.itensFila }));
    } catch {
      this.armazenamentoOk = false;
    }
  }

  private carregar(): ItemFila[] {
    try {
      const bruto = this.dep.armazenamento.ler();
      if (!bruto) return [];
      const lido = JSON.parse(bruto) as { itens?: unknown };
      if (!lido || !Array.isArray(lido.itens)) return [];
      return lido.itens.filter(
        (i): i is ItemFila =>
          !!i &&
          typeof i === "object" &&
          typeof (i as ItemFila).id_cliente === "string" &&
          typeof (i as ItemFila).registro === "object" &&
          ["na_fila", "enviado", "recusado"].includes((i as ItemFila).estado),
      );
    } catch {
      this.armazenamentoOk = false;
      return [];
    }
  }
}
