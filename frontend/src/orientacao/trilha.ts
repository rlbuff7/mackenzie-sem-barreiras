/**
 * Trilha e mensagens recentes da orientação ao vivo. Vivem SÓ na memória desta página (RNF04):
 * nada aqui toca em localStorage, IndexedDB, cookie ou console. `limpar()` apaga tudo ao parar.
 *
 * - Trilha: posições anteriores, amostradas a cada ~1,5 s, só as dos últimos JANELA_TRILHA_S segundos, no
 *   máximo MAXIMO_TRILHA. O `ha_segundos` é calculado no envio, em relação à posição enviada.
 * - Recentes: as mensagens que o app já mostrou/falou nesta sessão ({chave, ha_segundos}), no máximo 20,
 *   para o servidor não repetir a mesma frase antes do intervalo.
 * Tempo em milissegundos, sempre passado de fora (testável sem relógio).
 */

/** Janela da trilha: espelha JANELA_TRILHA_SEGUNDOS da API (provisório). */
export const JANELA_TRILHA_S = 15;
export const MAXIMO_TRILHA = 10;
export const INTERVALO_AMOSTRA_TRILHA_MS = 1500;
export const MAXIMO_RECENTES = 20;
/** Maior `chave` aceita pela API (max_length=64). */
export const TAMANHO_MAXIMO_CHAVE = 64;
/** Depois disto a mensagem já não evita repetição (a API usa 20 s; folga larga). */
export const RETENCAO_RECENTES_S = 120;

export interface Fix {
  lat: number;
  lon: number;
  /** Em metros, como o aparelho informa. */
  precisao_m: number;
  /** Quando o app recebeu a posição (Date.now()). */
  instante_ms: number;
}

export interface PontoDaTrilha {
  lat: number;
  lon: number;
  precisao_m: number;
  ha_segundos: number;
}

export interface MensagemRecente {
  chave: string;
  ha_segundos: number;
}

const arredondar1 = (n: number): number => Math.round(n * 10) / 10;
const finito = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

export function fixValido(fix: Fix | null | undefined): fix is Fix {
  return !!fix && finito(fix.lat) && finito(fix.lon) && finito(fix.precisao_m) && finito(fix.instante_ms) &&
    Math.abs(fix.lat) <= 90 && Math.abs(fix.lon) <= 180 && fix.precisao_m >= 0;
}

export class Trilha {
  private pontos: Fix[] = [];

  /** Guarda a posição se já passaram INTERVALO_AMOSTRA_TRILHA_MS da última guardada; poda o que saiu da janela. */
  adicionar(fix: Fix): void {
    if (!fixValido(fix)) return;
    const ultimo = this.pontos[this.pontos.length - 1];
    if (!ultimo || fix.instante_ms - ultimo.instante_ms >= INTERVALO_AMOSTRA_TRILHA_MS) {
      this.pontos.push({ lat: fix.lat, lon: fix.lon, precisao_m: fix.precisao_m, instante_ms: fix.instante_ms });
    }
    this.podar(fix.instante_ms);
  }

  private podar(agora_ms: number): void {
    this.pontos = this.pontos.filter((p) => (agora_ms - p.instante_ms) / 1000 <= JANELA_TRILHA_S);
    if (this.pontos.length > MAXIMO_TRILHA) this.pontos = this.pontos.slice(this.pontos.length - MAXIMO_TRILHA);
  }

  /** Pontos anteriores a `fix` (mais antigo primeiro), com ha_segundos > 0 em relação a ele. Sem pontos: lista vazia. */
  paraEnvio(fix: Fix): PontoDaTrilha[] {
    const saida: PontoDaTrilha[] = [];
    for (const p of this.pontos) {
      const ha = arredondar1((fix.instante_ms - p.instante_ms) / 1000);
      if (ha > 0 && ha <= JANELA_TRILHA_S) {
        saida.push({ lat: p.lat, lon: p.lon, precisao_m: arredondar1(p.precisao_m), ha_segundos: ha });
      }
    }
    return saida.slice(Math.max(0, saida.length - MAXIMO_TRILHA));
  }

  tamanho(): number {
    return this.pontos.length;
  }

  limpar(): void {
    this.pontos = [];
  }
}

export class Recentes {
  private vistas = new Map<string, number>();

  /** Registra que a mensagem de `chave` foi mostrada/falada agora. Chave vazia ou grande demais é ignorada. */
  registrar(chave: string, agora_ms: number): void {
    if (typeof chave !== "string" || chave === "" || chave.length > TAMANHO_MAXIMO_CHAVE || !finito(agora_ms)) return;
    this.vistas.delete(chave);
    this.vistas.set(chave, agora_ms);
  }

  /** Até MAXIMO_RECENTES (as mais novas), com ha_segundos >= 0; some o que passou de RETENCAO_RECENTES_S. */
  paraEnvio(agora_ms: number): MensagemRecente[] {
    for (const [chave, instante] of this.vistas) {
      if ((agora_ms - instante) / 1000 > RETENCAO_RECENTES_S) this.vistas.delete(chave);
    }
    const lista = [...this.vistas].map(([chave, instante]) => ({ chave, ha_segundos: Math.max(0, arredondar1((agora_ms - instante) / 1000)) }));
    return lista.slice(Math.max(0, lista.length - MAXIMO_RECENTES));
  }

  tamanho(): number {
    return this.vistas.size;
  }

  limpar(): void {
    this.vistas.clear();
  }
}
