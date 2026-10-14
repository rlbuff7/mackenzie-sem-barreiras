/**
 * Página inicial (index.html): mapa do campus como referência visual, com o cartão de entrada.
 * Não chama a API do projeto (as rotas novas ainda não existem) e não depende de
 * nenhum terceiro além dos tiles do OpenStreetMap. Se o mapa falhar, o texto da
 * página continua completo.
 */
import "../estilos.css";
import "./inicio.css";
import "../mapa/marcadores.css";
import { TAMANHO_ICONE_POSICAO_PX, htmlMarcadorPosicao } from "../mapa/marcadores.ts";
import { iniciarSeletorTema } from "../design/seletor-tema.ts";
import { iniciarInterruptorMovimento } from "../design/interruptor-movimento.ts";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Campus Mackenzie Higienópolis, aproximado: confirmar com o mapeamento de campo.
const CENTRO_CAMPUS: L.LatLngTuple = [-23.5475, -46.6522];
const ZOOM_INICIAL = 17;
const ZOOM_MAXIMO = 19;
const ZOOM_MINIMO = 15;

/** O mapa nunca anima (público cego e com baixa visão): nada de zoom, fade, inércia nem salto no limite. */
const SEM_ANIMACAO = {
  zoomAnimation: false,
  fadeAnimation: false,
  markerZoomAnimation: false,
  inertia: false,
  bounceAtZoomLimits: false,
} as const;

function iniciarMapaCampus(): void {
  const contêiner = document.getElementById("mapa-campus");
  if (!contêiner) return;

  try {
    const mapa = L.map(contêiner, {
      center: CENTRO_CAMPUS,
      zoom: ZOOM_INICIAL,
      minZoom: ZOOM_MINIMO,
      maxZoom: ZOOM_MAXIMO,
      zoomControl: false,
      ...SEM_ANIMACAO,
    });
    // Zoom embaixo à direita: no alto ficam a etiqueta do campus e o seletor de tema.
    L.control.zoom({ position: "bottomright" }).addTo(mapa);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: ZOOM_MAXIMO,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>',
    }).addTo(mapa);

    // Referência do campus: a bola de posição, sem seta (aqui não há rumo, e o mapa não chuta direção).
    // Não é a posição de quem abre a página: essa nunca é lida nem gravada nesta tela.
    const metade = TAMANHO_ICONE_POSICAO_PX / 2;
    L.marker(CENTRO_CAMPUS, {
      title: "Campus Mackenzie Higienópolis (referência aproximada)",
      alt: "Campus Mackenzie Higienópolis (referência aproximada)",
      icon: L.divIcon({
        className: "",
        html: htmlMarcadorPosicao(null),
        iconSize: [TAMANHO_ICONE_POSICAO_PX, TAMANHO_ICONE_POSICAO_PX],
        iconAnchor: [metade, metade],
      }),
    }).addTo(mapa);
  } catch {
    const aviso = document.getElementById("mapa-indisponivel");
    if (aviso) aviso.hidden = false;
    contêiner.hidden = true;
  }
}

iniciarSeletorTema();
iniciarInterruptorMovimento();
iniciarMapaCampus();
