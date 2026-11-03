/**
 * Tela "Orientação ao vivo" (index.html): GPS + bússola + POST /api/orientacoes a cada ~2,5 s.
 *
 * PRIVACIDADE (RNF04, inegociável): a posição de quem navega e a trilha vivem só em variáveis desta
 * função e somem ao parar. Nada é gravado (sem localStorage, IndexedDB, cookie, arquivo) nem impresso
 * (sem console), e a única saída é o POST para /api/orientacoes. O teste orientacao-privacidade.test.ts
 * varre os módulos desta tela atrás disso.
 *
 * SILÊNCIO: o app só mostra e fala o `mensagem.texto` que a API devolve; não inventa direção.
 * O mapa não anima (animate: false) e só acompanha a pessoa dentro do campus (ver dentroDoCampus).
 */
import L from "leaflet";
import { TAMANHO_ICONE_POSICAO_PX, htmlMarcadorPosicao } from "../mapa/marcadores.ts";
import { enfileirarFala, falar, type FalaDeVoz, type LeituraEmCurso, type PreferenciasDeVoz, type SinteseDeVoz } from "../rotas/voz.ts";
import type { RotaResposta } from "../rotas/tipos.ts";
import type { Orientacao } from "../a11y/localizacao.ts";
import {
  TELA_AO_VIVO,
  TEXTO_ENCERRADA,
  TEXTO_GPS_PERDIDO,
  TEXTO_SEM_BUSSOLA,
  TEXTO_SEM_GEOLOCALIZACAO,
  TEXTO_SEM_MENSAGEM,
  RESULTADO_SEM_REDE,
  ROTULO_AGUARDANDO,
  ROTULO_PARADA,
  ROTULOS,
  apresentacaoSemGps,
  dentroDoCampus,
  interpretarResposta,
  resultadoDoErroDeGps,
  telaAoParar,
  type Apresentacao,
  type EstadoDaOrientacao,
} from "../orientacao/apresentacao.ts";
import { JanelaDeBussola, deveEnviar, gpsPerdido, lerEventoDeOrientacao, montarRequisicao, type EventoDeOrientacao } from "../orientacao/requisicao.ts";
import { Recentes, Trilha, type Fix } from "../orientacao/trilha.ts";

function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id);
  if (!e) throw new Error(`Falta o elemento #${id} em index.html`);
  return e as T;
}

interface OrientacaoComIos extends EventoDeOrientacao {
  type?: string;
}
type ClasseDeOrientacao = typeof DeviceOrientationEvent & { requestPermission?: () => Promise<"granted" | "denied"> };
interface TravaDeTela {
  release(): Promise<void>;
}
type NavegadorComTrava = Navigator & { wakeLock?: { request(tipo: "screen"): Promise<TravaDeTela> } };

export interface DependenciasAoVivo {
  mapa: L.Map | null;
  orientacao: Orientacao;
  sintese: SinteseDeVoz | null;
  /** Voz e velocidade escolhidas em Ajustes (lidas a cada fala). */
  preferencias: () => PreferenciasDeVoz;
  /** A rota traçada (não a simulação); null se não há. */
  rota: () => RotaResposta | null;
  /** Antes de começar: tira a simulação e a leitura em voz do caminho. */
  aoComecar: () => void;
}

const ESTADOS_CSS: Record<EstadoDaOrientacao, string> = {
  na_rota: "ao-vivo__estado--na-rota",
  fora_da_rota: "ao-vivo__estado--fora",
  precisao_insuficiente: "ao-vivo__estado--sem-gps",
  chegou: "ao-vivo__estado--chegou",
};

