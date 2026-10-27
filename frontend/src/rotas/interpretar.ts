/**
 * Pedido e resposta da API de rotas, sem DOM e sem rede (a chamada de verdade fica em api.ts).
 * Regra do projeto: silêncio é melhor que palpite. Resposta que não bate com o contrato nunca
 * vira linha no mapa: vira a mensagem "Não encontrei um caminho seguro".
 */
import type {
  MotivoDeErro,
  Perfil,
  PontoInteresse,
  ResultadoPontos,
  ResultadoRota,
  RotaResposta,
} from "./tipos.ts";

export const URL_PONTOS = "/api/pontos-interesse";
export const URL_ROTAS = "/api/rotas";

/** Retângulo do campus (minLon, minLat, maxLon, maxLat), em graus, com folga em volta do centro aproximado. */
export const BBOX_CAMPUS = [-46.6622, -23.5575, -46.6422, -23.5375] as const;

export const MENSAGEM_SEM_ROTA = "Não encontrei um caminho seguro entre esses pontos.";
export const MENSAGEM_REDE = "Sem conexão com o servidor. Confira a internet e tente de novo.";
export const MENSAGEM_INDISPONIVEL =
  "O mapa de caminhos do campus não está disponível agora. Tente de novo em alguns instantes.";
export const MENSAGEM_OUTRO = "Não consegui traçar a rota agora. Tente de novo.";
export const MENSAGEM_RESPOSTA_INVALIDA = MENSAGEM_SEM_ROTA;

export function urlDosPontos(bbox: readonly number[] = BBOX_CAMPUS): string {
  return `${URL_PONTOS}?bbox=${bbox.join(",")}`;
}

export interface PedidoDeRota {
  origem_id: number;
  destino_id: number;
  perfil: Perfil;
}

export interface RequisicaoHttp {
  url: string;
  init: { method: "POST"; headers: Record<string, string>; body: string };
}

/** Corpo exato do contrato (campos extras são recusados pela API). Sem posição, sem identificador de pessoa. */
export function montarRequisicaoDeRota(pedido: PedidoDeRota): RequisicaoHttp {
  return {
    url: URL_ROTAS,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origem_id: pedido.origem_id,
        destino_id: pedido.destino_id,
        perfil: pedido.perfil,
      }),
    },
  };
}

type Dicionario = Record<string, unknown>;

