/**
 * Cola da orientação com o navegador, igual nas duas páginas: pega a região aria-live, o botão
 * "Voz do site" e a nota pelos ids, entrega a síntese de voz e o localStorage (com try/catch).
 */
import type { FalaDeVoz, SinteseDeVoz } from "../rotas/voz.ts";
import { criarOrientacao, ligarBotaoDeVoz, type Orientacao } from "./localizacao.ts";

function porId(id: string): HTMLElement {
  const e = document.getElementById(id);
  if (!e) throw new Error(`Falta o elemento #${id} na página`);
  return e;
}

export function iniciarOrientacaoDaPagina(ids: { regiao: string; botao: string; nota: string; estado: string }): Orientacao {
  const sintese =
    typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined"
      ? (window.speechSynthesis as unknown as SinteseDeVoz)
      : null;
  const armazem = ((): Storage | null => {
    try {
      return window.localStorage;
    } catch {
      return null;
    }
  })();
  const orientacao = criarOrientacao({
    documento: document,
    regiao: porId(ids.regiao),
    sintese,
    criarFala: (texto) => new SpeechSynthesisUtterance(texto) as unknown as FalaDeVoz,
    armazem,
    agendar: (fn, ms) => window.setTimeout(fn, ms),
    cancelarAgenda: (id) => window.clearTimeout(id as number),
  });
  ligarBotaoDeVoz(porId(ids.botao) as HTMLButtonElement, porId(ids.nota), orientacao, porId(ids.estado));
  window.addEventListener("pagehide", () => {
    try {
      sintese?.cancel();
    } catch {
      /* nada a fazer */
    }
  });
  return orientacao;
}
