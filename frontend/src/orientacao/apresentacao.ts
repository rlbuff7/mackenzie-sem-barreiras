/**
 * Resposta de POST /api/orientacoes -> o que a tela mostra, fala e vibra. Sem DOM e sem rede.
 *
 * Regra de ouro (CLAUDE.md §1): silêncio é melhor que palpite. O app NÃO inventa direção nem frase: só
 * mostra e fala o `mensagem.texto` que a API devolveu; o resto é rótulo fixo do `estado` (sempre com
 * símbolo e palavra, nunca só cor). Resposta que não bate com o contrato vira "orientação pausada",
 * sem fala e sem vibração.
 */
import { MENSAGEM_SEM_ROTA } from "../rotas/interpretar.ts";
import { VIBRACAO_CHEGADA, padraoDeVibracao, type Curva } from "../rotas/simulacao.ts";
import { NOME_TELA_ROTA, resumoDaRota } from "../rotas/resumo.ts";
import { NOME_DO_APP, type Tela } from "../a11y/orientacao.ts";

export type EstadoDaOrientacao = "na_rota" | "fora_da_rota" | "precisao_insuficiente" | "chegou";
export type PrioridadeDaMensagem = "perigo" | "alta" | "media" | "baixa";

export interface MensagemDaApi {
  chave: string;
  texto: string;
  prioridade: PrioridadeDaMensagem;
}

export interface Apresentacao {
  estado: EstadoDaOrientacao;
  /** Palavra do estado, em texto grande. */
  rotulo: string;
  /** Forma do estado (junto da palavra): nunca só cor. */
  simbolo: string;
  /** "Faltam cerca de N metros", ou null (sem distância, ou já chegou). */
  distanciaTexto: string | null;
  mensagem: MensagemDaApi | null;
  /** perigo ou alta: região assertive, cancela a fala anterior. */
  urgente: boolean;
  /** Padrão de vibração (vazio = nenhuma). */
  vibrar: number[];
  chegou: boolean;
  /** O que anunciar/falar (vazio se não há o que dizer). Na chegada inclui "Orientação encerrada". */
  textoParaDizer: string;
}

export const ROTULOS: Record<EstadoDaOrientacao, { rotulo: string; simbolo: string }> = {
  na_rota: { rotulo: "Na rota", simbolo: "✓" },
  fora_da_rota: { rotulo: "Você saiu da rota", simbolo: "✕" },
  precisao_insuficiente: { rotulo: "Sem GPS confiável", simbolo: "◆" },
  chegou: { rotulo: "Você chegou", simbolo: "★" },
};

export const VIBRACAO_ALTA = [300, 100, 300];

export const AVISO_SEGURANCA = "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade.";
export const AVISO_PROVISORIO = "Direções provisórias, calculadas pelo mapa aberto.";
export const ROTULO_AGUARDANDO = "Aguardando o GPS";
/** Orientação parada (erro ou fim): rótulo e forma próprios, para não parecer "sem GPS". */
export const ROTULO_PARADA = { rotulo: "Orientação parada", simbolo: "■" };
export const TEXTO_SEM_MENSAGEM = "Nenhuma mensagem ainda.";
export const TEXTO_ENCERRADA = "Orientação encerrada";
export const TEXTO_SEM_CONEXAO = "Sem conexão: orientação pausada";
export const TEXTO_RESPOSTA_INVALIDA = "Resposta inesperada do servidor: orientação pausada.";
export const TEXTO_GPS_PERDIDO = "Sem sinal de GPS agora. Em lugar aberto o sinal costuma melhorar; aguarde.";
export const TEXTO_GPS_NEGADO =
  "O GPS está bloqueado para este site. Para liberar: toque no cadeado ao lado do endereço, abra as configurações do site e permita a Localização. No iPhone: Ajustes, Privacidade, Serviços de Localização, Safari. Depois toque em Iniciar orientação ao vivo de novo.";
export const TEXTO_SEM_GEOLOCALIZACAO = "Este navegador não tem GPS. A orientação ao vivo não funciona aqui.";
export const TEXTO_SEM_BUSSOLA = "Sem bússola confiável neste aparelho: só direção pelo movimento, quando você anda.";

