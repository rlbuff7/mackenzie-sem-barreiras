/*
 * Fila de fotos (contrato `contrato-fotos.md`). Separada da fila de medições porque o corpo é um
 * JPEG de até ~1 MB (não cabe no localStorage). O armazenamento (IndexedDB na tela), o fetch e o
 * código da equipe entram por parâmetro: o node:test usa um fake. Sem armazenamento (IndexedDB
 * ausente ou com erro), a foto é enviada direto, uma vez; se falhar, não há onde guardar.
 */
import { atrasoReenvio_ms } from "./fila.ts";
import { CABECALHO_CODIGO } from "./fila.ts";
import {
  interpretarRespostaFoto,
  MOTIVO_SEM_GUARDA,
  urlDaFoto,
  type EstadoFoto,
  type ParametrosFoto,
} from "./fotos.ts";

export interface CorpoFoto {
  readonly size: number;
  readonly type: string;
}

export interface ItemFoto extends ParametrosFoto {
  blob: CorpoFoto;
  estado: EstadoFoto;
  motivo: string | null;
  /** Recusada por código errado (401): volta para a fila quando o código muda. */
  recusada_por_codigo: boolean;
}

/** Guarda de itens (IndexedDB na tela). */
export interface ArmazemFotos {
  listar(): Promise<ItemFoto[]>;
  gravar(item: ItemFoto): Promise<void>;
  remover(id_cliente: string): Promise<void>;
}

export interface RespostaFoto {
  status: number;
  json(): Promise<unknown>;
}

export type FetchFoto = (
  url: string,
  init: { method: string; headers: Record<string, string>; body: CorpoFoto; signal?: AbortSignal },
) => Promise<RespostaFoto>;

export interface DependenciasFilaFotos {
  /** null = sem IndexedDB: envio direto. */
  armazem: ArmazemFotos | null;
  fetch: FetchFoto;
  codigo: () => string;
  url?: string;
  timeout_ms?: number;
}

export type ResultadoAdicionar = { guardada: boolean; item: ItemFoto | null; motivo: string | null };

export class FilaFotos {
  private itensFila: ItemFoto[] = [];
  private enviando = false;
  private falhas = 0;
  private armazem: ArmazemFotos | null;
  private readonly dep: DependenciasFilaFotos;

  constructor(dep: DependenciasFilaFotos) {
    this.dep = dep;
    this.armazem = dep.armazem;
  }

  get itens(): readonly ItemFoto[] {
    return this.itensFila;
  }

  get temArmazem(): boolean {
    return this.armazem !== null;
  }

  proximoAtraso_ms(): number {
    return atrasoReenvio_ms(this.falhas);
  }

  zerarRecuo(): void {
    this.falhas = 0;
  }

  pendentes(): ItemFoto[] {
    return this.itensFila.filter((i) => i.estado === "na_fila");
  }

  /** Carrega o que ficou guardado de antes (só o que ainda não foi resolvido). */
  async carregar(): Promise<void> {
    if (!this.armazem) return;
    try {
      const lidos = await this.armazem.listar();
      for (const i of lidos) if (!this.itensFila.some((x) => x.id_cliente === i.id_cliente)) this.itensFila.push(i);
    } catch {
      this.armazem = null;
    }
  }

  /**
   * Guarda e tenta enviar. Com armazém: fica guardada (na fila) mesmo sem sinal. Sem armazém (ou se
   * a gravação falhar): tenta enviar direto; se falhar, devolve guardada=false com o motivo.
   */
  async adicionar(dados: ParametrosFoto, blob: CorpoFoto): Promise<ResultadoAdicionar> {
    const item: ItemFoto = { ...dados, blob, estado: "na_fila", motivo: null, recusada_por_codigo: false };
    let guardada = false;
    if (this.armazem) {
      try {
        await this.armazem.gravar(item);
        guardada = true;
      } catch {
        this.armazem = null;
      }
    }
    this.itensFila.push(item);
    await this.descarregar();
    if (guardada) return { guardada: true, item, motivo: null };
    if (item.estado === "na_fila") {
      // Sem onde guardar e o envio direto não passou: some da fila, a pessoa tira de novo.
      this.itensFila = this.itensFila.filter((i) => i !== item);
      return { guardada: false, item: null, motivo: MOTIVO_SEM_GUARDA };
    }
    return { guardada: false, item, motivo: null };
  }