function ehDicionario(v: unknown): v is Dicionario {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function numeroFinito(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function paresValidos(v: unknown): v is [number, number][] {
  return (
    Array.isArray(v) &&
    v.length >= 2 &&
    v.every(
      (p) =>
        Array.isArray(p) &&
        p.length >= 2 &&
        numeroFinito(p[0]) &&
        numeroFinito(p[1]) &&
        Math.abs(p[0]) <= 180 &&
        Math.abs(p[1]) <= 90,
    )
  );
}

function pontoDaRota(v: unknown): RotaResposta["origem"] | null {
  if (!ehDicionario(v)) return null;
  if (!numeroFinito(v.id) || typeof v.nome !== "string") return null;
  if (!numeroFinito(v.latitude) || !numeroFinito(v.longitude)) return null;
  return { id: v.id, nome: v.nome, latitude: v.latitude, longitude: v.longitude };
}

/** Confere o corpo de um 200 de POST /rotas. Devolve null se algo essencial faltar ou vier torto. */
export function lerRota(corpo: unknown): RotaResposta | null {
  if (!ehDicionario(corpo)) return null;
  const origem = pontoDaRota(corpo.origem);
  const destino = pontoDaRota(corpo.destino);
  const geometria = corpo.geometria;
  if (!origem || !destino || !ehDicionario(geometria)) return null;
  if (geometria.type !== "LineString" || !paresValidos(geometria.coordinates)) return null;
  if (!numeroFinito(corpo.distancia_m) || corpo.distancia_m < 0) return null;
  if (typeof corpo.rotulo !== "string" || typeof corpo.aviso_seguranca !== "string") return null;
  if (!Array.isArray(corpo.instrucoes) || corpo.instrucoes.length === 0) return null;
  const instrucoes = [];
  for (const i of corpo.instrucoes) {
    if (!ehDicionario(i) || typeof i.texto !== "string" || i.texto.trim() === "") return null;
    instrucoes.push({ ordem: numeroFinito(i.ordem) ? i.ordem : instrucoes.length + 1, texto: i.texto });
  }
  instrucoes.sort((a, b) => a.ordem - b.ordem);
  const avisos = Array.isArray(corpo.avisos)
    ? corpo.avisos.filter((a): a is string => typeof a === "string" && a.trim() !== "")
    : [];
  return {
    rotulo: corpo.rotulo,
    provisorio: corpo.provisorio === true,
    perfil: corpo.perfil === "cadeirante" ? "cadeirante" : "sem_restricao",
    origem,
    destino,
    distancia_m: corpo.distancia_m,
    acessivel_cadeirante: typeof corpo.acessivel_cadeirante === "boolean" ? corpo.acessivel_cadeirante : null,
    avisos,
    tipos_de_trecho: Array.isArray(corpo.trechos)
      ? corpo.trechos.map((t) => (ehDicionario(t) && typeof t.tipo === "string" ? t.tipo : ""))
      : [],
    aviso_seguranca: corpo.aviso_seguranca,
    instrucoes,
    coordenadas: geometria.coordinates,
  };
}

function erro(motivo: MotivoDeErro, mensagem: string): { tipo: "erro"; motivo: MotivoDeErro; mensagem: string } {
  return { tipo: "erro", motivo, mensagem };
}

function primeiroErroDe422(corpo: unknown): string | null {
  if (!ehDicionario(corpo)) return null;
  const lista = corpo.erros;
  if (Array.isArray(lista) && ehDicionario(lista[0]) && typeof lista[0].erro === "string") return lista[0].erro;
  return typeof corpo.mensagem === "string" ? corpo.mensagem : null;
}

/**
 * Defesa extra: no perfil cadeirante, rota com escada nunca é mostrada (o backend já a exclui; se
 * vier mesmo assim, vale o silêncio). Usa o tipo estruturado dos trechos; os textos só como reforço.
 */
export function rotaTemEscada(rota: RotaResposta): boolean {
  const texto = /escada/i;
  return (
    rota.tipos_de_trecho.some((t) => t.toLowerCase() === "escada") ||
    rota.avisos.some((a) => texto.test(a)) ||
    rota.instrucoes.some((i) => texto.test(i.texto)) ||
    rota.acessivel_cadeirante === false
  );
}

/** Traduz status + corpo JSON (ou null se não for JSON) de POST /rotas em resultado para a tela. */
export function interpretarRespostaDeRota(status: number, corpo: unknown, perfilPedido?: Perfil): ResultadoRota {
  if (status === 200) {
    const rota = lerRota(corpo);
    if (!rota) return erro("sem_rota", MENSAGEM_RESPOSTA_INVALIDA);
    if ((perfilPedido ?? rota.perfil) === "cadeirante" && rotaTemEscada(rota)) return erro("sem_rota", MENSAGEM_SEM_ROTA);
    return { tipo: "ok", rota };
  }
  if (status === 404) {
    if (ehDicionario(corpo) && corpo.codigo === "sem_rota") return erro("sem_rota", MENSAGEM_SEM_ROTA);
    return erro("invalido", "Um dos pontos não foi encontrado. Recarregue a página e escolha de novo.");
  }
  if (status === 422) {
    const detalhe = primeiroErroDe422(corpo);
    return erro("invalido", detalhe ? `Não deu para traçar essa rota: ${detalhe}` : "Não deu para traçar essa rota. Confira os dois pontos.");
  }
  if (status === 503) return erro("indisponivel", MENSAGEM_INDISPONIVEL);
  return erro("outro", MENSAGEM_OUTRO);
}

/** Lê um ponto de interesse (Feature GeoJSON); null se vier torto. */
function lerPonto(feature: unknown): PontoInteresse | null {
  if (!ehDicionario(feature) || !ehDicionario(feature.properties) || !ehDicionario(feature.geometry)) return null;
  const p = feature.properties;
  const coords = feature.geometry.coordinates;
  if (feature.geometry.type !== "Point" || !paresValidos([coords, coords])) return null;
  const [longitude, latitude] = coords as [number, number];
  if (!numeroFinito(p.id) || typeof p.nome !== "string" || typeof p.tipo !== "string") return null;
  return {
    id: p.id,
    tipo: p.tipo,
    nome: p.nome,
    descricao: typeof p.descricao === "string" ? p.descricao : null,
    acessivel: typeof p.acessivel === "boolean" ? p.acessivel : null,
    fonte_verificacao: typeof p.fonte_verificacao === "string" ? p.fonte_verificacao : "",
    tem_no: p.tem_no === true,
    latitude,
    longitude,
  };
}

export function interpretarRespostaDePontos(status: number, corpo: unknown): ResultadoPontos {
  if (status !== 200) {
    return erro(status === 503 ? "indisponivel" : "outro", "A lista de pontos do campus não carregou. Recarregue a página para tentar de novo.");
  }
  if (!ehDicionario(corpo) || !Array.isArray(corpo.features)) {
    return erro("outro", "A lista de pontos do campus não carregou. Recarregue a página para tentar de novo.");
  }
  const pontos = corpo.features.map(lerPonto).filter((p): p is PontoInteresse => p !== null);
  return { tipo: "ok", pontos, rotulo: typeof corpo.rotulo === "string" ? corpo.rotulo : "" };
}

/** Pontos que podem ser partida: todos os que estão ligados ao mapa de caminhos. */
export function pontosDePartida(pontos: PontoInteresse[]): PontoInteresse[] {
  return pontos.filter((p) => p.tem_no);
}

/** Destino é sempre a entrada de um prédio, ligada ao mapa de caminhos. */
export function pontosDeDestino(pontos: PontoInteresse[]): PontoInteresse[] {
  return pontos.filter((p) => p.tem_no && p.tipo === "entrada");
}

/** Erro de escolha antes de chamar a API (mensagem em palavra), ou null se está tudo certo. */
export function problemaNaEscolha(origemId: number | null, destinoId: number | null): string | null {
  if (origemId === null && destinoId === null) return "Escolha o ponto de partida e o destino.";
  if (origemId === null) return "Escolha o ponto de partida.";
  if (destinoId === null) return "Escolha o destino.";
  if (origemId === destinoId) return "Partida e destino são o mesmo ponto. Escolha dois pontos diferentes.";
  return null;
}
