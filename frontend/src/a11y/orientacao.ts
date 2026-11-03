/**
 * Onde a pessoa está no sistema: título da página, frase "Você está em: ..." e a preferência da voz do app.
 * Lógica sem DOM (o node:test roda com objetos de mentira); a ligação com a página fica em localizacao.ts.
 *
 * Decisão de 27/10/2026 (orientadora + Rodrigo): a mudança de tela é ANUNCIADA ao leitor de tela
 * (região aria-live), nunca falada sozinha: o navegador bloqueia fala sem gesto e áudio automático
 * atropela o leitor de tela (WCAG 1.4.2). Quem não usa leitor de tela toca em "Ativar voz" e, dali em
 * diante, o app fala a orientação a cada mudança de tela, com a voz escolhida em Ajustes.
 */

export const NOME_DO_APP = "Navegação Acessível no Campus";

/** Chave da preferência "falar a orientação a cada tela" (localStorage; sem ela vale só nesta visita). */
export const CHAVE_VOZ_ATIVA = "msb-voz-ativa";

export interface Tela {
  /** Nome curto da tela, que vai no título da página e na frase "Você está em". */
  nome: string;
  /** Próxima ação, em uma frase curta. */
  acao: string;
}

/** "Rota traçada · Navegação Acessível no Campus". */
export function tituloDaPagina(nomeDaTela: string): string {
  return `${nomeDaTela} · ${NOME_DO_APP}`;
}

/** "Você está em: Rota traçada. Cerca de 182 metros." (texto curto: o foco já leu o título da tela). */
export function anuncioDeLocalizacao(nomeDaTela: string, acao: string): string {
  const nome = nomeDaTela.trim().replace(/[.:]+$/, "");
  return `Você está em: ${nome}. ${acao.trim()}`.trim();
}

export function orientacaoDaTela(tela: Tela): string {
  return anuncioDeLocalizacao(tela.nome, tela.acao);
}

/** Rótulo FIXO do botão (prática do ARIA: o estado vai em aria-pressed, o texto não muda). */
export const ROTULO_DO_BOTAO_DE_VOZ = "Voz do site";

/** Texto visual do estado, ao lado do rótulo (aria-hidden: o leitor de tela já lê o aria-pressed). */
export function estadoVisualDaVoz(ativa: boolean): string {
  return ativa ? "Ligada" : "Desligada";
}

export const NOTA_VOZ_DESLIGADA =
  "Para quem não usa leitor de tela: toque para o app falar onde você está a cada tela.";
export const NOTA_VOZ_LIGADA = "Voz ligada: o app fala onde você está a cada tela. Toque de novo para desligar.";
export const NOTA_SEM_VOZ =
  "Este navegador não fala em voz alta. Quem usa leitor de tela continua sendo avisado a cada tela.";

export function notaDaVoz(ativa: boolean): string {
  return ativa ? NOTA_VOZ_LIGADA : NOTA_VOZ_DESLIGADA;
}

interface ArmazemTexto {
  getItem(chave: string): string | null;
  setItem(chave: string, valor: string): void;
  removeItem(chave: string): void;
}

/** Só o valor "1" liga. Sem armazenamento, valor estranho ou erro ao ler: desligada. */
export function lerVozAtiva(armazem: ArmazemTexto | null): boolean {
  try {
    return armazem?.getItem(CHAVE_VOZ_ATIVA) === "1";
  } catch {
    return false;
  }
}

export function guardarVozAtiva(armazem: ArmazemTexto | null, ativa: boolean): void {
  try {
    if (!armazem) return;
    if (ativa) armazem.setItem(CHAVE_VOZ_ATIVA, "1");
    else armazem.removeItem(CHAVE_VOZ_ATIVA);
  } catch {
    /* sem armazenamento: vale só nesta visita */
  }
}
