/*
 * Os 10 pontos de controle escolhidos pelo Maurício (docs/medicao-gps.md, P01 a P10).
 * Lógica pura, sem DOM. As coordenadas são REFERÊNCIAS estimadas em imagem de satélite, não
 * medições topográficas: servem para mostrar onde ficar e comparar depois, nunca para "corrigir"
 * a posição que o GPS mediu.
 */
import type { Condicao } from "./medicao.ts";

export interface PontoControle {
  /** 1 a 10: é o `ponto` que vai para a API (o banco aceita 1 a 12). */
  numero: number;
  codigo: string;
  /** Nome curto para a tela. */
  nome: string;
  /** Valor enviado à API (ceu_aberto, entre_predios, entrada_predio, coberto). */
  condicao: Condicao;
  referencia_lat: number;
  referencia_lon: number;
  observacao: string;
}

export const PONTOS_CONTROLE: readonly PontoControle[] = [
  { numero: 1, codigo: "P01", nome: "Praça de convivência, perto do Prédio 18", condicao: "ceu_aberto", referencia_lat: -23.54667967656296, referencia_lon: -46.65279158889783, observacao: "Praça em frente ao Auditório Ruy Barbosa." },
  { numero: 2, codigo: "P02", nome: "Área aberta perto da Biblioteca Central (Prédio 2)", condicao: "ceu_aberto", referencia_lat: -23.546013383953508, referencia_lon: -46.65202165910552, observacao: "Perto do Bosque das Fadas e da Ultra Coffee Mackenzie." },
  { numero: 3, codigo: "P03", nome: "Passagem entre os Prédios 6 e 24", condicao: "entre_predios", referencia_lat: -23.546915816255126, referencia_lon: -46.65172517217903, observacao: "Perto do escadão que dá acesso à frente do Starbucks." },
  { numero: 4, codigo: "P04", nome: "Entrada principal do Prédio 29", condicao: "entrada_predio", referencia_lat: -23.54757664389376, referencia_lon: -46.6516827262256, observacao: "Em frente ao Prédio 31 e colado ao prédio do MackGraphe." },
  { numero: 5, codigo: "P05", nome: "Entrada principal do Prédio 31", condicao: "entrada_predio", referencia_lat: -23.54744263607399, referencia_lon: -46.65146814951144, observacao: "Em frente ao MackGraphe." },
  { numero: 6, codigo: "P06", nome: "Entrada do Auditório da Escola Americana", condicao: "entrada_predio", referencia_lat: -23.547747707942488, referencia_lon: -46.652778943818376, observacao: "Perto da entrada da rua Piauí." },
  { numero: 7, codigo: "P07", nome: "Bifurcação de caminhos do campus", condicao: "ceu_aberto", referencia_lat: -23.5468504473735, referencia_lon: -46.652032195907886, observacao: "Perto do Starbucks." },
  { numero: 8, codigo: "P08", nome: "Início da escadaria externa", condicao: "entre_predios", referencia_lat: -23.547931731633664, referencia_lon: -46.65280467209573, observacao: "Escadaria de saída para a rua Piauí. Fique em local seguro, antes do primeiro degrau." },
  { numero: 9, codigo: "P09", nome: "Caminho perto das quadras poliesportivas", condicao: "ceu_aberto", referencia_lat: -23.547712278983497, referencia_lon: -46.65230980453806, observacao: "Caminho entre as quadras poliesportivas e o Prédio 45." },
  { numero: 10, codigo: "P10", nome: "Circulação perto do Auditório da Escola Americana", condicao: "ceu_aberto", referencia_lat: -23.547640357443996, referencia_lon: -46.65275773344059, observacao: "Área externa perto do auditório, onde ficam algumas vagas especiais para cadeirantes." },
];

/** Centro aproximado do campus (centroide do seed db/seeds/002; confirmar com o mapeamento). */
export const CENTRO_CAMPUS: readonly [number, number] = [-23.5471938, -46.6524631];
/** Recorte provisório do campus: o círculo de 500 m do seed (pendência: polígono definitivo). */
export const RAIO_CAMPUS_M = 500;

export function pontoDeControle(numero: number): PontoControle | undefined {
  return PONTOS_CONTROLE.find((p) => p.numero === numero);
}

/** "P03 · Passagem entre os Prédios 6 e 24" */
export function tituloDoPonto(p: PontoControle): string {
  return `${p.codigo} · ${p.nome}`;
}

/** Distância em metros entre duas coordenadas (haversine, esfera de 6371 km). */
export function distanciaMetros(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(a)));
}

const AVISO_ESTIMATIVA = "A referência é uma estimativa por imagem de satélite, não a posição exata.";

/** Texto auxiliar da legenda. Só informa: nunca corrige nem orienta direção. */
export function textoDistanciaReferencia(distancia_m: number | null): string {
  if (distancia_m === null || !Number.isFinite(distancia_m) || distancia_m < 0) return AVISO_ESTIMATIVA;
  const m = Math.round(distancia_m);
  const quanto = m < 1 ? "menos de 1 metro" : m === 1 ? "1 metro" : `${m} metros`;
  return `Referência a ${quanto}. ${AVISO_ESTIMATIVA}`;
}
