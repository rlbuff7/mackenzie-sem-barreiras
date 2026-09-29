/**
 * Mapa Leaflet: tiles do OpenStreetMap, área de estudo, barreiras por bbox e
 * seleção do ponto do alerta (clique no mapa, ou via botões externos que
 * chamam `selecionarPonto`).
 *
 * As cores usadas aqui (COR_*) espelham os tokens definidos em estilos.css.
 * Ficam duplicadas como constantes porque os elementos SVG do Leaflet usam
 * atributos de apresentação (stroke/fill), que não resolvem `var(--...)`.
 *
 * Os marcadores de barreira ficam fora da ordem de tabulação
 * (`keyboard: false`) para não criar uma fila de centenas de paradas de Tab
 * quando a bbox tem muitos resultados. Em troca, `aoAtualizarBarreiras` expõe
 * os mesmos dados como uma lista simples, para quem navega só por teclado ou
 * leitor de tela conseguir inspecionar as barreiras sem precisar apontar
 * para um marcador (ver main.ts, que renderiza essa lista).
 */

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  buscarAreaEstudo,
  buscarBarreiras,
  type ColecaoBarreiras,
  type FeatureBarreira,
} from "./api";
import { itensIguais, type ItemListaBarreira } from "./itens";

export type { ItemListaBarreira };

const CENTRO_INICIAL: L.LatLngTuple = [-23.5471938, -46.6524631];
const ZOOM_INICIAL = 17;
// Com zoom menor que este, o mapa mostraria meia cidade ou mais: a lista ficaria
// enorme e, afastando mais, o retângulo visível passaria de ±180° de longitude,
// que GET /barreiras recusa com 422. 13 ainda mostra o entorno inteiro do campus.
const ZOOM_MINIMO = 13;
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
  /** Barreiras da última bbox carregada (para renderizar a lista já na primeira vez). */
  obterItensAtuais(): ItemListaBarreira[];
  /** Registra uma função chamada sempre que as barreiras da bbox atual mudarem. */
  aoAtualizarBarreiras(ouvinte: (itens: ItemListaBarreira[]) => void): void;
  /** Centraliza o mapa numa barreira e abre o popup dela (usado pela lista acessível). */
  focarBarreira(id: number): void;
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

function limitar(valor: number, minimo: number, maximo: number): number {
  return Math.min(Math.max(valor, minimo), maximo);
}

/**
 * Retângulo visível no formato de GET /barreiras (minLon, minLat, maxLon,
 * maxLat), dentro de ±180/±90. O Leaflet deixa arrastar o mapa para além do
 * antimeridiano, e aí os limites passam de 180; a API recusaria esse bbox. Se o
 * que sobra depois de limitar não tem área (a vista inteira ficou fora do
 * mundo), devolve `null`: não há barreira nenhuma para pedir.
 */
