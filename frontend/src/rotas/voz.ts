/**
 * Leitura das instruções em voz (Web Speech API), com o objeto de síntese injetado para poder testar.
 * Nunca fala sozinho, em nenhum perfil: só pelo botão "Ouvir com a voz do app" (opcional). A pessoa cega usa o leitor de tela dela (TalkBack/VoiceOver), com a voz e a velocidade dela.
 * Sem `speechSynthesis`, devolve null e a tela mostra o aviso em texto; nada quebra.
 */

export interface VozDoAparelho {
  lang: string;
  name?: string;
}

export interface FalaDeVoz {
  lang: string;
  voice: unknown;
  rate?: number;
  onend: (() => void) | null;
  onerror: ((evento: { error?: string }) => void) | null;
}

export interface SinteseDeVoz {
  speak(fala: never): void;
  cancel(): void;
  getVoices(): VozDoAparelho[];
  onvoiceschanged?: unknown;
  addEventListener?(tipo: string, ouvinte: () => void): void;
}

export const LINGUA = "pt-BR";
export const AVISO_SEM_VOZ = "Seu navegador não lê em voz alta; use a lista.";
export const AVISO_VOZ_FALHOU = "A voz não conseguiu começar neste aparelho; use a lista.";
export const AVISO_SEM_VOZ_PORTUGUES =
  "Este aparelho não tem voz em português instalada; a leitura pode sair com sotaque estranho. A lista continua valendo.";

const norm = (l: string): string => l.replace("_", "-").toLowerCase();

/** Vozes pt-BR; se não houver nenhuma, pt-PT/pt. Lista vazia se não houver português. */
export function vozesPortuguesas<T extends VozDoAparelho>(vozes: readonly T[]): T[] {
  const br = vozes.filter((v) => norm(v.lang) === "pt-br");
  if (br.length > 0) return br;
  return vozes.filter((v) => norm(v.lang).startsWith("pt"));
}

const MARCAS_NATURAIS = ["natural", "neural", "enhanced", "aprimorad", "premium"];
const NOMES_BONS = ["luciana", "felipe", "francisca", "antonio", "thalita"];

/** Pontuação de qualidade provável: voz neural/natural +3, Google +2, nome conhecido +2, local (offline) +1. */
export function pontuarVoz(voz: VozDoAparelho & { localService?: boolean }): number {
  const nome = (voz.name ?? "").toLowerCase();
  let pontos = 0;
  if (MARCAS_NATURAIS.some((m) => nome.includes(m))) pontos += 3;
  if (nome.includes("google")) pontos += 2;
  if (NOMES_BONS.some((m) => nome.includes(m))) pontos += 2;
  if (voz.localService === true) pontos += 1;
  return pontos;
}

/** Entre as vozes em português, a de maior pontuação; empate: a primeira. Sem português: null. */
export function escolherMelhorVoz<T extends VozDoAparelho & { localService?: boolean }>(vozes: readonly T[]): T | null {
  let melhor: T | null = null;
  let melhorPontos = -1;
  for (const v of vozesPortuguesas(vozes)) {
    const p = pontuarVoz(v);
    if (p > melhorPontos) {
      melhor = v;
      melhorPontos = p;
    }
  }
  return melhor;
}

/** Compatibilidade: mesma escolha automática. */
export function escolherVoz<T extends VozDoAparelho>(vozes: readonly T[]): T | null {
  return escolherMelhorVoz(vozes);
}

export const CHAVE_VOZ = "msb-voz";
export const CHAVE_VELOCIDADE = "msb-voz-velocidade";
export const VELOCIDADES = [0.8, 1, 1.2] as const;

export interface PreferenciasDeVoz {
  /** Nome da voz escolhida; null = automática. */
  nomeVoz: string | null;
  velocidade: number;
}

export function velocidadeValida(v: unknown): number {
  const n = typeof v === "string" ? Number(v.replace(",", ".")) : Number(v);
  return (VELOCIDADES as readonly number[]).includes(n) ? n : 1;
}