  /** O código mudou: o que foi recusado por código errado volta para a fila. */
  reabrirRecusadasPorCodigo(): number {
    let n = 0;
    for (const i of this.itensFila) {
      if (i.estado === "recusada" && i.recusada_por_codigo) {
        i.estado = "na_fila";
        i.motivo = null;
        i.recusada_por_codigo = false;
        void this.persistir(i);
        n += 1;
      }
    }
    this.falhas = 0;
    return n;
  }

  /** Envia as pendentes, uma por vez, até acabar ou até um problema de rede/servidor. */
  async descarregar(): Promise<"nada" | "enviado" | "sem_codigo" | "codigo_errado" | "fila" | "ocupado"> {
    if (this.enviando) return "ocupado";
    const codigo = this.dep.codigo().trim();
    if (!codigo) {
      for (const i of this.pendentes()) i.motivo = "falta o código da equipe";
      return "sem_codigo";
    }
    this.enviando = true;
    let mandou = 0;
    try {
      for (;;) {
        const item = this.pendentes()[0];
        if (!item) return mandou > 0 ? "enviado" : "nada";
        const r = await this.enviarUma(item, codigo);
        if (r === "codigo_errado") return "codigo_errado";
        if (r === "fila") return "fila";
        mandou += 1;
      }
    } finally {
      this.enviando = false;
    }
  }

  private async enviarUma(item: ItemFoto, codigo: string): Promise<"ok" | "codigo_errado" | "fila"> {
    const controle = typeof AbortController === "function" ? new AbortController() : null;
    const relogio = controle ? setTimeout(() => controle.abort(), this.dep.timeout_ms ?? 30_000) : null;
    let status: number | null = null;
    let corpo: unknown = null;
    try {
      const r = await this.dep.fetch(urlDaFoto(item, this.dep.url), {
        method: "POST",
        headers: { "Content-Type": "image/jpeg", [CABECALHO_CODIGO]: codigo },
        body: item.blob,
        ...(controle ? { signal: controle.signal } : {}),
      });
      status = r.status;
      try {
        corpo = await r.json();
      } catch {
        corpo = null;
      }
    } catch {
      status = null;
    } finally {
      if (relogio !== null) clearTimeout(relogio);
    }

    const res = interpretarRespostaFoto(status, corpo);
    if (res.tipo === "enviada") {
      item.estado = "enviada";
      item.motivo = null;
      this.falhas = 0;
      await this.apagar(item);
      return "ok";
    }
    if (res.tipo === "recusada") {
      item.estado = "recusada";
      item.motivo = res.motivo;
      await this.apagar(item);
      return "ok";
    }
    if (res.tipo === "codigo_errado") {
      for (const i of this.pendentes()) {
        i.estado = "recusada";
        i.motivo = "código da equipe errado";
        i.recusada_por_codigo = true;
        void this.persistir(i);
      }
      return "codigo_errado";
    }
    item.motivo = res.motivo;
    this.falhas += 1;
    return "fila";
  }

  /** Enviada ou recusada por motivo da foto: não há o que reenviar, sai do armazém. */
  private async apagar(item: ItemFoto): Promise<void> {
    if (!this.armazem) return;
    try {
      await this.armazem.remover(item.id_cliente);
    } catch {
      /* fica lá; o id_cliente evita duplicar se reenviar */
    }
  }

  private async persistir(item: ItemFoto): Promise<void> {
    if (!this.armazem) return;
    try {
      await this.armazem.gravar(item);
    } catch {
      /* segue em memória */
    }
  }
}
