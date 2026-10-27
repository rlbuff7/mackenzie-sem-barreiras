/**
 * Textos da rota, escritos para serem lidos em voz: "metros" por extenso, sem símbolo, sem coordenada.
 * Nada aqui inventa orientação: as instruções vêm prontas da API.
 */
import type { RotaResposta } from "./tipos.ts";

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

/**
 * Resumo curto que a região aria-live lê quando a rota aparece (o foco vai para o título e o leitor
 * de tela da pessoa lê avisos e instruções na ordem do HTML; aqui não se repete o texto todo).
 */
export function anuncioDaRota(rota: RotaResposta): string {
  const n = rota.avisos.length;
  const avisos = n === 0 ? "sem avisos" : n === 1 ? "1 aviso" : `${n} avisos`;
  return `Rota traçada: cerca de ${textoDistancia(rota.distancia_m)}, ${avisos}. As instruções vêm a seguir.`;
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