interface ArmazemTexto {
  getItem(chave: string): string | null;
  setItem(chave: string, valor: string): void;
  removeItem(chave: string): void;
}

export function lerPreferenciasDeVoz(armazem: ArmazemTexto | null): PreferenciasDeVoz {
  try {
    const nome = armazem?.getItem(CHAVE_VOZ) ?? null;
    return { nomeVoz: nome && nome !== "" ? nome : null, velocidade: velocidadeValida(armazem?.getItem(CHAVE_VELOCIDADE) ?? 1) };
  } catch {
    return { nomeVoz: null, velocidade: 1 };
  }
}

export function guardarPreferenciasDeVoz(armazem: ArmazemTexto | null, prefs: PreferenciasDeVoz): void {
  try {
    if (!armazem) return;
    if (prefs.nomeVoz) armazem.setItem(CHAVE_VOZ, prefs.nomeVoz);
    else armazem.removeItem(CHAVE_VOZ);
    armazem.setItem(CHAVE_VELOCIDADE, String(velocidadeValida(prefs.velocidade)));
  } catch {
    /* sem armazenamento: vale só nesta visita */
  }
}

/** Voz escolhida pelo nome (se ainda existir e for portuguesa); senão a melhor automática. */
export function resolverVoz<T extends VozDoAparelho & { localService?: boolean }>(vozes: readonly T[], nomeVoz: string | null): T | null {
  if (nomeVoz) {
    const achada = vozesPortuguesas(vozes).find((v) => v.name === nomeVoz);
    if (achada) return achada;
  }
  return escolherMelhorVoz(vozes);
}

/** Aviso só quando a lista de vozes já carregou (não vazia) e nenhuma é portuguesa. */
export function avisoDeVoz(vozes: readonly VozDoAparelho[]): string | null {
  return vozes.length > 0 && escolherVoz(vozes) === null ? AVISO_SEM_VOZ_PORTUGUES : null;
}

export interface OpcoesDeFala {
  sintese: SinteseDeVoz | null;
  criarFala: (texto: string) => FalaDeVoz;
  /** Voz e velocidade escolhidas em Ajustes (padrão: automática, 1×). */
  preferencias?: PreferenciasDeVoz;
  /** Chamado uma vez quando a leitura acaba (ou falha, com `falhou`). Não é chamado depois de parar(). */
  aoTerminar?: (falhou: boolean) => void;
}

export interface LeituraEmCurso {
  parar(): void;
}

/** Enfileira uma fala por texto (as chamadas a speak() acontecem juntas, no mesmo toque). */
export function falar(textos: readonly string[], opcoes: OpcoesDeFala): LeituraEmCurso | null {
  const { sintese, criarFala, aoTerminar, preferencias } = opcoes;
  if (!sintese) return null;
  const falas = textos.map((t) => t.trim()).filter((t) => t !== "");
  let encerrada = false;
  const encerrar = (falhou: boolean): void => {
    if (encerrada) return;
    encerrada = true;
    aoTerminar?.(falhou);
  };
  const voz = resolverVoz(sintese.getVoices(), preferencias?.nomeVoz ?? null);
  try {
    sintese.cancel();
    falas.forEach((texto, i) => {
      const fala = criarFala(texto);
      fala.lang = LINGUA;
      if (voz) fala.voice = voz;
      if (preferencias) fala.rate = velocidadeValida(preferencias.velocidade);
      if (i === falas.length - 1) fala.onend = () => encerrar(false);
      fala.onerror = (evento) => {
        // "canceled"/"interrupted" é só o efeito de parar(): não é falha.
        if (evento?.error === "canceled" || evento?.error === "interrupted") return;
        encerrar(true);
      };
      sintese.speak(fala as never);
    });
  } catch {
    encerrar(true);
    return { parar() {} };
  }
  if (falas.length === 0) encerrar(false);
  return {
    parar() {
      encerrada = true;
      try {
        sintese.cancel();
      } catch {
        /* nada a fazer */
      }
    },
  };
}
