/**
 * Preferência de movimento (lógica pura, sem DOM global): o interruptor "Reduzir animações".
 * Ligado grava `data-movimento="reduzido"` no <html>; o movimento.css desliga todo deslocamento,
 * toda transição e a troca animada entre páginas quando esse atributo existe. Desligado = sem
 * atributo: o movimento só vale se o aparelho NÃO pedir `prefers-reduced-motion: reduce`.
 * A escolha fica no localStorage; se ele estiver bloqueado (aba privada), vale só na página.
 */

export const CHAVE_MOVIMENTO = "msb-movimento";

export type PreferenciaMovimento = "padrao" | "reduzido";

export type RaizMovimento = Pick<Element, "setAttribute" | "removeAttribute">;
export type LeituraArmazenamento = Pick<Storage, "getItem"> | null;
export type EscritaArmazenamento = Pick<Storage, "setItem" | "removeItem"> | null;

export function aplicarMovimento(raiz: RaizMovimento, preferencia: PreferenciaMovimento): void {
  if (preferencia === "reduzido") raiz.setAttribute("data-movimento", "reduzido");
  else raiz.removeAttribute("data-movimento");
}

export function lerMovimentoSalvo(armazenamento: LeituraArmazenamento): PreferenciaMovimento {
  try {
    return armazenamento?.getItem(CHAVE_MOVIMENTO) === "reduzido" ? "reduzido" : "padrao";
  } catch {
    return "padrao";
  }
}

/** Devolve false se não deu para gravar (sem armazenamento ou bloqueado); nunca lança. */
export function salvarMovimento(armazenamento: EscritaArmazenamento, preferencia: PreferenciaMovimento): boolean {
  if (!armazenamento) return false;
  try {
    if (preferencia === "reduzido") armazenamento.setItem(CHAVE_MOVIMENTO, "reduzido");
    else armazenamento.removeItem(CHAVE_MOVIMENTO);
    return true;
  } catch {
    return false;
  }
}

/** Movimento fica desligado se a pessoa ligou o interruptor OU se o aparelho pede menos movimento. */
export function movimentoReduzido(preferencia: PreferenciaMovimento, aparelhoPedeReduzir: boolean): boolean {
  return preferencia === "reduzido" || aparelhoPedeReduzir;
}
