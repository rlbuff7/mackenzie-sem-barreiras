/**
 * Textos da rota, escritos para serem lidos em voz: "metros" por extenso, sem símbolo, sem coordenada.
 * Nada aqui inventa orientação: as instruções vêm prontas da API.
 */
import { anuncioDeLocalizacao } from "../a11y/orientacao.ts";
import type { RotaResposta } from "./tipos.ts";

export const NOME_TELA_ROTA = "Rota traçada";

/** "182 metros", "1 metro", "menos de 1 metro". Sem separador de milhar, para a voz não ler "ponto". */
export function textoDistancia(distancia_m: number): string {
  const arredondada = Math.round(distancia_m);
  if (arredondada < 1) return "menos de 1 metro";
  return arredondada === 1 ? "1 metro" : `${arredondada} metros`;
}

export function textoDistanciaTotal(distancia_m: number): string {
  return `Distância total: ${textoDistancia(distancia_m)}.`;
}

export function tituloDoResultado(rota: Pick<RotaResposta, "origem" | "destino">): string {
  return `Rota de ${rota.origem.nome} até ${rota.destino.nome}`;
}

/** Frase curta da próxima ação na tela "Rota traçada" (o foco vai para o título; avisos e instruções vêm na ordem do HTML). */
export function resumoDaRota(rota: Pick<RotaResposta, "avisos" | "distancia_m">): string {
  const n = rota.avisos.length;
  const avisos = n === 0 ? "sem avisos" : n === 1 ? "1 aviso" : `${n} avisos`;
  return `Cerca de ${textoDistancia(rota.distancia_m)}, ${avisos}. As instruções vêm a seguir.`;
}

/** O que a região aria-live (ou a voz do app) diz quando a rota aparece: "Você está em: Rota traçada. Cerca de ...". */
export function anuncioDaRota(rota: Pick<RotaResposta, "avisos" | "distancia_m">): string {
  return anuncioDeLocalizacao(NOME_TELA_ROTA, resumoDaRota(rota));
}

const ABERTURA_PROVISORIA = "Trecho provisório de demonstração.";

/**
 * O que a voz fala, uma frase por item (uma fala por instrução). Começa pelo aviso de segurança
 * (com o aviso de trecho provisório na frente, quando for o caso), diz que é demonstração, lê os
 * avisos da API e as instruções; a última instrução da API é a chegada.
 */
export function montarFalas(rota: RotaResposta): string[] {
  const primeira = rota.provisorio ? `${ABERTURA_PROVISORIA} ${rota.aviso_seguranca}` : rota.aviso_seguranca;
  return [
    primeira,
    `Demonstração do protótipo. Rota de ${rota.origem.nome} até ${rota.destino.nome}. ${textoDistanciaTotal(rota.distancia_m)}`,
    ...rota.avisos,
    ...rota.instrucoes.map((i) => i.texto),
  ];
}
