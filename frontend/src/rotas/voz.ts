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
  onend: (() => void) | null;
  onerror: ((evento: { error?: string }) => void) | null;
}

export interface SinteseDeVoz {
  speak(fala: never): void;
  cancel(): void;
  getVoices(): VozDoAparelho[];
}

export const LINGUA = "pt-BR";
export const AVISO_SEM_VOZ = "Seu navegador não lê em voz alta; use a lista.";
export const AVISO_VOZ_FALHOU = "A voz não conseguiu começar neste aparelho; use a lista.";
export const AVISO_SEM_VOZ_PORTUGUES =
  "Este aparelho não tem voz em português instalada; a leitura pode sair com sotaque estranho. A lista continua valendo.";

/** Prefere pt-BR; aceita outra variante de português; senão null (a fala ainda leva lang = pt-BR). */
export function escolherVoz<T extends VozDoAparelho>(vozes: readonly T[]): T | null {
  const norm = (l: string): string => l.replace("_", "-").toLowerCase();
  return vozes.find((v) => norm(v.lang) === "pt-br") ?? vozes.find((v) => norm(v.lang).startsWith("pt")) ?? null;
}

/** Aviso só quando a lista de vozes já carregou (não vazia) e nenhuma é portuguesa. */
export function avisoDeVoz(vozes: readonly VozDoAparelho[]): string | null {
  return vozes.length > 0 && escolherVoz(vozes) === null ? AVISO_SEM_VOZ_PORTUGUES : null;
}

export interface OpcoesDeFala {
  sintese: SinteseDeVoz | null;
  criarFala: (texto: string) => FalaDeVoz;
  /** Chamado uma vez quando a leitura acaba (ou falha, com `falhou`). Não é chamado depois de parar(). */
  aoTerminar?: (falhou: boolean) => void;
}

export interface LeituraEmCurso {
  parar(): void;
}

/** Enfileira uma fala por texto (as chamadas a speak() acontecem juntas, no mesmo toque). */
export function falar(textos: readonly string[], opcoes: OpcoesDeFala): LeituraEmCurso | null {
  const { sintese, criarFala, aoTerminar } = opcoes;
  if (!sintese) return null;
  const falas = textos.map((t) => t.trim()).filter((t) => t !== "");
  let encerrada = false;
  const encerrar = (falhou: boolean): void => {
    if (encerrada) return;
    encerrada = true;
    aoTerminar?.(falhou);
  };
  const voz = escolherVoz(sintese.getVoices());
  try {
    sintese.cancel();
    falas.forEach((texto, i) => {
      const fala = criarFala(texto);
      fala.lang = LINGUA;
      if (voz) fala.voice = voz;
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