const ESTADOS = Object.keys(ROTULOS) as EstadoDaOrientacao[];
const PRIORIDADES: readonly string[] = ["perigo", "alta", "media", "baixa"];

type Dicionario = Record<string, unknown>;
const ehDicionario = (v: unknown): v is Dicionario => typeof v === "object" && v !== null && !Array.isArray(v);

/** "Faltam cerca de 112 metros"; null se a API não informou (ou não é número). */
export function textoDeDistanciaRestante(distancia_m: unknown): string | null {
  if (typeof distancia_m !== "number" || !Number.isFinite(distancia_m) || distancia_m < 0) return null;
  const n = Math.round(distancia_m);
  if (n === 0) return "Falta menos de 1 metro";
  return n === 1 ? "Falta cerca de 1 metro" : `Faltam cerca de ${n} metros`;
}

/**
 * Vibração da mensagem. Perigo e alta: [300,100,300]. Curva: o padrão da simulação, lido do texto que a API
 * mandou ("vire à direita"...); direção: pelo setor da `chave`; "frente" e o resto não vibram.
 */
export function vibracaoDaMensagem(m: MensagemDaApi): number[] {
  if (m.prioridade === "perigo" || m.prioridade === "alta") return [...VIBRACAO_ALTA];
  if (m.chave.startsWith("curva_")) {
    const t = m.texto.toLowerCase();
    const leve = t.includes("levemente");
    let curva: Curva | null = null;
    if (t.includes("retorno")) curva = "retorno";
    else if (t.includes("direita")) curva = leve ? "leve_direita" : "direita";
    else if (t.includes("esquerda")) curva = leve ? "leve_esquerda" : "esquerda";
    return padraoDeVibracao(curva);
  }
  if (m.chave === "direcao_direita") return padraoDeVibracao("direita");
  if (m.chave === "direcao_esquerda") return padraoDeVibracao("esquerda");
  if (m.chave === "direcao_atras") return padraoDeVibracao("retorno");
  return [];
}

function lerMensagem(v: unknown): MensagemDaApi | null | undefined {
  if (v === null) return null;
  if (!ehDicionario(v)) return undefined;
  if (typeof v.chave !== "string" || v.chave.trim() === "" || typeof v.texto !== "string" || v.texto.trim() === "") return undefined;
  if (typeof v.prioridade !== "string" || !PRIORIDADES.includes(v.prioridade)) return undefined;
  return { chave: v.chave, texto: v.texto.trim(), prioridade: v.prioridade as PrioridadeDaMensagem };
}

/** Confere o corpo de um 200. null se algo essencial falta ou vem torto (vira "pausada", nunca palpite). */
export function lerResposta(corpo: unknown): Apresentacao | null {
  if (!ehDicionario(corpo)) return null;
  const estado = corpo.estado;
  if (typeof estado !== "string" || !ESTADOS.includes(estado as EstadoDaOrientacao)) return null;
  if (!("mensagem" in corpo)) return null;
  const mensagem = lerMensagem(corpo.mensagem);
  if (mensagem === undefined) return null;
  const e = estado as EstadoDaOrientacao;
  const chegou = e === "chegou";
  const urgente = !!mensagem && (mensagem.prioridade === "perigo" || mensagem.prioridade === "alta");
  const vibrar = chegou ? [...VIBRACAO_CHEGADA] : mensagem ? vibracaoDaMensagem(mensagem) : [];
  const textoParaDizer = chegou ? `${(mensagem?.texto ?? ROTULOS.chegou.rotulo).replace(/[.\s]+$/, "")}. ${TEXTO_ENCERRADA}.` : (mensagem?.texto ?? "");
  return {
    estado: e,
    ...ROTULOS[e],
    distanciaTexto: chegou ? null : textoDeDistanciaRestante(corpo.distancia_restante_m),
    mensagem,
    urgente,
    vibrar,
    chegou,
    textoParaDizer,
  };
}

/** Estado local quando o GPS some: só o rótulo, sem mensagem, sem distância, sem fala. */
export function apresentacaoSemGps(): Apresentacao {
  return { estado: "precisao_insuficiente", ...ROTULOS.precisao_insuficiente, distanciaTexto: null, mensagem: null, urgente: false, vibrar: [], chegou: false, textoParaDizer: "" };
}

