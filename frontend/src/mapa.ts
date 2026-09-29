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

/** Uma barreira da bbox atual, com só o necessário para a lista acessível. */
export interface ItemListaBarreira {
  id: number;
  tipoNome: string;
  status: FeatureBarreira["properties"]["status"];
  confirmacoes: number;
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

/**
 * Compara duas listas de barreiras pelo que a lista acessível exibe (id,
 * tipo, status, confirmações), como conjuntos — sem depender da ordem, já
 * que o backend não garante a mesma ordem entre duas consultas idênticas.
 * Usado para não notificar `aoAtualizarBarreiras` — e assim não forçar
 * main.ts a reconstruir a lista e derrubar o foco de teclado — quando a
 * recarga da bbox devolve exatamente o mesmo conteúdo de antes.
 */
function itensIguais(a: ItemListaBarreira[], b: ItemListaBarreira[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const porId = new Map(b.map((item) => [item.id, item]));
  return a.every((item) => {
    const outro = porId.get(item.id);
    return (
      outro !== undefined &&
      outro.tipoNome === item.tipoNome &&
      outro.status === item.status &&
      outro.confirmacoes === item.confirmacoes
    );
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
      marcadoresPorId.clear();
      const itens: ItemListaBarreira[] = [];
      for (const feature of colecao.features) {
        const [longitude, latitude] = feature.geometry.coordinates;
        const marcador = L.marker([latitude, longitude], {
          icon: criarIconeBarreira(feature.properties.status),
          keyboard: false,
        });
        marcador.bindPopup(conteudoPopupBarreira(feature));
        marcador.addTo(camadaBarreiras);
        marcadoresPorId.set(feature.properties.id, marcador);
        itens.push({
          id: feature.properties.id,
          tipoNome: feature.properties.tipo_nome,
          status: feature.properties.status,
          confirmacoes: feature.properties.confirmacoes,
        });
      }
      // Se a barreira que a lista acessível centralizou por último ainda está
      // nesta bbox, reabre o popup dela no marcador recém-criado — sem isso,
      // o clique em "ver no mapa" abriria o popup só para ele sumir na
      // próxima recarga (a cada moveend, mesmo sem o usuário mexer em nada).
      // É um reforço só desta primeira recarga: reabre no máximo uma vez, e
      // não fica reabrindo popup sozinho em toda recarga futura.
      if (idBarreiraEmFoco !== null) {
        marcadoresPorId.get(idBarreiraEmFoco)?.openPopup();
        idBarreiraEmFoco = null;
      }
      // Só troca o estado (e avisa a lista acessível) se o conteúdo realmente
      // mudou: recarregar com o mesmo resultado não pode forçar main.ts a
      // reconstruir a lista, porque isso derrubaria o foco de quem acabou de
      // ativar um botão "Ver no mapa" nela.
      if (!itensIguais(itens, itensAtuais)) {
        itensAtuais = itens;
        for (const ouvinte of ouvintesAtualizacaoBarreiras) {
          ouvinte(itens);
        }
      }
    } catch (erro) {
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
      idBarreiraEmFoco = id;
      mapa.setView(marcador.getLatLng(), Math.max(mapa.getZoom(), ZOOM_INICIAL));
      marcador.openPopup();
    },
  };
}
