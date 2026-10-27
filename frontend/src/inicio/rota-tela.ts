/**
 * Fluxo de rota da página inicial: listas De e Para (GET /api/pontos-interesse), perfil, "Traçar rota"
 * (POST /api/rotas), linha no mapa, instruções em texto e leitura em voz.
 *
 * Regras: a posição de quem usa nunca é lida (a partida é um ponto da lista); a voz só começa dentro
 * do toque no botão; sem caminho, não se desenha nada; depois de traçar, o foco vai para o título do
 * resultado e UMA frase é anunciada; o mapa não anima (animate: false em tudo que o move).
 */
import L from "leaflet";
import { buscarPontos, tracarRota } from "../rotas/api.ts";
import { paraLatLng, pontoParaLatLng } from "../rotas/geometria.ts";
import { pontosDeDestino, pontosDePartida, problemaNaEscolha } from "../rotas/interpretar.ts";
import { anuncioDaRota, montarFalas, textoDistanciaTotal, tituloDoResultado } from "../rotas/resumo.ts";
import type { Perfil, PontoInteresse, RotaResposta } from "../rotas/tipos.ts";
import { AVISO_SEM_VOZ, AVISO_VOZ_FALHOU, avisoDeVoz, falar, type FalaDeVoz, type LeituraEmCurso, type SinteseDeVoz } from "../rotas/voz.ts";
import {
  TAMANHO_ICONE_LOSANGO_PX,
  TAMANHO_ICONE_PINO_PX,
  htmlMarcadorReferencia,
  htmlPinoEntradaAcessivel,
} from "../mapa/marcadores.ts";

function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id);
  if (!e) throw new Error(`Falta o elemento #${id} em index.html`);
  return e as T;
}

function sinteseDoNavegador(): SinteseDeVoz | null {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined"
    ? (window.speechSynthesis as unknown as SinteseDeVoz)
    : null;
}

