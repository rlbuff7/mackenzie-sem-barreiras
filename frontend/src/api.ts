/**
 * Cliente HTTP tipado para a API do Mackenzie sem Barreiras.
 *
 * As formas de request/response aqui espelham exatamente o Contrato da API
 * (docs/api.md). Nenhum campo é inventado ou omitido em relação ao contrato.
 */

// Duas formas possíveis (R19): absoluta (`http://localhost:8000`, o padrão do
// servidor de dev do Vite — porta 5173 — que fala com a API por CORS) ou
// relativa (`/api`, usada pela imagem de container: `frontend/nginx.conf`
// encaminha `/api/` para o serviço `api` na mesma origem, sem precisar de
// CORS). A barra final é removida nos dois casos: todo `caminho` abaixo já
// começa com "/", então a concatenação nunca produz "//".
const URL_BASE_API: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

/** Um tipo de barreira ativo, como devolvido por GET /tipos-barreira. */
export interface TipoBarreira {
  codigo: string;
  nome: string;
  /** `tipos_barreira.descricao` aceita NULL no banco. */
  descricao: string | null;
}

/** Geometria de ponto em GeoJSON (coordinates = [longitude, latitude]). */
interface GeometriaPonto {
  type: "Point";
  coordinates: [number, number];
}

/** Geometria de polígono em GeoJSON. */
interface GeometriaPoligono {
  type: "Polygon";
  coordinates: number[][][];
}

/** Feature da área de estudo, devolvida por GET /area-estudo. */
export interface FeatureAreaEstudo {
  type: "Feature";
  properties: {
    nome: string;
    /** `area_estudo.descricao` aceita NULL no banco. */
    descricao: string | null;
  };
  geometry: GeometriaPoligono;
}

export interface ColecaoAreaEstudo {
  type: "FeatureCollection";
  features: FeatureAreaEstudo[];
}

/** Status possível de um alerta já persistido (bruto | descartado). */
export type StatusAlerta = "bruto" | "descartado";

/** Status possível de uma barreira consolidada. */
export type StatusBarreira = "pendente" | "confirmada";

/** Feature de barreira, devolvida por GET /barreiras. */
export interface FeatureBarreira {
  type: "Feature";
  properties: {
    id: number;
    tipo: string;
    tipo_nome: string;
    confirmacoes: number;
    status: StatusBarreira;
    atualizado_em: string;
  };
  geometry: GeometriaPonto;
}

export interface ColecaoBarreiras {
  type: "FeatureCollection";
  /** De onde vêm as barreiras (G10): o mesmo texto das estatísticas para a origem. */
  rotulo: string;
  features: FeatureBarreira[];
}

/** Corpo de POST /alertas. */
export interface PayloadAlerta {
  latitude: number;
  longitude: number;
  tipo: string;
  severidade: number | null;
  descricao: string | null;
  sessao_id: string;
}

/** Resposta de sucesso (201) de POST /alertas. */
export interface RespostaAlerta {
  id: number;
  status: StatusAlerta;
  motivo_descarte: string | null;
  mensagem: string;
}

/** Um erro de validação de campo, dentro da resposta 422. */
export interface ErroCampo {
  campo: string;
  erro: string;
}

/** Resposta de erro de validação (422) de POST /alertas. */
export interface RespostaErroValidacao {
  mensagem: string;
  erros: ErroCampo[];
}

/**
 * Resultado do envio de um alerta, como um dos três desfechos possíveis:
 * sucesso (201, com status bruto ou descartado), erro de validação (422)
 * ou falha de rede/servidor indisponível.
 */
export type ResultadoEnvioAlerta =
  | { tipo: "sucesso"; dados: RespostaAlerta }
  | { tipo: "erro_validacao"; dados: RespostaErroValidacao }
  | { tipo: "erro_rede"; mensagem: string };

/** Erro lançado quando a API responde com um formato inesperado. */
export class ErroApiInesperado extends Error {}

async function requisitarJson<T>(caminho: string): Promise<T> {
  const resposta = await fetch(`${URL_BASE_API}${caminho}`);
  if (!resposta.ok) {
    throw new ErroApiInesperado(
      `Falha ao consultar ${caminho}: HTTP ${resposta.status}`,
    );
  }
  return (await resposta.json()) as T;
}

/** GET /tipos-barreira — taxonomia ativa, ordenada por nome. */
export async function buscarTiposBarreira(): Promise<TipoBarreira[]> {
  return requisitarJson<TipoBarreira[]>("/tipos-barreira");
}

/** GET /area-estudo — polígono(s) da área de estudo, em GeoJSON. */
export async function buscarAreaEstudo(): Promise<ColecaoAreaEstudo> {
  return requisitarJson<ColecaoAreaEstudo>("/area-estudo");
}

/**
 * GET /barreiras?bbox=... — barreiras confirmadas/pendentes dentro da bbox
 * visível do mapa. `origem` é sempre "real": este é o cliente do voluntário
 * de campo, nunca do gerador de dados sintéticos.
 */
export async function buscarBarreiras(
  bbox: readonly [number, number, number, number],
): Promise<ColecaoBarreiras> {
  const parametros = new URLSearchParams({
    bbox: bbox.join(","),
    origem: "real",
  });
  return requisitarJson<ColecaoBarreiras>(`/barreiras?${parametros.toString()}`);
}

/**
 * POST /alertas — envia um alerta do voluntário. Nunca lança para 422 (erro
 * de validação) ou falha de rede: essas situações viram um `ResultadoEnvioAlerta`
 * para que a interface trate cada uma com uma mensagem adequada.
 */
export async function enviarAlerta(
  payload: PayloadAlerta,
): Promise<ResultadoEnvioAlerta> {
  let resposta: Response;
  try {
    resposta = await fetch(`${URL_BASE_API}/alertas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      tipo: "erro_rede",
      mensagem: "Não foi possível conectar ao servidor. Confira sua conexão e tente novamente.",
    };
  }

  if (resposta.status === 201) {
    try {
      const dados = (await resposta.json()) as RespostaAlerta;
      return { tipo: "sucesso", dados };
    } catch {
      return {
        tipo: "erro_rede",
        mensagem:
          "O servidor confirmou o recebimento, mas a resposta veio num formato inesperado. Recarregue a página para conferir se o alerta foi registrado.",
      };
    }
  }

  if (resposta.status === 422) {
    try {
      const dados = (await resposta.json()) as RespostaErroValidacao;
      return { tipo: "erro_validacao", dados };
    } catch {
      return {
        tipo: "erro_rede",
        mensagem:
          "O servidor recusou o alerta, mas a resposta veio num formato inesperado. Tente novamente.",
      };
    }
  }

  return {
    tipo: "erro_rede",
    mensagem: `O servidor respondeu de forma inesperada (HTTP ${resposta.status}). Tente novamente em instantes.`,
  };
}