export function iniciarOrientacaoAoVivo(deps: DependenciasAoVivo): void {
  const { mapa, orientacao, sintese } = deps;
  const botaoIniciar = el<HTMLButtonElement>("botao-orientacao-iniciar");
  const tela = el("tela-orientacao");
  const titulo = el("titulo-orientacao");
  const botaoParar = el<HTMLButtonElement>("botao-orientacao-parar");
  const caixaEstado = el("estado-orientacao");
  const simbolo = el("simbolo-orientacao");
  const rotuloEstado = el("rotulo-estado-orientacao");
  const distancia = el("distancia-orientacao");
  const ultimaMensagem = el("mensagem-orientacao");
  const status = el("status-orientacao");
  const regiaoUrgente = el("alerta-orientacao");
  const regiaoPolida = el("anuncio-rota");
  const formulario = el("form-rota");
  const resultado = el("resultado-rota");
  const tituloResultado = el("titulo-resultado");

  // Estado da sessão: tudo aqui some em parar().
  let ativa = false;
  let sessao = 0;
  let idGps: number | null = null;
  let idCiclo: number | null = null;
  let fix: Fix | null = null;
  let ultimoEnvio_ms: number | null = null;
  let emVoo: AbortController | null = null;
  let gpsPerdidoMostrado = false;
  let trilha = new Trilha();
  let recentes = new Recentes();
  const bussola = new JanelaDeBussola();
  let eventoBussola: string | null = null;
  let travaDeTela: TravaDeTela | null = null;
  let marcador: L.Marker | null = null;
  let leitura: LeituraEmCurso | null = null;
  let rotaDaSessao: RotaResposta | null = null;
  let avisoDaBussola: string | null = null;
  let ultimaMensagemAnunciada: string | null = null;

  const criarFala = (texto: string): FalaDeVoz => new SpeechSynthesisUtterance(texto) as unknown as FalaDeVoz;

  function mostrarStatus(texto: string | null): void {
    const t = texto ?? avisoDaBussola;
    status.textContent = t ?? "";
    status.hidden = t === null;
  }

  function anunciarPolido(texto: string): void {
    regiaoPolida.textContent = "";
    window.setTimeout(() => {
      regiaoPolida.textContent = texto;
    }, 60);
  }

  function anunciarUrgente(texto: string): void {
    regiaoUrgente.textContent = "";
    window.setTimeout(() => {
      regiaoUrgente.textContent = texto;
    }, 60);
  }

  function vibrar(padrao: number[]): void {
    if (padrao.length === 0) return;
    try {
      if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") navigator.vibrate(padrao);
    } catch {
      /* iPhone não vibra: a informação já está no texto */
    }
  }

  /** Mostra o estado (palavra + forma + borda; nunca só cor), a distância e a última mensagem. */
  function desenhar(a: Apresentacao | null, vazio: "aguardando" | "parada" = "aguardando"): void {
    const estado: EstadoDaOrientacao = a?.estado ?? "precisao_insuficiente";
    for (const classe of Object.values(ESTADOS_CSS)) caixaEstado.classList.remove(classe);
    caixaEstado.classList.add(ESTADOS_CSS[estado]);
    simbolo.textContent = a ? ROTULOS[estado].simbolo : vazio === "parada" ? ROTULO_PARADA.simbolo : ROTULOS[estado].simbolo;
    rotuloEstado.textContent = a ? a.rotulo : vazio === "parada" ? ROTULO_PARADA.rotulo : ROTULO_AGUARDANDO;
    distancia.textContent = a?.distanciaTexto ?? "";
    distancia.hidden = !a?.distanciaTexto;
    if (a?.mensagem) ultimaMensagem.textContent = a.mensagem.texto;
  }

  /** Mensagem da API: região aria-live (assertive se urgente, polite nas outras), voz do site se ligada, vibração. */
  function dizer(a: Apresentacao): void {
    const texto = a.textoParaDizer;
    if (texto === "") return;
    if (a.urgente) anunciarUrgente(texto);
    else anunciarPolido(texto);
    if (sintese && orientacao.vozAtiva()) {
      const opcoes = { sintese, criarFala, preferencias: deps.preferencias() };
      if (a.urgente || a.chegou) {
        // Urgente cancela a fala anterior (falar() cancela antes de falar).
        leitura = falar([texto], opcoes);
      } else if (!enfileirarFala(texto, opcoes)) {
        leitura = falar([texto], opcoes);
      }
    }
    vibrar(a.vibrar);
  }

  // ---------- ciclo de envio ----------

  async function enviar(): Promise<void> {
    const rota = rotaDaSessao;
    const agora_ms = Date.now();
    if (!ativa || !rota || !fix) return;
    const pedido = montarRequisicao({
      origem_id: rota.origem.id,
      destino_id: rota.destino.id,
      perfil: rota.perfil,
      fix,
      bussola: bussola.resumo(agora_ms),
      trilha: trilha.paraEnvio(fix),
      recentes: recentes.paraEnvio(agora_ms),
    });
    if (!pedido) return;
    const minhaSessao = sessao;
    const controle = new AbortController();
    emVoo = controle;
    ultimoEnvio_ms = agora_ms;
    let resultado;
    try {
      const resposta = await fetch(pedido.url, { ...pedido.init, signal: controle.signal, cache: "no-store" });
      let corpo: unknown = null;
      try {
        corpo = await resposta.json();
      } catch {
        corpo = null;
      }
      resultado = interpretarResposta(resposta.status, corpo);
    } catch {
      resultado = RESULTADO_SEM_REDE;
    }
    if (minhaSessao !== sessao || !ativa) return; // parou enquanto esperava: a resposta é descartada
    emVoo = null;
    if (resultado.tipo === "erro") {
      mostrarStatus(resultado.mensagem);
      if (resultado.parar) {
        encerrarRecursos();
        desenhar(null, "parada");
        anunciarPolido(resultado.mensagem);
      } else if (resultado.motivo === "rede" || resultado.motivo === "servidor") {
        anunciarSeMudou(resultado.mensagem);
      }
      return;
    }
    const a = resultado.apresentacao;
    mostrarStatus(null);
    ultimaMensagemAnunciada = null;
    gpsPerdidoMostrado = false;
    desenhar(a);
    if (a.mensagem) recentes.registrar(a.mensagem.chave, Date.now());
    dizer(a);
    if (a.chegou) {
      encerrarRecursos(false);
      mostrarStatus(`${TEXTO_ENCERRADA}: você chegou. Toque em Parar orientação para voltar.`);
    }
  }

  /** Aviso do próprio app (sem conexão, sem GPS): anuncia só quando muda, para não repetir a cada ciclo. */
  function anunciarSeMudou(texto: string): void {
    if (ultimaMensagemAnunciada === texto) return;
    ultimaMensagemAnunciada = texto;
    anunciarPolido(texto);
  }

  function ciclo(): void {
    const agora_ms = Date.now();
    if (gpsPerdido(fix, agora_ms)) {
      if (fix !== null && !gpsPerdidoMostrado) {
        gpsPerdidoMostrado = true;
        desenhar(apresentacaoSemGps());
        mostrarStatus(TEXTO_GPS_PERDIDO);
        anunciarSeMudou(TEXTO_GPS_PERDIDO);
      }
      return;
    }
    if (deveEnviar({ agora_ms, ultimoEnvio_ms, emVoo: emVoo !== null, fix })) void enviar();
  }

  // ---------- GPS ----------

  function aoPosicao(p: GeolocationPosition): void {
    if (!ativa) return;
    const novo: Fix = { lat: p.coords.latitude, lon: p.coords.longitude, precisao_m: p.coords.accuracy, instante_ms: Date.now() };
    fix = novo;
    trilha.adicionar(novo);
    moverMarcador(novo);
  }

  function aoErroDeGps(e: GeolocationPositionError): void {
    if (!ativa) return;
    const r = resultadoDoErroDeGps(e.code);
    mostrarStatus(r.mensagem);
    desenhar(apresentacaoSemGps());
    anunciarSeMudou(r.mensagem);
    if (r.parar) {
      encerrarRecursos();
      desenhar(null, "parada");
    }
  }

  function moverMarcador(f: Fix): void {
    if (!mapa || !dentroDoCampus(f.lat, f.lon)) return;
    try {
      const ll = L.latLng(f.lat, f.lon);
      if (marcador) marcador.setLatLng(ll);
      else {
        const metade = TAMANHO_ICONE_POSICAO_PX / 2;
        marcador = L.marker(ll, {
          keyboard: false,
          interactive: false,
          icon: L.divIcon({ className: "", html: htmlMarcadorPosicao(null), iconSize: [TAMANHO_ICONE_POSICAO_PX, TAMANHO_ICONE_POSICAO_PX], iconAnchor: [metade, metade] }),
        }).addTo(mapa);
      }
      mapa.setView(ll, 19, { animate: false });
    } catch {
      /* o mapa é só referência */
    }
  }

  // ---------- bússola ----------

  function aoOrientar(ev: Event): void {
    if (!ativa) return;
    const leituraDeBussola = lerEventoDeOrientacao(ev as unknown as OrientacaoComIos);
    if (leituraDeBussola) bussola.adicionar(leituraDeBussola.rumo_graus, Date.now());
  }

  /** iPhone pede permissão por toque; Android manda o evento absoluto. Sem nenhum dos dois: segue sem bússola. */
  async function ligarBussola(minhaSessao: number): Promise<void> {
    if (typeof DeviceOrientationEvent === "undefined") {
      avisoDaBussola = TEXTO_SEM_BUSSOLA;
      mostrarStatus(null);
      return;
    }
    const classe = DeviceOrientationEvent as ClasseDeOrientacao;
    if (typeof classe.requestPermission === "function") {
      try {
        const r = await classe.requestPermission();
        if (r !== "granted") {
          if (minhaSessao === sessao && ativa) {
            avisoDaBussola = TEXTO_SEM_BUSSOLA;
            mostrarStatus(null);
          }
          return;
        }
      } catch {
        if (minhaSessao === sessao && ativa) {
            avisoDaBussola = TEXTO_SEM_BUSSOLA;
            mostrarStatus(null);
          }
        return;
      }
    }
    if (minhaSessao !== sessao || !ativa) return;
    eventoBussola = "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
    window.addEventListener(eventoBussola, aoOrientar);
  }

  // ---------- manter a tela acesa ----------

  async function pedirTrava(): Promise<void> {
    try {
      const nav = navigator as NavegadorComTrava;
      if (!nav.wakeLock) return;
      const trava = await nav.wakeLock.request("screen");
      if (!ativa) {
        void trava.release().catch(() => {});
        return;
      }
      travaDeTela = trava;
    } catch {
      /* sem trava: a tela pode apagar; a orientação continua enquanto o navegador deixar */
    }
  }

  function aoMudarVisibilidade(): void {
    // O navegador solta a trava quando a página some; ao voltar, pede de novo.
    if (ativa && document.visibilityState === "visible") void pedirTrava();
  }

  // ---------- começar e parar ----------

  /** Solta GPS, ciclo, bússola, trava, pedido em voo, fala, trilha, recentes e marcador. A tela continua aberta. */
  function encerrarRecursos(cancelarFala = true): void {
    ativa = false;
    sessao += 1;
    if (idGps !== null && typeof navigator !== "undefined" && navigator.geolocation) navigator.geolocation.clearWatch(idGps);
    idGps = null;
    if (idCiclo !== null) window.clearInterval(idCiclo);
    idCiclo = null;
    if (eventoBussola) window.removeEventListener(eventoBussola, aoOrientar);
    eventoBussola = null;
    document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    window.removeEventListener("pagehide", aoSairDaPagina);
    emVoo?.abort();
    emVoo = null;
    const trava = travaDeTela;
    travaDeTela = null;
    if (trava) void trava.release().catch(() => {});
    if (cancelarFala) {
      leitura?.parar();
      leitura = null;
    }
    trilha.limpar();
    recentes.limpar();
    bussola.limpar();
    fix = null;
    ultimoEnvio_ms = null;
    marcador?.remove();
    marcador = null;
  }

  function aoSairDaPagina(): void {
    encerrarRecursos();
  }

  function comecar(): void {
    const rota = deps.rota();
    if (!rota || ativa) return;
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resultado.hidden = true;
      formulario.hidden = true;
      abrirTela();
      mostrarStatus(TEXTO_SEM_GEOLOCALIZACAO);
      desenhar(null, "parada");
      return;
    }
    deps.aoComecar();
    rotaDaSessao = rota;
    trilha = new Trilha();
    recentes = new Recentes();
    ativa = true;
    sessao += 1;
    ultimoEnvio_ms = null;
    gpsPerdidoMostrado = false;
    ultimaMensagemAnunciada = null;
    avisoDaBussola = null;
    abrirTela();
    // Tudo isto ainda dentro do toque: o iPhone só libera GPS, bússola e voz dentro do gesto.
    idGps = navigator.geolocation.watchPosition(aoPosicao, aoErroDeGps, { enableHighAccuracy: true, maximumAge: 0, timeout: 20_000 });
    const minhaSessao = sessao;
    void ligarBussola(minhaSessao);
    void pedirTrava();
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    window.addEventListener("pagehide", aoSairDaPagina);
    idCiclo = window.setInterval(ciclo, 500);
  }

  function abrirTela(): void {
    formulario.hidden = true;
    resultado.hidden = true;
    tela.hidden = false;
    desenhar(null);
    ultimaMensagem.textContent = TEXTO_SEM_MENSAGEM;
    mostrarStatus(null);
    regiaoUrgente.textContent = "";
    orientacao.mudarDeTela(TELA_AO_VIVO);
    titulo.focus();
  }

  function parar(): void {
    const rota = rotaDaSessao ?? deps.rota();
    encerrarRecursos();
    avisoDaBussola = null;
    rotaDaSessao = null;
    tela.hidden = true;
    regiaoUrgente.textContent = "";
    mostrarStatus(null);
    formulario.hidden = false;
    resultado.hidden = false;
    // Título "Rota traçada ..." e UM anúncio: "Orientação encerrada. ..." (a frase já traz o resumo da rota).
    if (rota) orientacao.mudarDeTela(telaAoParar(rota));
    else anunciarPolido(`${TEXTO_ENCERRADA}.`);
    tituloResultado.focus();
  }

  botaoIniciar.addEventListener("click", comecar);
  botaoParar.addEventListener("click", parar);
}
