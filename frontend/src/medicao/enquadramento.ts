/**
 * Quando o código pode mover a vista do mapa da medição. Lógica pura (sem Leaflet, sem DOM).
 *
 * Problema: com a pessoa longe do campus, cada posição do GPS (ou o enquadramento da posição
 * ◆ + halo) puxava o mapa de volta, e ela não conseguia olhar o campus.
 * Regra: depois que a pessoa mexe no mapa (arrastar ou zoom), o código só move a vista por
 * decisão dela ou quando o contexto muda de verdade (outro ponto, outra etapa).
 */

export type MotivoEnquadramento =
  | "inicio" // o mapa acabou de ser criado
  | "ponto" // mudou o ponto de controle: a referência ◆ é outra
  | "etapa" // entrou na etapa Medir (o mapa estava escondido)
  | "primeira_posicao" // chegou o primeiro sinal de GPS
  | "posicao_fora" // a posição saiu da área visível
  | "botao_centralizar" // "Centralizar em mim"
  | "botao_campus"; // "Ver o campus todo"

/** Motivos que sempre movem a vista e devolvem o controle ao código (zeram o estado "solto"). */
const MOTIVOS_QUE_ZERAM: readonly MotivoEnquadramento[] = ["inicio", "ponto", "etapa", "botao_centralizar"];

export function deveReenquadrar(motivo: MotivoEnquadramento, mapaSolto: boolean): boolean {
  if (motivo === "botao_campus") return true;
  if (MOTIVOS_QUE_ZERAM.includes(motivo)) return true;
  return !mapaSolto; // primeira_posicao e posicao_fora respeitam a pessoa
}

/** Estado "solto" depois de um enquadramento feito por este motivo (só vale se ele moveu a vista). */
export function mapaSoltoApos(motivo: MotivoEnquadramento, mapaSolto: boolean): boolean {
  if (motivo === "botao_campus") return true;
  if (MOTIVOS_QUE_ZERAM.includes(motivo)) return false;
  return mapaSolto;
}

/** Só o gesto da pessoa solta o mapa; movimento feito pelo código (flag ligada) não conta. */
export function soltarPorGesto(movendoPorCodigo: boolean, mapaSolto: boolean): boolean {
  return movendoPorCodigo ? mapaSolto : true;
}
