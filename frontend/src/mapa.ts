/**
 * Mapa Leaflet: tiles do OpenStreetMap, área de estudo, barreiras por bbox e
 * seleção do ponto do alerta (clique no mapa, ou via botões externos que
 * chamam `selecionarPonto`).
 *
 * As cores usadas aqui (COR_*) espelham os tokens definidos em estilos.css.
 * Ficam duplicadas como constantes porque os elementos SVG do Leaflet usam
 * atributos de apresentação (stroke/fill), que não resolvem `var(--...)`.
 */

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { buscarAreaEstudo, buscarBarreiras, type FeatureBarreira } from "./api";

const CENTRO_INICIAL: L.LatLngTuple = [-23.5471938, -46.6524631];
const ZOOM_INICIAL = 17;
const ATRASO_DEBOUNCE_MS = 300;

const COR_PRIMARIA = "#1B4B6B";
const COR_SELECAO = "#B5501C";

export interface PontoSelecionado {
  latitude: number;
  longitude: number;
}

export interface ControladorMapa {
  /** Centro atual do mapa (para o botão "usar o centro do mapa"). */
  obterCentro(): PontoSelecionado;
  /** Move (ou cria) o marcador do ponto escolhido e avisa os ouvintes. */
  selecionarPonto(ponto: PontoSelecionado): void;
  /** Registra uma função chamada sempre que o ponto selecionado mudar. */
  aoSelecionarPonto(ouvinte: (ponto: PontoSelecionado) => void): void;
  /** Remove o marcador do ponto selecionado (usado após o envio do alerta). */
  limparSelecao(): void;
}

function debounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  atrasoMs: number,
): (...args: Args) => void {
  let temporizador: number | undefined;
  return (...args: Args) => {
    if (temporizador !== undefined) {
      window.clearTimeout(temporizador);
    }
    temporizador = window.setTimeout(() => fn(...args), atrasoMs);
  };
}

function escaparHtml(texto: string): string {
  const elemento = document.createElement("div");
  elemento.textContent = texto;
  return elemento.innerHTML;
}

function criarIconeBarreira(status: FeatureBarreira["properties"]["status"]): L.DivIcon {
  const classeExtra = status === "confirmada" ? "icone-barreira--confirmada" : "icone-barreira--pendente";
  return L.divIcon({
    className: "",
    html: `<span class="icone-barreira ${classeExtra}"></span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function conteudoPopupBarreira(feature: FeatureBarreira): string {
  const { tipo_nome, status, confirmacoes } = feature.properties;
  const rotuloStatus = status === "confirmada" ? "Confirmada" : "Pendente";
  const rotuloConfirmacoes =
    confirmacoes === 1 ? "1 confirmação" : `${confirmacoes} confirmações`;
  return [
    `<p class="popup-barreira__tipo">${escaparHtml(tipo_nome)}</p>`,
    `<p>Status: <strong>${rotuloStatus}</strong></p>`,
    `<p>${rotuloConfirmacoes}</p>`,
  ].join("");
}

export async function iniciarMapa(elementoId: string): Promise<ControladorMapa> {
  const mapa = L.map(elementoId, {
    center: CENTRO_INICIAL,
    zoom: ZOOM_INICIAL,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>',
  }).addTo(mapa);

  const camadaBarreiras = L.layerGroup().addTo(mapa);
  let marcadorSelecao: L.CircleMarker | null = null;
  const ouvintesSelecao: Array<(ponto: PontoSelecionado) => void> = [];

  async function carregarAreaEstudo(): Promise<void> {
    try {
      const colecao = await buscarAreaEstudo();
      L.geoJSON(colecao, {
        style: {
          color: COR_PRIMARIA,
          weight: 2,
          dashArray: "6 4",
          fillColor: COR_PRIMARIA,
          fillOpacity: 0.05,
        },
      }).addTo(mapa);
    } catch (erro) {
      console.error("Falha ao carregar a área de estudo:", erro);
    }
  }

  async function carregarBarreirasNaBbox(): Promise<void> {
    const limites = mapa.getBounds();
    const bbox: [number, number, number, number] = [
      limites.getWest(),
      limites.getSouth(),
      limites.getEast(),
      limites.getNorth(),
    ];
    try {
      const colecao = await buscarBarreiras(bbox);
      camadaBarreiras.clearLayers();
      for (const feature of colecao.features) {
        const [longitude, latitude] = feature.geometry.coordinates;
        const marcador = L.marker([latitude, longitude], {
          icon: criarIconeBarreira(feature.properties.status),
          keyboard: false,
        });
        marcador.bindPopup(conteudoPopupBarreira(feature));
        marcador.addTo(camadaBarreiras);
      }
    } catch (erro) {
      console.error("Falha ao carregar barreiras da área visível:", erro);
    }
  }

  const carregarBarreirasComDebounce = debounce(carregarBarreirasNaBbox, ATRASO_DEBOUNCE_MS);
  mapa.on("moveend", carregarBarreirasComDebounce);

  function selecionarPonto(ponto: PontoSelecionado): void {
    const posicao: L.LatLngTuple = [ponto.latitude, ponto.longitude];
    if (marcadorSelecao) {
      marcadorSelecao.setLatLng(posicao);
    } else {
      marcadorSelecao = L.circleMarker(posicao, {
        radius: 10,
        color: COR_SELECAO,
        weight: 3,
        fillColor: COR_SELECAO,
        fillOpacity: 0.85,
      }).addTo(mapa);
    }
    for (const ouvinte of ouvintesSelecao) {
      ouvinte(ponto);
    }
  }

  mapa.on("click", (evento: L.LeafletMouseEvent) => {
    selecionarPonto({ latitude: evento.latlng.lat, longitude: evento.latlng.lng });
  });

  await carregarAreaEstudo();
  await carregarBarreirasNaBbox();

  return {
    obterCentro(): PontoSelecionado {
      const centro = mapa.getCenter();
      return { latitude: centro.lat, longitude: centro.lng };
    },
    selecionarPonto,
    aoSelecionarPonto(ouvinte: (ponto: PontoSelecionado) => void): void {
      ouvintesSelecao.push(ouvinte);
    },
    limparSelecao(): void {
      if (marcadorSelecao) {
        mapa.removeLayer(marcadorSelecao);
        marcadorSelecao = null;
      }
    },
  };
}
