/** Chamadas de rede de /api/pontos-interesse e /api/rotas. A lógica de interpretar fica em interpretar.ts. */
import {
  MENSAGEM_REDE,
  interpretarRespostaDePontos,
  interpretarRespostaDeRota,
  montarRequisicaoDeRota,
  urlDosPontos,
  type PedidoDeRota,
} from "./interpretar.ts";
import type { ResultadoPontos, ResultadoRota } from "./tipos.ts";

type Busca = (url: string, init?: RequestInit) => Promise<Response>;

async function corpoJson(resposta: Response): Promise<unknown> {
  try {
    return await resposta.json();
  } catch {
    return null;
  }
}

export async function buscarPontos(busca: Busca = fetch.bind(globalThis)): Promise<ResultadoPontos> {
  try {
    const resposta = await busca(urlDosPontos());
    return interpretarRespostaDePontos(resposta.status, await corpoJson(resposta));
  } catch {
    return { tipo: "erro", motivo: "rede", mensagem: MENSAGEM_REDE };
  }
}

export async function tracarRota(pedido: PedidoDeRota, busca: Busca = fetch.bind(globalThis)): Promise<ResultadoRota> {
  const { url, init } = montarRequisicaoDeRota(pedido);
  try {
    const resposta = await busca(url, init);
    return interpretarRespostaDeRota(resposta.status, await corpoJson(resposta), pedido.perfil);
  } catch {
    return { tipo: "erro", motivo: "rede", mensagem: MENSAGEM_REDE };
  }
}
