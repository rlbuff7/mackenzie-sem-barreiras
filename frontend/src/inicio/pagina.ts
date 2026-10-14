/**
 * Página inicial (index.html): só mostra o mapa do campus como referência visual.
 * Não chama a API do projeto (as rotas novas ainda não existem) e não depende de
 * nenhum terceiro além dos tiles do OpenStreetMap. Se o mapa falhar, o texto da
 * página continua completo.
 */
import "../estilos.css";
import "./inicio.css";
import { iniciarSeletorTema } from "../design/seletor-tema.ts";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Campus Mackenzie Higienópolis, aproximado: confirmar com o mapeamento de campo.
const CENTRO_CAMPUS: L.LatLngTuple = [-23.5475, -46.6522];
const ZOOM_INICIAL = 17;
const ZOOM_MAXIMO = 19;
const ZOOM_MINIMO = 15;

function iniciarMapaCampus(): void {
  const contêiner = document.getElementById("mapa-campus");
  if (!contêiner) return;

  try {
    const mapa = L.map(contêiner, {
      center: CENTRO_CAMPUS,
      zoom: ZOOM_INICIAL,
      minZoom: ZOOM_MINIMO,
      maxZoom: ZOOM_MAXIMO,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: ZOOM_MAXIMO,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>',
    }).addTo(mapa);

    // Marcador de referência: quadrado com borda dupla, para não depender só da cor.
    L.marker(CENTRO_CAMPUS, {
      title: "Campus Mackenzie Higienópolis (referência aproximada)",
      alt: "Campus Mackenzie Higienópolis (referência aproximada)",
      icon: L.divIcon({
        className: "",
        html: '<span class="inicio__marcador" aria-hidden="true"></span>',
        iconSize: [22, 22],
        iconAnchor: [11, 11],
      }),
    }).addTo(mapa);
  } catch {
    const aviso = document.getElementById("mapa-indisponivel");
    if (aviso) aviso.hidden = false;
    contêiner.hidden = true;
  }
}

iniciarSeletorTema();
iniciarMapaCampus();
