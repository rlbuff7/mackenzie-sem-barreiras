/**
 * Liga a orientação ("Você está em: ...") à página: título, região aria-live única, fala opcional.
 * Objetos injetados (documento, região, síntese) para o node:test; a página real entrega os do navegador.
 *
 * - Troca de tela: título novo; UMA frase na região aria-live (limpa e escreve no quadro seguinte, para
 *   repetir a mesma frase também ser lido). O foco no título da tela é do chamador (ele sabe qual é).
 * - Voz do app ligada: a frase é falada com a voz escolhida em Ajustes e a região fica vazia (leitor de
 *   tela e voz do app falando juntos atropelam um ao outro). Se a fala falhar (por exemplo, o navegador
 *   exige um toque antes), a frase vai para a região.
 * - Nada fala sozinho: a fala começa dentro do toque em "Voz do site" ou, com a voz já ligada, a cada mudança de tela.
 */
import { falar, lerPreferenciasDeVoz, type FalaDeVoz, type LeituraEmCurso, type SinteseDeVoz } from "../rotas/voz.ts";
import {
  guardarVozAtiva,
  lerVozAtiva,
  notaDaVoz,
  NOTA_SEM_VOZ,
  orientacaoDaTela,
  estadoVisualDaVoz,
  tituloDaPagina,
  type Tela,
} from "./orientacao.ts";

export interface DocumentoComTitulo {
  title: string;
}
export interface RegiaoViva {
  textContent: string | null;
}
interface ArmazemTexto {
  getItem(chave: string): string | null;
  setItem(chave: string, valor: string): void;
  removeItem(chave: string): void;
}

export interface DependenciasDaOrientacao {
  documento: DocumentoComTitulo;
  regiao: RegiaoViva;
  sintese: SinteseDeVoz | null;
  criarFala: (texto: string) => FalaDeVoz;
  armazem: ArmazemTexto | null;
  agendar?: (fn: () => void, ms: number) => unknown;
  cancelarAgenda?: (id: unknown) => void;
}

export interface Orientacao {
  /** Põe o título e guarda a tela, sem anunciar (carregamento da página, ou volta silenciosa). */
  definirTela(tela: Tela): void;
  /** Troca de tela: título e anúncio (região aria-live ou voz do app). `anunciar: false` só põe o título. */
  mudarDeTela(tela: Tela, opcoes?: { anunciar?: boolean }): void;
  vozAtiva(): boolean;
  /** Há voz no navegador? Sem ela o botão "Voz do site" não aparece. */
  temVoz(): boolean;
  /** Liga ou desliga a voz (chame dentro do toque). Ao ligar, fala a orientação da tela atual. */
  alternarVoz(): boolean;
}

export function criarOrientacao(deps: DependenciasDaOrientacao): Orientacao {
  const { documento, regiao, sintese, criarFala, armazem } = deps;
  const agendar = deps.agendar ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const cancelarAgenda = deps.cancelarAgenda ?? ((id: unknown) => clearTimeout(id as ReturnType<typeof setTimeout>));
  let ativa = sintese !== null && lerVozAtiva(armazem);
  let atual: Tela | null = null;
  let pendente: unknown = null;
  let leitura: LeituraEmCurso | null = null;

  function cancelarPendente(): void {
    if (pendente !== null) cancelarAgenda(pendente);
    pendente = null;
  }

  function escreverNaRegiao(texto: string): void {
    cancelarPendente();
    regiao.textContent = "";
    pendente = agendar(() => {
      regiao.textContent = texto;
      pendente = null;
    }, 60);
  }

  /** Fala a frase (dentro de um toque ou numa troca de tela). Falha ou sem voz: cai na região aria-live. */
  function falarOuEscrever(texto: string): void {
    cancelarPendente();
    regiao.textContent = "";
    leitura = falar([texto], {
      sintese,
      criarFala,
      preferencias: lerPreferenciasDeVoz(armazem),
      aoTerminar: (falhou) => {
        leitura = null;
        if (falhou) escreverNaRegiao(texto);
      },
    });
    if (leitura === null) escreverNaRegiao(texto);
  }

  return {
    definirTela(tela) {
      atual = tela;
      documento.title = tituloDaPagina(tela.nome);
      cancelarPendente();
      regiao.textContent = "";
    },
    mudarDeTela(tela, opcoes = {}) {
      atual = tela;
      documento.title = tituloDaPagina(tela.nome);
      if (opcoes.anunciar === false) {
        cancelarPendente();
        regiao.textContent = "";
        return;
      }
      const texto = orientacaoDaTela(tela);
      if (ativa && sintese) falarOuEscrever(texto);
      else escreverNaRegiao(texto);
    },
    vozAtiva: () => ativa,
    temVoz: () => sintese !== null,
    alternarVoz() {
      if (!sintese) return false;
      ativa = !ativa;
      guardarVozAtiva(armazem, ativa);
      if (ativa) {
        if (atual) falarOuEscrever(orientacaoDaTela(atual));
      } else {
        leitura?.parar();
        leitura = null;
      }
      return ativa;
    },
  };
}

/** Elementos do botão "Voz do site" e da nota abaixo dele (só o que o código mexe). */
export interface BotaoDeVoz {
  hidden: boolean | string;
  textContent: string | null;
  setAttribute(nome: string, valor: string): void;
  addEventListener(tipo: "click", ouvinte: () => void): void;
}
export interface NotaDeVoz {
  hidden: boolean | string;
  textContent: string | null;
}

/**
 * Mostra o estado da voz no botão (aria-pressed + texto visual do estado, rótulo fixo) e na nota; o clique liga ou desliga.
 * Sem voz no navegador: o botão some e a nota explica.
 */
export function ligarBotaoDeVoz(botao: BotaoDeVoz, nota: NotaDeVoz | null, orientacao: Orientacao, estado: NotaDeVoz | null = null): void {
  const desenhar = (): void => {
    const ativa = orientacao.vozAtiva();
    if (estado) estado.textContent = estadoVisualDaVoz(ativa);
    botao.setAttribute("aria-pressed", String(ativa));
    if (nota) nota.textContent = notaDaVoz(ativa);
  };
  if (!orientacao.temVoz()) {
    botao.hidden = true;
    if (nota) {
      nota.textContent = NOTA_SEM_VOZ;
      nota.hidden = false;
    }
    return;
  }
  desenhar();
  botao.addEventListener("click", () => {
    orientacao.alternarVoz();
    desenhar();
  });
}
