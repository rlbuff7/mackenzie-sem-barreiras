/**
 * Escolha de tema (lógica pura, sem DOM global): Automático, Claro, Escuro ou Alto contraste.
 * Automático = sem `data-tema` no <html>, e o tokens.css segue o sistema (prefers-color-scheme
 * e prefers-contrast). Os outros três gravam `data-tema` e vencem o sistema.
 * A escolha fica no localStorage; se ele estiver bloqueado (aba privada), o tema vale só na página.
 */

export const CHAVE_TEMA = "msb-tema";

export type TemaEscolhido = "automatico" | "claro" | "escuro" | "alto-contraste";

export const TEMAS: readonly { valor: TemaEscolhido; rotulo: string }[] = [
  { valor: "automatico", rotulo: "Automático (segue o aparelho)" },
  { valor: "claro", rotulo: "Claro" },
  { valor: "escuro", rotulo: "Escuro" },
  { valor: "alto-contraste", rotulo: "Alto contraste" },
];

export type RaizTema = Pick<Element, "setAttribute" | "removeAttribute">;
export type LeituraArmazenamento = Pick<Storage, "getItem"> | null;
export type EscritaArmazenamento = Pick<Storage, "setItem" | "removeItem"> | null;

export function ehTemaEscolhido(valor: unknown): valor is TemaEscolhido {
  return TEMAS.some((t) => t.valor === valor);
}

/** Valor do atributo `data-tema`; `null` quer dizer "sem atributo" (automático). */
export function temaParaAtributo(tema: TemaEscolhido): string | null {
  return tema === "automatico" ? null : tema;
}

export function aplicarTema(raiz: RaizTema, tema: TemaEscolhido): void {
  const atributo = temaParaAtributo(tema);
  if (atributo === null) raiz.removeAttribute("data-tema");
  else raiz.setAttribute("data-tema", atributo);
}

export function lerTemaSalvo(armazenamento: LeituraArmazenamento): TemaEscolhido {
  try {
    const salvo = armazenamento?.getItem(CHAVE_TEMA);
    return ehTemaEscolhido(salvo) ? salvo : "automatico";
  } catch {
    return "automatico";
  }
}

/** Devolve false se não deu para gravar (sem armazenamento ou bloqueado); nunca lança. */
export function salvarTema(armazenamento: EscritaArmazenamento, tema: TemaEscolhido): boolean {
  if (!armazenamento) return false;
  try {
    if (tema === "automatico") armazenamento.removeItem(CHAVE_TEMA);
    else armazenamento.setItem(CHAVE_TEMA, tema);
    return true;
  } catch {
    return false;
  }
}
