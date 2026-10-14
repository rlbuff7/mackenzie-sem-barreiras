/**
 * Liga o interruptor `#interruptor-movimento` ("Reduzir animações") ao movimento: aplica o salvo,
 * e ao mudar aplica e lembra. A lógica está em movimento.ts (com teste); aqui só entram o DOM,
 * o localStorage e o `prefers-reduced-motion` do navegador.
 * Se o aparelho já pede menos movimento, o interruptor aparece ligado e travado (aria-disabled, sem
 * `disabled`, para continuar no Tab e o leitor de tela ler a nota): desligá-lo não traria o
 * movimento de volta (o aparelho vence), então não finge que daria.
 */
import { aplicarMovimento, lerMovimentoSalvo, movimentoReduzido, salvarMovimento } from "./movimento.ts";

function armazenamentoOuNulo(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function iniciarInterruptorMovimento(): void {
  const encontrado = document.getElementById("interruptor-movimento");
  if (!(encontrado instanceof HTMLInputElement)) return;
  const interruptor: HTMLInputElement = encontrado;
  const nota = document.getElementById("nota-movimento");

  const armazenamento = armazenamentoOuNulo();
  const consulta = window.matchMedia("(prefers-reduced-motion: reduce)");
  let preferencia = lerMovimentoSalvo(armazenamento);
  aplicarMovimento(document.documentElement, preferencia);

  function desenhar(): void {
    const aparelho = consulta.matches;
    interruptor.checked = movimentoReduzido(preferencia, aparelho);
    interruptor.setAttribute("aria-disabled", String(aparelho));
    if (nota) nota.hidden = !aparelho;
  }

  interruptor.addEventListener("click", (evento) => {
    if (consulta.matches) evento.preventDefault(); // o aparelho vence: o clique não muda nada
  });
  interruptor.addEventListener("change", () => {
    preferencia = interruptor.checked ? "reduzido" : "padrao";
    aplicarMovimento(document.documentElement, preferencia);
    salvarMovimento(armazenamento, preferencia);
  });
  consulta.addEventListener("change", desenhar);
  desenhar();
}
