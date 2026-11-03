/**
 * As três telas da página inicial, para o título da página e o "Você está em: ...".
 * Sem DOM: o node:test confere os textos.
 */
import { NOME_TELA_ROTA, resumoDaRota } from "../rotas/resumo.ts";
import type { RotaResposta } from "../rotas/tipos.ts";
import type { Tela } from "../a11y/orientacao.ts";

export const TELA_ESCOLHER: Tela = {
  nome: "Escolher destino",
  acao: "Escolha de onde sai, para onde vai e o seu perfil. Depois toque em Traçar rota.",
};

export function telaDaRota(rota: Pick<RotaResposta, "avisos" | "distancia_m">): Tela {
  return { nome: NOME_TELA_ROTA, acao: resumoDaRota(rota) };
}

/** Rota não traçada (sem caminho, pedido inválido, rede). A mensagem do motivo recebe o foco e é lida por isso. */
export const TELA_SEM_ROTA: Tela = {
  nome: "Rota não traçada",
  acao: "Leia a mensagem e escolha de novo.",
};
