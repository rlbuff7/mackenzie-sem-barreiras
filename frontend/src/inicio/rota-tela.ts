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
import { montarFalas, textoDistanciaTotal, tituloDoResultado } from "../rotas/resumo.ts";
import type { Orientacao } from "../a11y/localizacao.ts";
import { iniciarOrientacaoAoVivo } from "./orientacao-tela.ts";
import { TELA_ESCOLHER, TELA_SEM_ROTA, telaDaRota } from "./telas.ts";
import type { Perfil, PontoInteresse, RotaResposta } from "../rotas/tipos.ts";
import { guardarPreferenciasDeVoz, lerPreferenciasDeVoz, vozesPortuguesas, velocidadeValida, AVISO_SEM_VOZ, AVISO_VOZ_FALHOU, avisoDeVoz, falar, enfileirarFala, type FalaDeVoz, type LeituraEmCurso, type SinteseDeVoz } from "../rotas/voz.ts";
import { fatorValido, metrosPorPasso, planejarFalas, proximoEvento, pontoNaDistancia, comprimentoTotal_m, VIBRACAO_CHEGADA } from "../rotas/simulacao.ts";
import { ESPERA_ANUNCIO_BUSCA_MS, confirmacaoDeOrigem, criarDebounce, escolherDestino, filtrarPontos, rotuloDoMarcador, textoContagem } from "../rotas/destino.ts";
import {
  TAMANHO_ALVO_MARCADOR_PX,
  TAMANHO_ICONE_LOSANGO_PX,
  TAMANHO_ICONE_PINO_PX,
  htmlAlvoEntrada,
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

export function iniciarRota(mapa: L.Map | null, orientacao: Orientacao): void {
  const selDe = el<HTMLSelectElement>("rota-de");
  const selPara = el<HTMLSelectElement>("rota-para");
  const campoBusca = el<HTMLInputElement>("rota-busca");
  const regiaoViva = el("anuncio-rota");
  const textoDestino = el("destino-escolhido");
  const botaoUsarOrigem = el<HTMLButtonElement>("usar-como-origem");
  const form = el<HTMLFormElement>("form-rota");
  const botao = el<HTMLButtonElement>("botao-tracar");
  const erroPontos = el("erro-pontos");
  const erroEscolha = el("erro-escolha");
  const erroRota = el("erro-rota");
  const resultado = el("resultado-rota");
  const titulo = el("titulo-resultado");
  const rotulo = el("rotulo-rota");
  const distancia = el("distancia-rota");
  const avisos = el("avisos-rota");
  const lista = el("instrucoes-rota");
  const botaoVoz = el<HTMLButtonElement>("botao-voz");
  const avisoVoz = el("aviso-voz");
  const botaoSimular = el<HTMLButtonElement>("botao-simular");
  const botaoPararSimulacao = el<HTMLButtonElement>("botao-parar-simulacao");
  const selSimulacao = el<HTMLSelectElement>("seletor-velocidade-simulacao");
  const blocoOrientacao = el("bloco-orientacao");
  let timerSimulacao: number | null = null;
  let bolinha: L.CircleMarker | null = null;

  const sintese = sinteseDoNavegador();
  let leitura: LeituraEmCurso | null = null;
  const selVoz = el<HTMLSelectElement>("seletor-voz");
  const selVelocidade = el<HTMLSelectElement>("seletor-velocidade");
  const botaoTestarVoz = el<HTMLButtonElement>("botao-testar-voz");
  const armazem = ((): Storage | null => {
    try {
      return window.localStorage;
    } catch {
      return null;
    }
  })();
  let preferencias = lerPreferenciasDeVoz(armazem);

  /** Lista as vozes pt do aparelho; no Chrome Android ela chega vazia e é recalculada em 'voiceschanged'. */
  function montarListaDeVozes(): void {
    const nomes = sintese ? vozesPortuguesas(sintese.getVoices()).map((v) => v.name ?? "") : [];
    const opcoes = nomes.filter((n) => n !== "");
    selVoz.replaceChildren(new Option("Automática (melhor disponível)", ""));
    for (const nome of opcoes) selVoz.append(new Option(nome, nome));
    selVoz.value = preferencias.nomeVoz && opcoes.includes(preferencias.nomeVoz) ? preferencias.nomeVoz : "";
  }
  selVelocidade.value = String(preferencias.velocidade);
  montarListaDeVozes();
  if (sintese) {
    if (typeof sintese.addEventListener === "function") sintese.addEventListener("voiceschanged", montarListaDeVozes);
    else sintese.onvoiceschanged = montarListaDeVozes;
  } else {
    botaoTestarVoz.hidden = true;
    selVoz.disabled = true;
    selVelocidade.disabled = true;
  }
  const aoMudarPreferencia = (): void => {
    preferencias = { nomeVoz: selVoz.value === "" ? null : selVoz.value, velocidade: velocidadeValida(selVelocidade.value) };
    guardarPreferenciasDeVoz(armazem, preferencias);
  };
  selVoz.addEventListener("change", aoMudarPreferencia);
  selVelocidade.addEventListener("change", aoMudarPreferencia);
  botaoTestarVoz.addEventListener("click", () => {
    leitura?.parar();
    leitura = falar(["Esta é a voz do app."], {
      sintese,
      criarFala: (texto) => new SpeechSynthesisUtterance(texto) as unknown as FalaDeVoz,
      preferencias,
      aoTerminar: () => {
        leitura = null;
      },
    });
  });

  const camadaRota = mapa ? L.layerGroup().addTo(mapa) : null;
  const camadaEntradas = mapa ? L.layerGroup().addTo(mapa) : null;
  let rotaAtual: RotaResposta | null = null;
  let ocupado = false;

  const mostrar = (e: HTMLElement, texto: string): void => {
    e.textContent = texto;
    e.hidden = false;
  };
  const esconder = (e: HTMLElement): void => {
    e.textContent = "";
    e.hidden = true;
  };

  function pararVoz(): void {
    leitura?.parar();
    leitura = null;
    botaoVoz.textContent = "Ouvir com a voz do app";
  }

  function limparResultado(): void {
    pararSimulacao();
    pararVoz();
    rotaAtual = null;
    camadaRota?.clearLayers();
    resultado.hidden = true;
    esconder(erroRota);
    esconder(erroEscolha);
    // De volta à tela de escolha: só o título muda (sem anúncio nem foco; a pessoa está nos campos).
    orientacao.definirTela(TELA_ESCOLHER);
  }

  // ---------- Simular caminhada (demonstração: a posição é imaginária) ----------

  function vibrar(padrao: number[]): void {
    if (padrao.length === 0) return;
    try {
      if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") navigator.vibrate(padrao);
    } catch {
      /* iPhone não vibra: nada a fazer */
    }
  }

  function dizer(texto: string, prioritaria: boolean): void {
    if (!prioritaria && enfileirarFala(texto, { sintese, criarFala: (t) => new SpeechSynthesisUtterance(t) as unknown as FalaDeVoz, preferencias })) return;
    // Prioritária: cancela antes, para nunca chegar atrasada (falar() também cancela).
    try {
      sintese?.cancel();
    } catch {
      /* nada a fazer */
    }
    leitura = falar([texto], {
      sintese,
      criarFala: (t) => new SpeechSynthesisUtterance(t) as unknown as FalaDeVoz,
      preferencias,
    });
  }

  function pararSimulacao(): void {
    if (timerSimulacao !== null) {
      window.clearInterval(timerSimulacao);
      timerSimulacao = null;
      leitura?.parar();
      leitura = null;
      try {
        sintese?.cancel();
      } catch {
        /* nada a fazer */
      }
    }
    bolinha?.remove();
    bolinha = null;
    botaoSimular.hidden = false;
    botaoPararSimulacao.hidden = true;
    selSimulacao.disabled = false;
    blocoOrientacao.hidden = false;
  }

  function iniciarSimulacao(): void {
    const rota = rotaAtual;
    if (!rota || rota.coordenadas.length === 0) return;
    pararSimulacao();
    pararVoz();
    const total_m = comprimentoTotal_m(rota.coordenadas);
    const fator = fatorValido(selSimulacao.value);
    const passo_m = metrosPorPasso(fator);
    const eventos = planejarFalas(rota.instrucoes, total_m, fator);
    const jaFaladas = new Set<string>();
    let percorrido_m = 0;
    botaoSimular.hidden = true;
    botaoPararSimulacao.hidden = false;
    selSimulacao.disabled = true;
    blocoOrientacao.hidden = true; // a simulação não tem GPS: sem "orientação ao vivo" ao mesmo tempo
    const mover = (): void => {
      const p = pontoNaDistancia(rota.coordenadas, percorrido_m);
      if (!p || !mapa) return;
      try {
        const ll = L.latLng(p[1], p[0]);
        if (bolinha) bolinha.setLatLng(ll);
        else bolinha = L.circleMarker(ll, { radius: 10, color: "#ffffff", weight: 3, fillColor: "#1a5fb4", fillOpacity: 1, interactive: false }).addTo(mapa);
        mapa.setView(ll, 19, { animate: false });
      } catch {
        /* o mapa é só referência */
      }
    };
    const falasDevidas = (): void => {
      for (let f = proximoEvento(eventos, percorrido_m, jaFaladas); f; f = proximoEvento(eventos, percorrido_m, jaFaladas)) {
        jaFaladas.add(f.chave);
        dizer(f.texto, f.prioridade === "alta");
        vibrar(f.vibrar);
      }
    };
    const passar = (): void => {
      percorrido_m = Math.min(percorrido_m + passo_m, total_m);
      mover();
      falasDevidas();
      if (percorrido_m >= total_m) {
        // Chegada: o texto é a última instrução da API (já falada ao cruzar o inicio_m dela); aqui só vibra e para.
        if (timerSimulacao !== null) window.clearInterval(timerSimulacao);
        timerSimulacao = null;
        vibrar(VIBRACAO_CHEGADA);
        bolinha?.remove();
        bolinha = null;
        botaoSimular.hidden = false;
        botaoPararSimulacao.hidden = true;
        selSimulacao.disabled = false;
        blocoOrientacao.hidden = false;
        return;
      }
    };
    mover();
    falasDevidas();
    timerSimulacao = window.setInterval(passar, 250);
  }

  botaoSimular.addEventListener("click", iniciarSimulacao);
  botaoPararSimulacao.addEventListener("click", pararSimulacao);

  // ---------- listas De e Para (com busca) ----------

  let todasPartidas: PontoInteresse[] = [];
  let todosDestinos: PontoInteresse[] = [];

  /** Anuncia na região aria-live que já existe (limpa antes, para repetir a mesma frase também ser lida). */
  function anunciar(texto: string): void {
    regiaoViva.textContent = "";
    window.setTimeout(() => {
      regiaoViva.textContent = texto;
    }, 60);
  }

  /** Lista filtrada pela busca; o que está escolhido continua na lista mesmo sem combinar (não some do campo). */
  function preencher(sel: HTMLSelectElement, pontos: PontoInteresse[], marcarAcessivel: boolean, mantido: string): void {
    const visiveis = filtrarPontos(pontos, campoBusca.value);
    const ids = new Set(visiveis.map((p) => String(p.id)));
    const lista = mantido !== "" && !ids.has(mantido) ? [...visiveis, ...pontos.filter((p) => String(p.id) === mantido)] : visiveis;
    sel.replaceChildren();
    const inicial = document.createElement("option");
    inicial.value = "";
    inicial.textContent = pontos.length === 0 ? "Nenhum ponto disponível" : visiveis.length === 0 ? "Nenhum lugar encontrado" : "Escolha um ponto";
    sel.append(inicial);
    for (const p of lista) {
      const o = document.createElement("option");
      o.value = String(p.id);
      o.textContent = marcarAcessivel && p.acessivel === true ? `${p.nome} (entrada acessível)` : p.nome;
      sel.append(o);
    }
    sel.value = mantido;
    sel.disabled = pontos.length === 0;
  }

  function preencherListas(): void {
    preencher(selDe, todasPartidas, false, selDe.value);
    preencher(selPara, todosDestinos, true, selPara.value);
  }

  /** Quantos lugares a busca achou (o maior das duas listas: a pessoa vê as duas). */
  function totalEncontrado(): number {
    return Math.max(filtrarPontos(todasPartidas, campoBusca.value).length, filtrarPontos(todosDestinos, campoBusca.value).length);
  }

  const anunciarContagem = criarDebounce(
    () => {
      if (campoBusca.value.trim() !== "") anunciar(textoContagem(totalEncontrado()));
    },
    ESPERA_ANUNCIO_BUSCA_MS,
    { agendar: (fn, ms) => window.setTimeout(fn, ms), cancelar: (id) => window.clearTimeout(id as number) },
  );
  campoBusca.addEventListener("input", () => {
    preencherListas();
    anunciarContagem.chamar();
  });
  // Enter na busca não envia o formulário (a pessoa ainda está escolhendo): só confirma a contagem.
  campoBusca.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    anunciarContagem.cancelar();
    anunciar(textoContagem(totalEncontrado()));
  });

  void buscarPontos().then((r) => {
    if (r.tipo === "erro") {
      for (const sel of [selDe, selPara]) {
        sel.replaceChildren(new Option("Lista indisponível", ""));
        sel.disabled = true;
      }
      mostrar(erroPontos, r.mensagem);
      return;
    }
    todasPartidas = pontosDePartida(r.pontos);
    todosDestinos = pontosDeDestino(r.pontos);
    preencherListas();
    desenharEntradasNoMapa();
    if (r.pontos.length === 0) mostrar(erroPontos, "Ainda não há pontos do campus cadastrados.");
  });

  const idEscolhido = (sel: HTMLSelectElement): number | null => (sel.value === "" ? null : Number(sel.value));
  const perfilEscolhido = (): Perfil =>
    (form.querySelector<HTMLInputElement>('input[name="perfil"]:checked')?.value as Perfil | undefined) ?? "cegueira";

  // Mudou a escolha: o resultado antigo deixou de valer (não fica rota de outro par de pontos na tela).
  for (const campo of [selDe, selPara, ...form.querySelectorAll<HTMLInputElement>('input[name="perfil"]')]) {
    campo.addEventListener("change", () => {
      if (rotaAtual || !erroRota.hidden || !erroEscolha.hidden) limparResultado();
    });
  }

  // ---------- destino pelo toque no mapa (RF03): o mesmo efeito da lista Para ----------

  const marcadoresDeEntrada = new Map<number, L.Marker>();
  let destinoConfirmadoId: number | null = null;

  /** Anel no marcador do destino escolhido e aria-pressed; a confirmação some se o Para mudou por outro caminho. */
  function sincronizarDestino(): void {
    const atual = idEscolhido(selPara);
    for (const [id, m] of marcadoresDeEntrada) {
      const e = m.getElement();
      if (!e) continue;
      e.querySelector(".mapa-alvo")?.classList.toggle("mapa-alvo--escolhido", id === atual);
      e.setAttribute("aria-pressed", id === atual ? "true" : "false");
    }
    if (destinoConfirmadoId !== null && destinoConfirmadoId !== atual) {
      destinoConfirmadoId = null;
      esconder(textoDestino);
    }
    if (idEscolhido(selDe) !== null) botaoUsarOrigem.hidden = true;
  }
  selPara.addEventListener("change", sincronizarDestino);
  selDe.addEventListener("change", sincronizarDestino);

  function escolherPeloMapa(id: number): void {
    const escolha = escolherDestino(todosDestinos, id, idEscolhido(selDe));
    if (!escolha) return;
    preencher(selPara, todosDestinos, true, String(id));
    selPara.dispatchEvent(new Event("change", { bubbles: true }));
    destinoConfirmadoId = id;
    mostrar(textoDestino, escolha.confirmacao);
    botaoUsarOrigem.hidden = !escolha.oferecerOrigem;
    sincronizarDestino();
    anunciar(escolha.oferecerOrigem ? `${escolha.confirmacao}. Há um botão para usar este ponto como origem.` : escolha.confirmacao);
  }

  botaoUsarOrigem.addEventListener("click", () => {
    const id = destinoConfirmadoId;
    const ponto = todasPartidas.find((p) => p.id === id);
    if (!ponto) return;
    // A origem passa a ser este ponto e o destino volta a ficar em aberto (partida e destino iguais não traçam rota).
    preencher(selDe, todasPartidas, false, String(ponto.id));
    preencher(selPara, todosDestinos, true, "");
    selDe.dispatchEvent(new Event("change", { bubbles: true }));
    selPara.dispatchEvent(new Event("change", { bubbles: true }));
    esconder(textoDestino);
    botaoUsarOrigem.hidden = true;
    selPara.focus();
    anunciar(`${confirmacaoDeOrigem(ponto.nome)}. Agora escolha o destino.`);
  });

  function desenharEntradasNoMapa(): void {
    if (!mapa) return;
    try {
      for (const ponto of todosDestinos) {
        const m = L.marker(pontoParaLatLng(ponto), {
          // Sem Tab: o mapa vem antes do formulário e dezenas de paradas travariam quem usa teclado; a lista Para faz o mesmo.
          keyboard: false,
          icon: L.divIcon({ className: "", html: htmlAlvoEntrada(false), iconSize: [TAMANHO_ALVO_MARCADOR_PX, TAMANHO_ALVO_MARCADOR_PX], iconAnchor: [TAMANHO_ALVO_MARCADOR_PX / 2, TAMANHO_ALVO_MARCADOR_PX / 2] }),
        });
        m.on("add", () => {
          const e = m.getElement();
          if (!e) return;
          e.setAttribute("role", "button");
          e.setAttribute("aria-label", rotuloDoMarcador(ponto.nome));
          e.setAttribute("aria-pressed", "false");
          e.setAttribute("tabindex", "-1");
          e.addEventListener("keydown", (ev) => {
            if (ev.key !== "Enter" && ev.key !== " ") return;
            ev.preventDefault();
            escolherPeloMapa(ponto.id);
          });
        });
        m.on("click", () => escolherPeloMapa(ponto.id));
        m.addTo(camadaEntradas ?? mapa);
        marcadoresDeEntrada.set(ponto.id, m);
      }
    } catch {
      // O mapa é só referência: a busca e a lista Para fazem o mesmo.
    }
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
    // Quem lê é o leitor de tela da pessoa: foco no título, depois avisos e <ol> na ordem do HTML; a região live só diz
    // onde a pessoa está e resume (com a voz do app ligada, é o app que fala essa frase).
    orientacao.mudarDeTela(telaDaRota(rota));
  }

  /** Começa a leitura (avisos antes das instruções, ver montarFalas). Sem await antes: no iPhone a voz só começa dentro do gesto. */
  function iniciarLeitura(): void {
    if (!rotaAtual) return;
    leitura = falar(montarFalas(rotaAtual), {
      sintese,
      criarFala: (texto) => new SpeechSynthesisUtterance(texto) as unknown as FalaDeVoz,
      preferencias,
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

  // ---------- Orientação ao vivo (GPS de verdade; a simulação acima é outra coisa) ----------

  iniciarOrientacaoAoVivo({
    mapa,
    orientacao,
    sintese,
    preferencias: () => preferencias,
    rota: () => rotaAtual,
    aoComecar: () => {
      pararSimulacao();
      pararVoz();
    },
  });

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
      orientacao.mudarDeTela(TELA_SEM_ROTA);
    }
  });
}

type PontoDaTela = { nome: string; latitude: number; longitude: number };
