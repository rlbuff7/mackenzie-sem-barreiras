/**
 * Página inicial (index.html): mapa do campus como referência visual, com o cartão de entrada.
 * Chama só /api/pontos-interesse e /api/rotas (rota-tela.ts) e não depende de nenhum
 * terceiro além dos tiles do OpenStreetMap. Se o mapa falhar, o texto da página continua
 * completo e o fluxo de rota funciona só com as listas.
 */
import "../estilos.css";
import "./inicio.css";
import "../mapa/marcadores.css";
import { OPCOES_DE_FOCO_DO_MAPA, OPCOES_DO_ZOOM, PREFIXO_DA_ATRIBUICAO } from "../mapa/acessibilidade.ts";
import { TAMANHO_ICONE_POSICAO_PX, htmlMarcadorPosicao } from "../mapa/marcadores.ts";
import { iniciarAjustes } from "../design/ajustes.ts";
import { iniciarSeletorTema } from "../design/seletor-tema.ts";
import { iniciarInterruptorMovimento } from "../design/interruptor-movimento.ts";
import { iniciarRota } from "./rota-tela.ts";
import { iniciarOrientacaoDaPagina } from "../a11y/pagina.ts";
import { TELA_ESCOLHER } from "./telas.ts";
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

function iniciarMapaCampus(): L.Map | null {
  const contêiner = document.getElementById("mapa-campus");
  if (!contêiner) return null;

  try {
    const mapa = L.map(contêiner, {
      center: CENTRO_CAMPUS,
      zoom: ZOOM_INICIAL,
      minZoom: ZOOM_MINIMO,
      maxZoom: ZOOM_MAXIMO,
      zoomControl: false,
      ...SEM_ANIMACAO,
      ...OPCOES_DE_FOCO_DO_MAPA,
    });
    mapa.attributionControl.setPrefix(PREFIXO_DA_ATRIBUICAO);
    // Zoom embaixo à direita: no alto ficam a etiqueta do campus e o seletor de tema.
    L.control.zoom({ position: "bottomright", ...OPCOES_DO_ZOOM }).addTo(mapa);

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
      // Só referência visual: sem foco e sem papel de botão (o leitor de tela não teria o que fazer ali).
      keyboard: false,
      interactive: false,
      icon: L.divIcon({
        className: "",
        html: htmlMarcadorPosicao(null),
        iconSize: [TAMANHO_ICONE_POSICAO_PX, TAMANHO_ICONE_POSICAO_PX],
        iconAnchor: [metade, metade],
      }),
    }).addTo(mapa);
    return mapa;
  } catch {
    const aviso = document.getElementById("mapa-indisponivel");
    if (aviso) aviso.hidden = false;
    contêiner.hidden = true;
    return null;
  }
}

iniciarAjustes();
iniciarSeletorTema();
iniciarInterruptorMovimento();
const orientacao = iniciarOrientacaoDaPagina({ regiao: "anuncio-rota", botao: "botao-voz-tela", nota: "nota-voz-tela" });
orientacao.definirTela(TELA_ESCOLHER);
iniciarRota(iniciarMapaCampus(), orientacao);
