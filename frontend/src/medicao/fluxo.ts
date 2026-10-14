/*
 * Lógica pura do fluxo guiado da medição: "Ponto N de 12 · medição N de 3", barra de 12 segmentos,
 * nível da precisão (palavra e forma, nunca só cor) e contagem de 30 s parado.
 * Sem DOM nem relógio: tudo recebe os dados por parâmetro, para o node:test.
 */
import { MOTIVO_SEM_SINAL, type EstadoEnvio } from "./fila.ts";
import { contarPontoRegistrado, type Registro } from "./medicao.ts";

export const TOTAL_PONTOS = 12;
export const MEDICOES_POR_PONTO = 3;
export const DURACAO_CONTAGEM_S = 30;

/** Limites da classificação da precisão (CLAUDE.md §11 e canvas de 14/10/2026). Provisórios. */
export const LIMITE_PRECISAO_BOA_M = 10;
export const LIMITE_PRECISAO_MEDIA_M = 20;

export type NivelPrecisao = "boa" | "media" | "ruim";

export const ROTULO_NIVEL: Record<NivelPrecisao, { palavra: string; forma: string }> = {
  boa: { palavra: "boa", forma: "●" },
  media: { palavra: "média", forma: "▲" },
  ruim: { palavra: "ruim", forma: "■" },
};

/** <= 10 m boa, <= 20 m média, acima disso ruim. Sem número (ou inválido): null, "sem posição". */
export function classificarPrecisao(precisao_m: number | null): NivelPrecisao | null {
  if (typeof precisao_m !== "number" || !Number.isFinite(precisao_m) || precisao_m < 0) return null;
  if (precisao_m <= LIMITE_PRECISAO_BOA_M) return "boa";
  if (precisao_m <= LIMITE_PRECISAO_MEDIA_M) return "media";
  return "ruim";
}

export function textoPrecisao(precisao_m: number | null): string {
  const nivel = classificarPrecisao(precisao_m);
  if (nivel === null || precisao_m === null) return "Aguardando a posição do GPS";
  const { palavra, forma } = ROTULO_NIVEL[nivel];
  return `${forma} ${palavra}`;
}

export function formatarMetros(precisao_m: number | null): string {
  if (typeof precisao_m !== "number" || !Number.isFinite(precisao_m)) return "– m";
  return `${Math.round(precisao_m)} m`;
}

/** Quantas medições (tipo ponto) este aparelho já fez no ponto. */
export function medicoesFeitas(registros: readonly Registro[], ponto: number, aparelho: string): number {
  return contarPontoRegistrado(registros, ponto, aparelho);
}

/** Número da medição que vem a seguir no ponto (1, 2, 3; 4 em diante é medição extra). */
export function numeroDaProximaMedicao(registros: readonly Registro[], ponto: number, aparelho: string): number {
  return medicoesFeitas(registros, ponto, aparelho) + 1;
}

export function textoMedicao(medicao: number): string {
  return medicao <= MEDICOES_POR_PONTO
    ? `medição ${medicao} de ${MEDICOES_POR_PONTO}`
    : `medição extra (${medicao})`;
}

export interface Segmento {
  ponto: number;
  completo: boolean;
  atual: boolean;
  /** Ficou para trás sem as 3 medições (foi pulado ou ficou pela metade). */
  pulado: boolean;
}

export function segmentosProgresso(registros: readonly Registro[], aparelho: string, pontoAtual: number): Segmento[] {
  return Array.from({ length: TOTAL_PONTOS }, (_, i) => {
    const ponto = i + 1;
    const completo = medicoesFeitas(registros, ponto, aparelho) >= MEDICOES_POR_PONTO;
    return { ponto, completo, atual: ponto === pontoAtual, pulado: !completo && ponto < pontoAtual };
  });
}

export function pontosCompletos(segmentos: readonly Segmento[]): number {
  return segmentos.filter((s) => s.completo).length;
}

/** Texto lido pelo leitor de tela na barra de progresso. */
export function textoProgresso(segmentos: readonly Segmento[]): string {
  const atual = segmentos.find((s) => s.atual);
  const completos = pontosCompletos(segmentos);
  return `${completos} de ${TOTAL_PONTOS} pontos completos` + (atual ? `. Ponto atual: ${atual.ponto}.` : ".");
}

/** Ponto seguinte, ou null depois do último. */
export function proximoPonto(ponto: number): number | null {
  return ponto >= TOTAL_PONTOS ? null : ponto + 1;
}

/** Segundos que faltam na contagem (arredonda para cima, nunca negativo; relógio que voltou = total). */
export function segundosRestantes(inicio_ms: number, agora_ms: number, total_s: number = DURACAO_CONTAGEM_S): number {
  const passou_ms = agora_ms - inicio_ms;
  if (passou_ms < 0) return total_s;
  return Math.max(0, Math.ceil(total_s - passou_ms / 1000));
}

/** Fração (0 a 1) já cumprida da contagem, para a barra. */
export function fracaoContagem(restantes_s: number, total_s: number = DURACAO_CONTAGEM_S): number {
  if (total_s <= 0) return 1;
  return Math.min(1, Math.max(0, (total_s - restantes_s) / total_s));
}

// ---------- etapas: uma por tela ----------

export type Etapa = "preparar" | "medir" | "resultado";