function bboxVisivel(limites: L.LatLngBounds): [number, number, number, number] | null {
  const bbox: [number, number, number, number] = [
    limitar(limites.getWest(), -180, 180),
    limitar(limites.getSouth(), -90, 90),
    limitar(limites.getEast(), -180, 180),
    limitar(limites.getNorth(), -90, 90),
  ];
  return bbox[0] < bbox[2] && bbox[1] < bbox[3] ? bbox : null;
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
    minZoom: ZOOM_MINIMO,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>',
  }).addTo(mapa);

  const camadaBarreiras = L.layerGroup().addTo(mapa);
  let marcadorSelecao: L.CircleMarker | null = null;
  const ouvintesSelecao: Array<(ponto: PontoSelecionado) => void> = [];
  const marcadoresPorId = new Map<number, L.Marker>();
  const ouvintesAtualizacaoBarreiras: Array<(itens: ItemListaBarreira[]) => void> = [];
  let itensAtuais: ItemListaBarreira[] = [];
  let idBarreiraEmFoco: number | null = null;

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

  // Só a consulta mais recente vale: mover o mapa de novo cancela a anterior, e
  // uma resposta que chegue atrasada (o fetch já não abortável) é ignorada pela
  // sequência, para não sobrescrever a vista mais nova com a bbox antiga.
  let controladorConsulta: AbortController | null = null;
  let sequenciaConsulta = 0;

  async function carregarBarreirasNaBbox(): Promise<void> {
    controladorConsulta?.abort();
    const controlador = new AbortController();
    controladorConsulta = controlador;
    const minhaSequencia = ++sequenciaConsulta;
    const bbox = bboxVisivel(mapa.getBounds());
    try {
      const colecao: Pick<ColecaoBarreiras, "features"> =
        bbox === null
          ? { features: [] }
          : await buscarBarreiras(bbox, controlador.signal);
      if (minhaSequencia !== sequenciaConsulta) {
        return;
      }
      const itens: ItemListaBarreira[] = colecao.features.map((feature) => ({
        id: feature.properties.id,
        tipoNome: feature.properties.tipo_nome,
        status: feature.properties.status,
        confirmacoes: feature.properties.confirmacoes,
        latitude: feature.geometry.coordinates[1],
        longitude: feature.geometry.coordinates[0],
      }));
      // Só refaz a camada de marcadores (e avisa a lista acessível) se o
      // conteúdo realmente mudou: recarregar com o mesmo resultado não pode
      // apagar e recriar os marcadores (fecharia o popup aberto) nem forçar
      // main.ts a reconstruir a lista, o que derrubaria o foco de quem acabou
      // de ativar um botão "Ver no mapa" nela.
      const mudou = !itensIguais(itens, itensAtuais);
      if (mudou) {
        camadaBarreiras.clearLayers();
        marcadoresPorId.clear();
        for (const feature of colecao.features) {
          const [longitude, latitude] = feature.geometry.coordinates;
          const marcador = L.marker([latitude, longitude], {
            icon: criarIconeBarreira(feature.properties.status),
            keyboard: false,
          });
          marcador.bindPopup(conteudoPopupBarreira(feature));
          marcador.addTo(camadaBarreiras);
          marcadoresPorId.set(feature.properties.id, marcador);
        }
        itensAtuais = itens;
      }
      // Se a barreira que a lista acessível centralizou por último ainda está
      // nesta bbox, reabre o popup dela — sem isso, o clique em "ver no mapa"
      // abriria o popup só para ele sumir na recarga do moveend. É um reforço
      // só desta primeira recarga: reabre no máximo uma vez.
      if (idBarreiraEmFoco !== null) {
        marcadoresPorId.get(idBarreiraEmFoco)?.openPopup();
        idBarreiraEmFoco = null;
      }
      if (mudou) {
        for (const ouvinte of ouvintesAtualizacaoBarreiras) {
          ouvinte(itens);
        }
      }
    } catch (erro) {
      if (erro instanceof DOMException && erro.name === "AbortError") {
        return; // cancelada por uma consulta mais nova: não é falha
      }
      console.error("Falha ao carregar barreiras da área visível:", erro);
    }
  }

  const carregarBarreirasComDebounce = debounce(carregarBarreirasNaBbox, ATRASO_DEBOUNCE_MS);
  mapa.on("moveend", carregarBarreirasComDebounce);

  function selecionarPonto(ponto: PontoSelecionado): void {
    // Escolher um ponto para um alerta novo é uma ação diferente de inspecionar
    // uma barreira existente: solta o "foco" para não reabrir um popup antigo.
    idBarreiraEmFoco = null;
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
    obterItensAtuais(): ItemListaBarreira[] {
      return itensAtuais;
    },
    aoAtualizarBarreiras(ouvinte: (itens: ItemListaBarreira[]) => void): void {
      ouvintesAtualizacaoBarreiras.push(ouvinte);
    },
    focarBarreira(id: number): void {
      const marcador = marcadoresPorId.get(id);
      if (!marcador) {
        return;
      }
      const destino = marcador.getLatLng();
      const zoomDestino = Math.max(mapa.getZoom(), ZOOM_INICIAL);
      // A recarga que reabre o popup vem do `moveend`. Se a vista já está no
      // destino, não haverá `moveend`: o "foco" ficaria armado e reabriria o
      // popup numa recarga futura qualquer (o usuário arrastando o mapa).
      const vistaMuda = !mapa.getCenter().equals(destino) || mapa.getZoom() !== zoomDestino;
      idBarreiraEmFoco = vistaMuda ? id : null;
      mapa.setView(destino, zoomDestino);
      marcador.openPopup();
    },
  };
}
