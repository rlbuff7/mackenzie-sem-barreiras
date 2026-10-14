/**
 * Liga o <select id="seletor-tema"> das páginas ao tema: aplica o salvo, e ao mudar aplica e lembra.
 * A lógica está em tema.ts (com teste); aqui só entra o DOM e o localStorage do navegador.
 */
import { aplicarTema, ehTemaEscolhido, lerTemaSalvo, salvarTema } from "./tema.ts";

function armazenamentoOuNulo(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function iniciarSeletorTema(): void {
  const seletor = document.getElementById("seletor-tema");
  if (!(seletor instanceof HTMLSelectElement)) return;

  const armazenamento = armazenamentoOuNulo();
  const inicial = lerTemaSalvo(armazenamento);
  seletor.value = inicial;
  aplicarTema(document.documentElement, inicial);

  seletor.addEventListener("change", () => {
    if (!ehTemaEscolhido(seletor.value)) return;
    aplicarTema(document.documentElement, seletor.value);
    salvarTema(armazenamento, seletor.value);
  });
}