export type ResultadoOrientacao =
  | { tipo: "ok"; apresentacao: Apresentacao }
  /** `parar`: acaba a orientação; senão fica pausada e tenta de novo no próximo ciclo. */
  | { tipo: "erro"; motivo: "rede" | "servidor" | "sem_rota" | "invalido" | "resposta_invalida"; mensagem: string; parar: boolean };

export function interpretarResposta(status: number, corpo: unknown): ResultadoOrientacao {
  if (status === 200) {
    const apresentacao = lerResposta(corpo);
    return apresentacao ? { tipo: "ok", apresentacao } : { tipo: "erro", motivo: "resposta_invalida", mensagem: TEXTO_RESPOSTA_INVALIDA, parar: false };
  }
  if (status === 404) {
    if (ehDicionario(corpo) && corpo.codigo === "sem_rota") {
      const m = typeof corpo.mensagem === "string" && corpo.mensagem.trim() !== "" ? corpo.mensagem.trim() : MENSAGEM_SEM_ROTA;
      return { tipo: "erro", motivo: "sem_rota", mensagem: m, parar: true };
    }
    return { tipo: "erro", motivo: "invalido", mensagem: "Um dos pontos da rota não foi encontrado. Volte e trace a rota de novo.", parar: true };
  }
  if (status === 413 || status === 422 || (status >= 400 && status < 500 && status !== 408 && status !== 429)) {
    return { tipo: "erro", motivo: "invalido", mensagem: "Não deu para orientar com esses dados. Volte e trace a rota de novo.", parar: true };
  }
  return { tipo: "erro", motivo: "servidor", mensagem: TEXTO_SEM_CONEXAO, parar: false };
}

export const RESULTADO_SEM_REDE: ResultadoOrientacao = { tipo: "erro", motivo: "rede", mensagem: TEXTO_SEM_CONEXAO, parar: false };

/** Erro do GPS (PositionError.code): 1 negado (para), 2 e 3 são passageiros (continua esperando). */
export function resultadoDoErroDeGps(codigo: number): { mensagem: string; parar: boolean } {
  if (codigo === 1) return { mensagem: TEXTO_GPS_NEGADO, parar: true };
  return { mensagem: TEXTO_GPS_PERDIDO, parar: false };
}

// ---------- telas (título da página e anúncio, via a11y/orientacao) ----------

export const NOME_TELA_AO_VIVO = "Orientação ao vivo";

export const TELA_AO_VIVO: Tela = {
  nome: NOME_TELA_AO_VIVO,
  acao: "Aguardando o GPS. Para encerrar, toque em Parar orientação.",
};

/** Ao parar: volta à "Rota traçada ...", dizendo que a orientação acabou. */
export function telaAoParar(rota: Parameters<typeof resumoDaRota>[0]): Tela {
  return { nome: NOME_TELA_ROTA, acao: `${TEXTO_ENCERRADA}. ${resumoDaRota(rota)}` };
}

/** "Orientação ao vivo · Navegação Acessível no Campus" (o mesmo texto de tituloDaPagina). */
export const TITULO_AO_VIVO = `${NOME_TELA_AO_VIVO} · ${NOME_DO_APP}`;

// ---------- mapa: privacidade dos tiles ----------

/** Retângulo do campus (minLon, minLat, maxLon, maxLat) com folga; fora dele o mapa NÃO segue a pessoa. */
export const LIMITE_MAPA_CAMPUS = [-46.6622, -23.5575, -46.6422, -23.5375] as const;

/**
 * O mapa só acompanha a posição dentro do campus: os blocos do mapa pedidos ao OpenStreetMap revelam a
 * região mostrada, e quem está longe não deve ter o lugar em que está entregue a um terceiro.
 */
export function dentroDoCampus(lat: number, lon: number): boolean {
  const [minLon, minLat, maxLon, maxLat] = LIMITE_MAPA_CAMPUS;
  return Number.isFinite(lat) && Number.isFinite(lon) && lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat;
}
