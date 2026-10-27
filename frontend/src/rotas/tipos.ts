/**
 * Tipos do contrato de GET /pontos-interesse e POST /rotas (docs/planos/e6-prototipo-banner.md, B2 e B3).
 * Coordenadas do GeoJSON vêm como [longitude, latitude]; unidades no nome (`distancia_m`).
 */
export type Perfil = "sem_restricao" | "cadeirante" | "deficiencia_visual";

export interface PontoInteresse {
  id: number;
  tipo: string;
  nome: string;
  descricao: string | null;
  acessivel: boolean | null;
  fonte_verificacao: string;
  tem_no: boolean;
  /** Em graus (WGS84). */
  latitude: number;
  longitude: number;
}

export interface PontoDaRota {
  id: number;
  nome: string;
  latitude: number;
  longitude: number;
}

export interface Instrucao {
  ordem: number;
  texto: string;
}

export interface RotaResposta {
  rotulo: string;
  provisorio: boolean;
  perfil: Perfil;
  origem: PontoDaRota;
  destino: PontoDaRota;
  distancia_m: number;
  acessivel_cadeirante: boolean | null;
  avisos: string[];
  /** Tipo de cada trecho (calcada, escada, rampa...), como a API devolve. */
  tipos_de_trecho: string[];
  aviso_seguranca: string;
  instrucoes: Instrucao[];
  /** LineString GeoJSON: cada par é [longitude, latitude]. */
  coordenadas: [number, number][];
}

export type MotivoDeErro = "sem_rota" | "invalido" | "indisponivel" | "rede" | "outro";

export type ResultadoRota =
  | { tipo: "ok"; rota: RotaResposta }
  | { tipo: "erro"; motivo: MotivoDeErro; mensagem: string };

export type ResultadoPontos =
  | { tipo: "ok"; pontos: PontoInteresse[]; rotulo: string }
  | { tipo: "erro"; motivo: MotivoDeErro; mensagem: string };
