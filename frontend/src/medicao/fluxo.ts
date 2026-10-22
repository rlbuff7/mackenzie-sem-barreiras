/*
 * Lógica pura do fluxo guiado da medição: "Ponto N de 10 · medição N de 3", barra de 10 segmentos,
 * nível da precisão (palavra e forma, nunca só cor) e contagem de 30 s parado.
 * Sem DOM nem relógio: tudo recebe os dados por parâmetro, para o node:test.
 */
import { MOTIVO_SEM_SINAL, type EstadoEnvio } from "./fila.ts";
import { contarPontoRegistrado, type Registro } from "./medicao.ts";
import { PONTOS_CONTROLE } from "./pontos-controle.ts";

export const TOTAL_PONTOS = PONTOS_CONTROLE.length;
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

function registrosEsperando(n: number): string {
  return n === 1 ? "1 registro ainda espera internet" : `${n} registros ainda esperam internet`;
}

/** Falado uma vez depois de confirmar "Recomeçar", junto com a volta à etapa Preparar. */
export function anuncioRecomecou(esperando: number): string {
  const fila =
    esperando > 0
      ? ` ${registrosEsperando(esperando)} e ${esperando === 1 ? "será enviado" : "serão enviados"} sozinho${esperando === 1 ? "" : "s"}.`
      : "";
  return `Recomeçado. Você voltou ao ponto 1.${fila} O que já foi enviado ao banco continua lá.`;
}

/**
 * Registros da rodada atual: os feitos desde o último "Recomeçar" (`desde_iso`, null = todos). Os que
 * ficaram esperando envio de antes do recomeço continuam na fila, mas não contam no ponto N de 10.
 */
export function registrosDaRodada(registros: readonly Registro[], desde_iso: string | null): Registro[] {
  if (!desde_iso) return [...registros];
  return registros.filter((r) => r.horario_iso >= desde_iso);
}

/**
 * Texto da confirmação do botão "Recomeçar". Recomeçar volta ao ponto 1 e zera a contagem de pontos;
 * NÃO apaga o que ainda não foi enviado: esses registros continuam na fila e saem sozinhos quando
 * houver internet. O que já foi enviado continua no banco (nada é apagado no servidor).
 * `esperando` = registros ainda na fila de envio.
 */
export function textoConfirmarRecomecar(esperando: number): string {
  const inicio = "Recomeçar volta ao ponto 1 e zera a contagem de pontos.";
  const fila =
    esperando > 0
      ? ` ${registrosEsperando(esperando)} e ${esperando === 1 ? "CONTINUA" : "CONTINUAM"} neste aparelho: ${esperando === 1 ? "será enviado" : "serão enviados"} sozinho${esperando === 1 ? "" : "s"} quando houver sinal.`
      : "";
  return (
    `${inicio}${fila} O que já foi enviado ao banco continua lá: nada é apagado no servidor.` +
    " Ficam salvos o aparelho, o código da equipe e a condição."
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

// ---------- aviso do trajeto ----------

/** "1 posição" / "12 posições". */
export function textoPosicoes(n: number): string {
  return n === 1 ? "1 posição" : `${n} posições`;
}

/** Texto VISÍVEL da faixa do trajeto: muda a cada posição gravada. */
export function textoTrajeto(gravadas: number, precisao_m: number | null): string {
  return `Trajeto gravando: ${textoPosicoes(gravadas)}, precisão ${formatarMetros(precisao_m)}.`;
}

/** O leitor de tela só fala na 1ª posição e a cada 10 (o texto visível muda sempre). */
export function deveAnunciarTrajeto(gravadas: number): boolean {
  return gravadas === 1 || (gravadas > 0 && gravadas % 10 === 0);
}