export const ETAPAS: readonly { id: Etapa; titulo: string }[] = [
  { id: "preparar", titulo: "Preparar" },
  { id: "medir", titulo: "Medir o ponto" },
  { id: "resultado", titulo: "Resultado do ponto" },
];

export const TOTAL_ETAPAS = ETAPAS.length;

export function numeroDaEtapa(etapa: Etapa): number {
  return ETAPAS.findIndex((e) => e.id === etapa) + 1;
}

export function textoEtapa(etapa: Etapa): string {
  return `Etapa ${numeroDaEtapa(etapa)} de ${TOTAL_ETAPAS}`;
}

export function tituloEtapa(etapa: Etapa): string {
  return ETAPAS.find((e) => e.id === etapa)?.titulo ?? "";
}

/** Sem aparelho ou sem código da equipe, a medição começa por Preparar; com os dois, volta direto a Medir. */
export function etapaInicial(estado: { temAparelho: boolean; temCodigo: boolean }): Etapa {
  return estado.temAparelho && estado.temCodigo ? "medir" : "preparar";
}

/**
 * Frase falada UMA vez (aria-live) quando a etapa troca. O foco vai para o título da etapa e o leitor
 * de tela já lê "Etapa X de Y, <título>": por isso a frase traz só o que o título não diz.
 */
export function anuncioDaEtapa(etapa: Etapa, ponto: number, medicao: number): string {
  if (etapa === "preparar") return "Preencha o aparelho e o código da equipe. Depois, continue para a medição.";
  if (etapa === "medir") return `Ponto ${ponto} de ${TOTAL_PONTOS}, ${textoMedicao(medicao)}.`;
  return `Ponto ${ponto} registrado, ${textoMedicao(medicao)}.`;
}

/** Falado uma vez depois de confirmar "Recomeçar", junto com a volta à etapa Preparar. */
export const ANUNCIO_RECOMECOU =
  "Recomeçado. Os registros deste aparelho foram apagados e você voltou ao ponto 1. O que já foi enviado ao banco continua lá.";

/**
 * Texto da confirmação do botão "Recomeçar". Recomeçar apaga só o que está NESTE aparelho (a fila de
 * registros) e volta ao ponto 1; o que já foi enviado ao banco continua lá.
 */
export function textoConfirmarRecomecar(total: number, naoEnviados: number): string {
  const servidor = "O que já foi enviado ao banco continua lá: nada é apagado no servidor.";
  if (total === 0) {
    return `Recomeçar volta ao ponto 1. Não há registros guardados neste aparelho. ${servidor}`;
  }
  const guardados =
    total === 1 ? "o 1 registro guardado neste aparelho" : `os ${total} registros guardados neste aparelho`;
  const perdidos =
    naoEnviados === 0
      ? "Todos já foram enviados."
      : naoEnviados === 1
        ? "1 ainda não foi enviado e será perdido."
        : `${naoEnviados} ainda não foram enviados e serão perdidos.`;
  const exportar = naoEnviados > 0 ? " Exporte o CSV antes se quiser guardar os que não foram enviados." : "";
  return (
    `Recomeçar apaga ${guardados} e volta ao ponto 1. ${perdidos} ${servidor}` +
    ` Ficam salvos o aparelho, o código da equipe e a condição.${exportar}`
  );
}

// ---------- como o estado de envio aparece na tela ----------

export type EstadoCartao = "enviado" | "fila" | "recusado";

export interface TextoEnvio {
  cartao: EstadoCartao;
  icone: string;
  /** Título do cartão: "Enviado para a equipe", "Na fila, sem sinal", "Recusado: motivo". */
  titulo: string;
  /** Rótulo curto da lista de últimos registros: "✓ enviado", "◆ na fila", "✕ recusado: motivo". */
  curto: string;
}

/** Palavra, ícone e forma de cada estado (nunca só cor). Contrato: "✓ enviado", "◆ na fila, sem sinal", "✕ recusado: <motivo>". */
export function descreverEnvio(e: {
  estado: EstadoEnvio;
  motivo: string | null;
  temCodigo: boolean;
  online: boolean;
}): TextoEnvio {
  if (e.estado === "enviado") {
    return { cartao: "enviado", icone: "✓", titulo: "Enviado para a equipe", curto: "✓ enviado" };
  }
  if (e.estado === "recusado") {
    const motivo = e.motivo ?? "motivo não informado";
    return { cartao: "recusado", icone: "✕", titulo: `Recusado: ${motivo}`, curto: `✕ recusado: ${motivo}` };
  }
  if (!e.temCodigo) {
    return {
      cartao: "fila",
      icone: "◆",
      titulo: "Não enviado: falta o código da equipe",
      curto: "◆ não enviado: falta o código",
    };
  }
  if (e.motivo === MOTIVO_SEM_SINAL || (!e.online && e.motivo === null)) {
    return { cartao: "fila", icone: "◆", titulo: "Na fila, sem sinal", curto: "◆ na fila, sem sinal" };
  }
  if (e.motivo !== null) {
    return { cartao: "fila", icone: "◆", titulo: `Na fila: ${e.motivo}`, curto: `◆ na fila: ${e.motivo}` };
  }
  return { cartao: "fila", icone: "◆", titulo: "Na fila, enviando", curto: "◆ na fila" };
}
