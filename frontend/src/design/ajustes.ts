/**
 * Botão "Ajustes" (tema e "Reduzir animações" ficam dentro do painel). Botão com aria-expanded e
 * aria-controls, painel logo abaixo do topo, sem animação na abertura. O estado aberto/fechado não
 * é guardado: a página começa sempre com o painel fechado. Esc fecha e devolve o foco ao botão.
 */
export function iniciarAjustes(): void {
  const botao = document.getElementById("botao-ajustes");
  const painel = document.getElementById("painel-ajustes");
  if (!(botao instanceof HTMLButtonElement) || !painel) return;

  function definir(aberto: boolean, devolverFoco: boolean): void {
    painel!.hidden = !aberto;
    botao!.setAttribute("aria-expanded", String(aberto));
    if (!aberto && devolverFoco) botao!.focus();
  }

  botao.addEventListener("click", () => definir(Boolean(painel.hidden), false));
  painel.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") definir(false, true);
  });
}