export function iniciarRota(mapa: L.Map | null): void {
  const selDe = el<HTMLSelectElement>("rota-de");
  const selPara = el<HTMLSelectElement>("rota-para");
  const form = el<HTMLFormElement>("form-rota");
  const botao = el<HTMLButtonElement>("botao-tracar");
  const erroPontos = el("erro-pontos");
  const erroEscolha = el("erro-escolha");
  const erroRota = el("erro-rota");
  const anuncio = el("anuncio-rota");
  const resultado = el("resultado-rota");
  const titulo = el("titulo-resultado");
  const rotulo = el("rotulo-rota");
  const distancia = el("distancia-rota");
  const avisos = el("avisos-rota");
  const lista = el("instrucoes-rota");
  const botaoVoz = el<HTMLButtonElement>("botao-voz");
  const avisoVoz = el("aviso-voz");

  const camadaRota = mapa ? L.layerGroup().addTo(mapa) : null;
  const sintese = sinteseDoNavegador();
  let leitura: LeituraEmCurso | null = null;
  let rotaAtual: RotaResposta | null = null;
  let ocupado = false;
  let anuncioPendente: number | null = null;

  const mostrar = (e: HTMLElement, texto: string): void => {
    e.textContent = texto;
    e.hidden = false;
  };
  const esconder = (e: HTMLElement): void => {
    e.textContent = "";
    e.hidden = true;
  };

  /** Fala uma frase só, uma vez: limpa a região e escreve no quadro seguinte (repetir a mesma frase também é lido). */
  function anunciar(frase: string): void {
    if (anuncioPendente !== null) window.clearTimeout(anuncioPendente);
    anuncio.textContent = "";
    anuncioPendente = window.setTimeout(() => {
      anuncio.textContent = frase;
      anuncioPendente = null;
    }, 60);
  }

  function pararVoz(): void {
    leitura?.parar();
    leitura = null;
    botaoVoz.textContent = "Ouvir com a voz do app";
  }

  function limparResultado(): void {
    pararVoz();
    rotaAtual = null;
    camadaRota?.clearLayers();
    resultado.hidden = true;
    esconder(erroRota);
    esconder(erroEscolha);
    anuncio.textContent = "";
  }

  // ---------- listas De e Para ----------

  function preencher(sel: HTMLSelectElement, pontos: PontoInteresse[], marcarAcessivel: boolean): void {
    sel.replaceChildren();
    const inicial = document.createElement("option");
    inicial.value = "";
    inicial.textContent = pontos.length > 0 ? "Escolha um ponto" : "Nenhum ponto disponível";
    sel.append(inicial);
    for (const p of pontos) {
      const o = document.createElement("option");
      o.value = String(p.id);
      o.textContent = marcarAcessivel && p.acessivel === true ? `${p.nome} (entrada acessível)` : p.nome;
      sel.append(o);
    }
    sel.disabled = pontos.length === 0;
  }

  void buscarPontos().then((r) => {
    if (r.tipo === "erro") {
      for (const sel of [selDe, selPara]) {
        sel.replaceChildren(new Option("Lista indisponível", ""));
        sel.disabled = true;
      }
      mostrar(erroPontos, r.mensagem);
      return;
    }
    preencher(selDe, pontosDePartida(r.pontos), false);
    preencher(selPara, pontosDeDestino(r.pontos), true);
    if (r.pontos.length === 0) mostrar(erroPontos, "Ainda não há pontos do campus cadastrados.");
  });

  const idEscolhido = (sel: HTMLSelectElement): number | null => (sel.value === "" ? null : Number(sel.value));
  const perfilEscolhido = (): Perfil =>
    (form.querySelector<HTMLInputElement>('input[name="perfil"]:checked')?.value as Perfil | undefined) ?? "deficiencia_visual";

  // Mudou a escolha: o resultado antigo deixou de valer (não fica rota de outro par de pontos na tela).
  for (const campo of [selDe, selPara, ...form.querySelectorAll<HTMLInputElement>('input[name="perfil"]')]) {
    campo.addEventListener("change", () => {
      if (rotaAtual || !erroRota.hidden || !erroEscolha.hidden) limparResultado();
    });
  }

  // ---------- mapa ----------

  function marcador(ponto: PontoDaTela, html: string, tamanho: number, rotuloTexto: string): L.Marker {
    const m = L.marker(pontoParaLatLng(ponto), {
      keyboard: false,
      interactive: false,
      icon: L.divIcon({ className: "", html, iconSize: [tamanho, tamanho], iconAnchor: [tamanho / 2, tamanho / 2] }),
    });
    m.bindTooltip(`${rotuloTexto}: ${ponto.nome}`, { permanent: true, direction: "top", className: "mapa-rotulo-ponto", offset: [0, -tamanho / 2] });
    return m;
  }

  function desenharNoMapa(rota: RotaResposta): void {
    if (!mapa || !camadaRota) return;
    try {
      const linha = paraLatLng(rota.coordenadas);
      // Contorno branco por baixo, laranja por cima: some em qualquer cor de tile, e a forma é a mesma.
      L.polyline(linha, { className: "mapa-rota-contorno", interactive: false, weight: 10, color: "#ffffff" }).addTo(camadaRota);
      L.polyline(linha, { className: "mapa-rota-linha", interactive: false, weight: 6, color: "#d9560f" }).addTo(camadaRota);
      marcador(rota.origem, htmlMarcadorReferencia(), TAMANHO_ICONE_LOSANGO_PX, "Partida").addTo(camadaRota);
      const destinoAcessivel = rota.acessivel_cadeirante !== false && rota.perfil === "cadeirante";
      marcador(rota.destino, destinoAcessivel ? htmlPinoEntradaAcessivel() : htmlMarcadorReferencia(), destinoAcessivel ? TAMANHO_ICONE_PINO_PX : TAMANHO_ICONE_LOSANGO_PX, "Chegada").addTo(camadaRota);
      mapa.invalidateSize({ animate: false });
      mapa.fitBounds(L.latLngBounds(linha), { padding: [40, 40], animate: false });
    } catch {
      // O mapa é só referência: a lista de instruções já diz tudo.
    }
  }

  // ---------- resultado ----------

  function desenharResultado(rota: RotaResposta): void {
    rotaAtual = rota;
    titulo.textContent = tituloDoResultado(rota);
    rotulo.textContent = rota.rotulo;
    distancia.textContent = textoDistanciaTotal(rota.distancia_m);
    avisos.replaceChildren(...rota.avisos.map((a) => Object.assign(document.createElement("li"), { textContent: `Atenção: ${a}` })));
    avisos.hidden = rota.avisos.length === 0;
    lista.replaceChildren(...rota.instrucoes.map((i) => Object.assign(document.createElement("li"), { textContent: i.texto })));
    botaoVoz.hidden = sintese === null;
    botaoVoz.textContent = "Ouvir com a voz do app";
    if (sintese === null) mostrar(avisoVoz, AVISO_SEM_VOZ);
    else esconder(avisoVoz);
    desenharNoMapa(rota);
    // Desenha tudo ANTES de mostrar e de anunciar; depois foco no título e uma frase só.
    resultado.hidden = false;
    titulo.focus();
    // Quem lê é o leitor de tela da pessoa: foco no título, depois avisos e <ol> na ordem do HTML; a região live só resume.
    anunciar(anuncioDaRota(rota));
  }

  /** Começa a leitura (avisos antes das instruções, ver montarFalas). Sem await antes: no iPhone a voz só começa dentro do gesto. */
  function iniciarLeitura(): void {
    if (!rotaAtual) return;
    leitura = falar(montarFalas(rotaAtual), {
      sintese,
      criarFala: (texto) => new SpeechSynthesisUtterance(texto) as unknown as FalaDeVoz,
      aoTerminar: (falhou) => {
        leitura = null;
        botaoVoz.textContent = "Ouvir com a voz do app";
        if (falhou) mostrar(avisoVoz, AVISO_VOZ_FALHOU);
      },
    });
    if (leitura === null) {
      mostrar(avisoVoz, AVISO_SEM_VOZ);
      return;
    }
    botaoVoz.textContent = "Parar";
    const aviso = sintese ? avisoDeVoz(sintese.getVoices()) : null;
    if (aviso) mostrar(avisoVoz, aviso);
    else esconder(avisoVoz);
  }

  botaoVoz.addEventListener("click", () => {
    if (leitura) {
      pararVoz();
      return;
    }
    iniciarLeitura();
  });

  window.addEventListener("pagehide", () => sintese?.cancel());

  // ---------- Traçar rota ----------

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (ocupado) return;
    limparResultado();
    const origemId = idEscolhido(selDe);
    const destinoId = idEscolhido(selPara);
    const problema = problemaNaEscolha(origemId, destinoId);
    if (problema !== null || origemId === null || destinoId === null) {
      mostrar(erroEscolha, problema ?? "Escolha os dois pontos.");
      (origemId === null ? selDe : selPara).focus();
      return;
    }
    ocupado = true;
    botao.setAttribute("aria-disabled", "true");
    botao.textContent = "Traçando…";
    const r = await tracarRota({ origem_id: origemId, destino_id: destinoId, perfil: perfilEscolhido() });
    ocupado = false;
    botao.removeAttribute("aria-disabled");
    botao.textContent = "Traçar rota";
    if (r.tipo === "ok") {
      desenharResultado(r.rota);
    } else {
      // Silêncio é melhor que palpite: nada no mapa. A frase recebe o foco e é lida por isso.
      mostrar(erroRota, r.mensagem);
      erroRota.focus();
    }
  });
}

type PontoDaTela = { nome: string; latitude: number; longitude: number };
