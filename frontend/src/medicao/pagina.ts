/*
 * Tela da página de medição de GPS (medicao.html), fluxo guiado: ponto N de 12, medição N de 3,
 * contagem de 30 s parado, envio em tempo real para a equipe. Liga a lógica pura (medicao.ts,
 * fluxo.ts, fila.ts, mapa/) às APIs do navegador: geolocalização, orientação do aparelho,
 * vibração, localStorage, fetch e download do CSV.
 * A posição medida aqui é a dos celulares DA EQUIPE nos pontos de controle; a posição de quem
 * navega continua nunca sendo gravada.
 */
import "../estilos.css";
import "./medicao.css";
import "../mapa/marcadores.css";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { iniciarSeletorTema } from "../design/seletor-tema.ts";
import { TAMANHO_ICONE_POSICAO_PX, htmlMarcadorPosicao } from "../mapa/marcadores.ts";
import { rumoParaSeta } from "../mapa/rumo.ts";
import { FilaEnvio, type FetchSimulavel, type ItemFila, type ResultadoRodada } from "./fila.ts";
import {
  DURACAO_CONTAGEM_S,
  MEDICOES_POR_PONTO,
  TOTAL_PONTOS,
  classificarPrecisao,
  descreverEnvio,
  formatarMetros,
  fracaoContagem,
  medicoesFeitas,
  numeroDaProximaMedicao,
  pontosCompletos,
  proximoPonto,
  segmentosProgresso,
  segundosRestantes,
  textoMedicao,
  textoPrecisao,
  textoProgresso,
} from "./fluxo.ts";
import {
  ROTULO_CONDICAO,
  gerarCsv,
  montarRegistroBussola,
  montarRegistroPosicao,
  montarRegistroVibracao,
  nomeArquivoCsv,
  oscilacaoBussola,
  podeGravarTrajeto,
  type Condicao,
  type PosicaoMedida,
  type Registro,
} from "./medicao.ts";

const CHAVE_FILA = "msb-medicao-fila";
const CHAVE_REGISTROS_ANTIGA = "msb-medicao-registros";
const CHAVE_APARELHO = "msb-medicao-aparelho";
const CHAVE_CODIGO = "msb-medicao-codigo";
const CHAVE_PONTO = "msb-medicao-ponto-atual";
const CHAVE_CONDICAO = "msb-medicao-condicao";
const TIMEOUT_POSICAO_MS = 30000;
const MAX_ULTIMOS = 6;

// Centro aproximado do campus (confirmar com o mapeamento): só o mapa inicial, antes do primeiro fix.
const CENTRO_CAMPUS: L.LatLngTuple = [-23.5475, -46.6522];

function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id);
  if (!e) throw new Error(`Elemento #${id} não encontrado`);
  return e as T;
}

/** Só troca o texto quando mudou: região aria-live não anuncia de novo o que continua igual. */
function texto(e: HTMLElement, valor: string): void {
  if (e.textContent !== valor) e.textContent = valor;
}

const campoAparelho = el<HTMLInputElement>("campo-aparelho");
const campoCodigo = el<HTMLInputElement>("campo-codigo");
const campoPonto = el<HTMLInputElement>("campo-ponto");
const campoCondicao = el<HTMLSelectElement>("campo-condicao");
const campoObservacao = el<HTMLInputElement>("campo-observacao");
const detalhesConfig = el<HTMLDetailsElement>("config");
const resumoConfig = el<HTMLElement>("resumo-config");
const codigoSalvo = el<HTMLParagraphElement>("codigo-salvo");
const codigoEdicao = el<HTMLDivElement>("codigo-edicao");
const botaoSalvarCodigo = el<HTMLButtonElement>("botao-salvar-codigo");
const botaoTrocarCodigo = el<HTMLButtonElement>("botao-trocar-codigo");
const tituloPonto = el<HTMLElement>("titulo-ponto");
const tituloMedicao = el<HTMLElement>("titulo-medicao");
const progresso = el<HTMLDivElement>("progresso");
const faixaTrajeto = el<HTMLDivElement>("faixa-trajeto");
const statusTrajeto = el<HTMLParagraphElement>("status-trajeto");
const botaoPararTrajeto = el<HTMLButtonElement>("botao-parar-trajeto");
const vistaMedir = el<HTMLDivElement>("vista-medir");
const vistaConfirmar = el<HTMLDivElement>("vista-confirmar");
const painelPrecisao = el<HTMLDivElement>("painel-precisao");
const precisaoValor = el<HTMLElement>("precisao-valor");
const precisaoNivel = el<HTMLElement>("precisao-nivel");
const contagemValor = el<HTMLElement>("contagem-valor");
const contagemBarra = el<HTMLDivElement>("contagem-barra");
const botaoContagem = el<HTMLButtonElement>("botao-contagem");
const dicaMedicao = el<HTMLParagraphElement>("dica-medicao");
const estadoEnvio = el<HTMLParagraphElement>("estado-envio");
const painelBussola = el<HTMLElement>("painel-bussola");
const botaoBussola = el<HTMLButtonElement>("botao-bussola");
const botaoRegistrarBussola = el<HTMLButtonElement>("botao-registrar-bussola");
const leituraBussola = el<HTMLParagraphElement>("leitura-bussola");
const statusBussola = el<HTMLParagraphElement>("status-bussola");
const botaoVibrar = el<HTMLButtonElement>("botao-vibrar");
const statusVibracao = el<HTMLParagraphElement>("status-vibracao");
const cartaoEstado = el<HTMLDivElement>("cartao-estado");
const cartaoIcone = el<HTMLElement>("cartao-icone");
const cartaoTitulo = el<HTMLElement>("cartao-titulo");
const cartaoDetalhe = el<HTMLElement>("cartao-detalhe");
const cartaoFila = el<HTMLDivElement>("cartao-fila");
const filaIcone = el<HTMLElement>("fila-icone");
const filaTitulo = el<HTMLElement>("fila-titulo");
const filaDetalhe = el<HTMLElement>("fila-detalhe");
const botaoProximo = el<HTMLButtonElement>("botao-proximo");
const textoProximo = el<HTMLElement>("texto-proximo");
const contagemRegistros = el<HTMLParagraphElement>("contagem-registros");
const listaRegistros = el<HTMLOListElement>("lista-registros");
const barraMedir = el<HTMLDivElement>("barra-medir");
const barraConfirmar = el<HTMLDivElement>("barra-confirmar");
const botaoRegistrar = el<HTMLButtonElement>("botao-registrar");
const botaoAbrirBussola = el<HTMLButtonElement>("botao-abrir-bussola");
const botaoPular = el<HTMLButtonElement>("botao-pular");
const statusPonto = el<HTMLParagraphElement>("status-ponto");
const botaoTrajeto = el<HTMLButtonElement>("botao-trajeto");
const botaoExportar = el<HTMLButtonElement>("botao-exportar");
const botaoApagar = el<HTMLButtonElement>("botao-apagar");
const botaoApagarSim = el<HTMLButtonElement>("botao-apagar-sim");
const botaoApagarNao = el<HTMLButtonElement>("botao-apagar-nao");
const caixaConfirmar = el<HTMLDivElement>("confirmar-apagar");
const textoConfirmar = el<HTMLParagraphElement>("texto-confirmar");
const statusRegistros = el<HTMLParagraphElement>("status-registros");

// ---------- armazenamento local ----------

function lerLocal(chave: string): string {
  try {
    return localStorage.getItem(chave) ?? "";
  } catch {
    return "";
  }
}

function gravarLocal(chave: string, valor: string): void {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    /* sem localStorage: o campo continua funcionando, só não é lembrado */
  }
}

const armazenamentoFila = {
  ler: (): string | null => {
    try {
      return localStorage.getItem(CHAVE_FILA);
    } catch {
      return null;
    }
  },
  gravar: (v: string): void => localStorage.setItem(CHAVE_FILA, v),
};

const fetchDaPagina: FetchSimulavel = async (url, init) => {
  const r = await fetch(url, init);
  return { status: r.status, json: () => r.json() as Promise<unknown> };
};

const codigoDaEquipe = (): string => lerLocal(CHAVE_CODIGO).trim();

const fila = new FilaEnvio({
  armazenamento: armazenamentoFila,
  fetch: fetchDaPagina,
  codigo: codigoDaEquipe,
});

/** Registros de antes da fila (chave antiga) entram na fila para não se perderem. */
function migrarRegistrosAntigos(): void {
  try {
    const bruto = localStorage.getItem(CHAVE_REGISTROS_ANTIGA);
    if (!bruto) return;
    const lido: unknown = JSON.parse(bruto);
    if (Array.isArray(lido) && lido.length > 0) fila.importarLegado(lido as Registro[]);
    localStorage.removeItem(CHAVE_REGISTROS_ANTIGA);
  } catch {
    /* lixo na chave antiga: ignora */
  }
}

// ---------- estado do fluxo ----------

let pontoAtual = 1;
let vista: "medir" | "confirmar" = "medir";
/** Último ponto registrado nesta tela (para a vista de confirmação). */
let ultimo: { ponto: number; medicao: number; id_cliente: string } | null = null;
let ultimaPosicao: PosicaoMedida | null = null;
let registrando = false;

const aparelho = (): string => campoAparelho.value.trim();
const condicaoInformada = (): Condicao => campoCondicao.value as Condicao;
const online = (): boolean => navigator.onLine !== false;

function pontoValido(valor: string): number | null {
  const n = Number(valor);
  return Number.isInteger(n) && n >= 1 && n <= TOTAL_PONTOS ? n : null;
}

function definirPonto(n: number): void {
  pontoAtual = n;
  campoPonto.value = String(n);
  gravarLocal(CHAVE_PONTO, String(n));
}

// ---------- desenho ----------

function itemDaFila(id_cliente: string): ItemFila | undefined {
  return fila.itens.find((i) => i.id_cliente === id_cliente);
}

function desenharCabecalho(): void {
  const registros = fila.registros();
  const ap = aparelho();
  let ponto = pontoAtual;
  let medicao = numeroDaProximaMedicao(registros, pontoAtual, ap);
  if (vista === "confirmar" && ultimo) {
    ponto = ultimo.ponto;
    medicao = ultimo.medicao;
  }
  texto(tituloPonto, `Ponto ${ponto} de ${TOTAL_PONTOS}`);
  texto(tituloMedicao, textoMedicao(medicao));

  const segmentos = segmentosProgresso(registros, ap, ponto);
  const filhos = progresso.children;
  segmentos.forEach((s, i) => {
    const filho = filhos[i];
    if (!filho) return;
    filho.setAttribute("data-completo", String(s.completo));
    filho.setAttribute("data-atual", String(s.atual));
  });
  progresso.setAttribute("aria-valuenow", String(pontosCompletos(segmentos)));
  progresso.setAttribute("aria-valuetext", textoProgresso(segmentos));

  const rotuloCondicao = ROTULO_CONDICAO[condicaoInformada()];
  texto(
    resumoConfig,
    `${ap || "Aparelho sem nome"} · ${codigoDaEquipe() ? "código salvo" : "sem código"} · ${rotuloCondicao}`,
  );
}

function textoEstadoEnvio(): string {
  if (fila.itens.length === 0) return "";
  const c = fila.contagem();
  const partes: string[] = [];
  if (!codigoDaEquipe()) partes.push("Não enviado: falta o código da equipe");
  else if (c.na_fila > 0) {
    const motivo = fila.pendentes()[0]?.motivo ?? (online() ? null : "sem sinal");
    partes.push(`◆ ${c.na_fila} na fila${motivo ? `: ${motivo}` : ""}`);
  } else if (c.enviado > 0) partes.push("✓ Tudo enviado para a equipe");
  if (c.recusado > 0) {
    const motivo = fila.itens.find((i) => i.estado === "recusado")?.motivo;
    partes.push(`✕ ${c.recusado} recusado${c.recusado > 1 ? "s" : ""}${motivo ? `: ${motivo}` : ""}`);
  }
  return partes.join(" · ");
}

function rotuloItem(item: ItemFila, registros: readonly Registro[]): { nome: string; valor: string } {
  const r = item.registro;
  if (r.tipo === "ponto") {
    const antes = registros.slice(0, registros.indexOf(r));
    const n = medicoesFeitas(antes, r.ponto ?? 0, r.aparelho) + 1;
    return { nome: `Ponto ${r.ponto} · medição ${n}`, valor: formatarMetros(r.precisao_m) };
  }
  if (r.tipo === "bussola") return { nome: `Bússola ${Math.round(r.bussola_rumo_graus ?? 0)}°`, valor: "teste" };
  if (r.tipo === "vibracao") return { nome: "Vibração", valor: "teste" };
  return { nome: "Trajeto", valor: formatarMetros(r.precisao_m) };
}

function desenharConfirmacao(): void {
  const temCodigo = codigoDaEquipe() !== "";
  const registros = fila.registros();
  const c = fila.contagem();
  const doUltimo = ultimo ? itemDaFila(ultimo.id_cliente) : undefined;

  if (ultimo && doUltimo) {
    const t = descreverEnvio({ estado: doUltimo.estado, motivo: doUltimo.motivo, temCodigo, online: online() });
    cartaoEstado.setAttribute("data-estado", t.cartao);
    texto(cartaoIcone, t.icone);
    texto(cartaoTitulo, t.titulo);
    const feitas = medicoesFeitas(registros, ultimo.ponto, aparelho());
    const completo = feitas >= MEDICOES_POR_PONTO;
    const detalhe =
      `Ponto ${ultimo.ponto} ${completo ? "completo" : "em andamento"} · ${Math.min(feitas, MEDICOES_POR_PONTO)} de ${MEDICOES_POR_PONTO} medições · ${formatarMetros(doUltimo.registro.precisao_m)}` +
      (t.cartao === "fila" ? ". Envio automático quando der." : "") +
      (doUltimo.recusado_por_codigo ? ". Corrija o código da equipe nas configurações acima." : "");
    texto(cartaoDetalhe, detalhe);

    const outrosNaFila = c.na_fila - (doUltimo.estado === "na_fila" ? 1 : 0);
    const outrosRecusados = c.recusado - (doUltimo.estado === "recusado" ? 1 : 0);
    if (outrosNaFila > 0) {
      cartaoFila.hidden = false;
      cartaoFila.setAttribute("data-estado", "fila");
      texto(filaIcone, String(outrosNaFila));
      texto(filaTitulo, temCodigo ? "Na fila, sem sinal" : "Não enviados: falta o código da equipe");
      texto(
        filaDetalhe,
        `${outrosNaFila} registro${outrosNaFila > 1 ? "s" : ""} esperando envio. Envio automático quando voltar.`,
      );
    } else if (outrosRecusados > 0) {
      cartaoFila.hidden = false;
      cartaoFila.setAttribute("data-estado", "recusado");
      texto(filaIcone, "✕");
      texto(
        filaTitulo,
        `${outrosRecusados} registro${outrosRecusados > 1 ? "s" : ""} recusado${outrosRecusados > 1 ? "s" : ""}`,
      );
      texto(filaDetalhe, fila.itens.find((i) => i.estado === "recusado")?.motivo ?? "");
    } else {
      cartaoFila.hidden = true;
    }

    const seguinte = proximoPonto(ultimo.ponto);
    if (feitas < MEDICOES_POR_PONTO) {
      botaoProximo.hidden = false;
      texto(textoProximo, `Próxima medição (${feitas + 1} de ${MEDICOES_POR_PONTO}) neste ponto`);
    } else if (seguinte !== null) {
      botaoProximo.hidden = false;
      texto(textoProximo, `Ir para o ponto ${seguinte}`);
    } else {
      botaoProximo.hidden = true;
    }
  }

  const pontos = registros.filter((r) => r.tipo === "ponto").length;
  const trajeto = registros.filter((r) => r.tipo === "trajeto").length;
  texto(
    contagemRegistros,
    `${registros.length} registros (${pontos} de ponto, ${trajeto} de trajeto, ${registros.length - pontos - trajeto} de teste): ` +
      `${c.enviado} enviados, ${c.na_fila} na fila, ${c.recusado} recusados.` +
      (fila.armazenamentoFunciona
        ? ""
        : " Atenção: este navegador não está guardando os registros; exporte o CSV antes de recarregar."),
  );

  const itens = fila.itens.filter((i) => i.registro.tipo !== "trajeto").slice(-MAX_ULTIMOS).reverse();
  const novos = itens.map((item) => {
    const { nome, valor } = rotuloItem(item, registros);
    const t = descreverEnvio({ estado: item.estado, motivo: item.motivo, temCodigo, online: online() });
    const li = document.createElement("li");
    const esq = document.createElement("span");
    esq.textContent = nome;
    const dir = document.createElement("span");
    const v = document.createElement("span");
    v.className = "medicao__item-valor";
    v.textContent = valor;
    const est = document.createElement("span");
    est.className = "medicao__item-estado";
    est.setAttribute("data-estado", item.estado);
    est.textContent = ` ${t.curto}`;
    dir.append(v, est);
    li.append(esq, dir);
    return li;
  });
  listaRegistros.replaceChildren(...novos);
}

function desenharCodigo(): void {
  const tem = codigoDaEquipe() !== "";
  codigoSalvo.hidden = !tem;
  codigoEdicao.hidden = tem;
}

function desenhar(): void {
  desenharCabecalho();
  texto(estadoEnvio, textoEstadoEnvio());
  desenharConfirmacao();
  desenharCodigo();
}

function mostrarVista(nova: "medir" | "confirmar"): void {
  vista = nova;
  vistaMedir.hidden = nova !== "medir";
  vistaConfirmar.hidden = nova !== "confirmar";
  barraMedir.hidden = nova !== "medir";
  barraConfirmar.hidden = nova !== "confirmar";
  desenhar();
  if (nova === "medir") mapa?.invalidateSize();
}

// ---------- mapa pequeno ----------

let mapa: L.Map | null = null;
let marcador: L.Marker | null = null;
let halo: L.Circle | null = null;
let rumoDoMarcador: number | null | undefined;

function iniciarMapa(): void {
  try {
    mapa = L.map(el("mapa-medicao"), { center: CENTRO_CAMPUS, zoom: 17, minZoom: 15, maxZoom: 19 });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>',
    }).addTo(mapa);
  } catch {
    mapa = null;
    el("mapa-medicao").hidden = true;
    el("mapa-indisponivel").hidden = false;
  }
}

function iconePosicao(rumo_graus: number | null): L.DivIcon {
  const metade = TAMANHO_ICONE_POSICAO_PX / 2;
  return L.divIcon({
    className: "",
    html: htmlMarcadorPosicao(rumo_graus),
    iconSize: [TAMANHO_ICONE_POSICAO_PX, TAMANHO_ICONE_POSICAO_PX],
    iconAnchor: [metade, metade],
  });
}

function rumoAtual(): number | null {
  return rumoParaSeta({
    rumo_gps_graus: ultimaPosicao?.heading ?? null,
    velocidade_ms: ultimaPosicao?.speed ?? null,
    bussola: ultimaLeitura,
  });
}

/** Bola + halo (L.circle com raio = precisão em metros) + seta só quando o rumo é conhecido. */
function atualizarMapa(): void {
  if (!mapa || !ultimaPosicao) return;
  const p = ultimaPosicao;
  const ll = L.latLng(p.latitude, p.longitude);
  const rumo = rumoAtual();
  if (!halo || !marcador) {
    halo = L.circle(ll, { radius: p.accuracy, className: "mapa-halo", interactive: false }).addTo(mapa);
    marcador = L.marker(ll, { icon: iconePosicao(rumo), interactive: false, keyboard: false }).addTo(mapa);
    rumoDoMarcador = rumo;
    mapa.fitBounds(halo.getBounds(), { maxZoom: 19, padding: [20, 20], animate: false });
    return;
  }
  halo.setLatLng(ll);
  halo.setRadius(p.accuracy);
  marcador.setLatLng(ll);
  if (rumo !== rumoDoMarcador) {
    marcador.setIcon(iconePosicao(rumo));
    rumoDoMarcador = rumo;
  }
  if (!mapa.getBounds().contains(ll)) mapa.panTo(ll);
}

// ---------- posição (uma vigia só, usada pelo painel, pelo mapa e pelo trajeto) ----------

let trajetoLigado = false;
let ultimoTrajeto_ms: number | null = null;
let gravadosNoTrajeto = 0;

function mensagemErroPosicao(e: GeolocationPositionError): string {
  if (e.code === e.PERMISSION_DENIED) return "Permissão de localização negada. Libere nas configurações do navegador.";
  if (e.code === e.POSITION_UNAVAILABLE) return "Posição indisponível agora. Tente de novo em campo aberto.";
  if (e.code === e.TIMEOUT) return "Demorou demais para obter a posição (30 s). Tente de novo.";
  return "Erro ao obter a posição.";
}

function posicaoMedida(p: GeolocationPosition): PosicaoMedida {
  const c = p.coords;
  return {
    latitude: c.latitude,
    longitude: c.longitude,
    accuracy: c.accuracy,
    altitude: c.altitude,
    altitudeAccuracy: c.altitudeAccuracy,
    speed: c.speed,
    heading: c.heading,
  };
}

function desenharPrecisao(precisao_m: number | null): void {
  texto(precisaoValor, formatarMetros(precisao_m));
  texto(precisaoNivel, textoPrecisao(precisao_m));
  painelPrecisao.setAttribute("data-nivel", classificarPrecisao(precisao_m) ?? "");
}

function aoReceberPosicao(p: GeolocationPosition): void {
  ultimaPosicao = posicaoMedida(p);
  desenharPrecisao(ultimaPosicao.accuracy);
  atualizarMapa();
  if (trajetoLigado) gravarTrajeto(ultimaPosicao);
}

function iniciarVigia(): void {
  if (!("geolocation" in navigator)) {
    texto(precisaoNivel, "Este navegador não tem geolocalização");
    return;
  }
  navigator.geolocation.watchPosition(
    aoReceberPosicao,
    (e) => {
      texto(precisaoNivel, mensagemErroPosicao(e));
      if (trajetoLigado) texto(statusTrajeto, `${mensagemErroPosicao(e)} O trajeto continua tentando.`);
    },
    { enableHighAccuracy: true, maximumAge: 0, timeout: TIMEOUT_POSICAO_MS },
  );
}

// ---------- contagem de 30 s ----------

let contagemInicio_ms: number | null = null;
let relogioContagem: number | null = null;
let ultimoAvisoContagem_s = -1;

function desenharContagem(restantes_s: number): void {
  texto(contagemValor, `${restantes_s} s`);
  contagemBarra.style.width = `${Math.round(fracaoContagem(restantes_s) * 100)}%`;
}

function pararContagem(): void {
  if (relogioContagem !== null) window.clearInterval(relogioContagem);
  relogioContagem = null;
  contagemInicio_ms = null;
  ultimoAvisoContagem_s = -1;
  desenharContagem(DURACAO_CONTAGEM_S);
  texto(botaoContagem, "Iniciar contagem de 30 s");
}

function iniciarContagem(): void {
  if (relogioContagem !== null) return;
  if (!aparelho()) {
    exigirAparelho(dicaMedicao);
    return;
  }
  contagemInicio_ms = Date.now();
  texto(botaoContagem, "Cancelar contagem");
  texto(dicaMedicao, `Fique parado: ${DURACAO_CONTAGEM_S} s. Registra sozinho quando chegar a zero.`);
  desenharContagem(DURACAO_CONTAGEM_S);
  relogioContagem = window.setInterval(() => {
    if (contagemInicio_ms === null) return;
    const restantes = segundosRestantes(contagemInicio_ms, Date.now());
    desenharContagem(restantes);
    // Só alguns avisos falados (10 s e zero): a cada segundo o leitor de tela falaria por cima de tudo.
    if ((restantes === 10 || restantes === 0) && restantes !== ultimoAvisoContagem_s) {
      ultimoAvisoContagem_s = restantes;
      texto(dicaMedicao, restantes === 0 ? "Registrando agora…" : `Faltam ${restantes} s. Continue parado.`);
    }
    if (restantes === 0) {
      pararContagem();
      registrarPonto();
    }
  }, 250);
}

function alternarContagem(): void {
  if (relogioContagem !== null) {
    pararContagem();
    texto(dicaMedicao, "Contagem cancelada. Toque em Registrar agora ou reinicie a contagem.");
  } else {
    iniciarContagem();
  }
}

// ---------- envio ----------

let relogioEnvio: number | null = null;

function agendarEnvio(): void {
  if (relogioEnvio !== null) window.clearTimeout(relogioEnvio);
  relogioEnvio = window.setTimeout(() => void rodadaDeEnvio(), fila.proximoAtraso_ms());
}

async function rodadaDeEnvio(): Promise<ResultadoRodada> {
  const r = await fila.descarregar();
  desenhar();
  agendarEnvio();
  return r;
}

function enviarAgora(): void {
  if (relogioEnvio !== null) window.clearTimeout(relogioEnvio);
  void rodadaDeEnvio();
}

// ---------- registrar ponto ----------

function exigirAparelho(destino: HTMLElement): void {
  texto(destino, "Preencha o campo Aparelho antes de registrar.");
  detalhesConfig.open = true;
  campoAparelho.focus();
}

function registrarPonto(): void {
  if (registrando) return;
  if (!aparelho()) {
    exigirAparelho(statusPonto);
    return;
  }
  if (!("geolocation" in navigator)) {
    texto(statusPonto, "Este navegador não tem geolocalização.");
    return;
  }
  registrando = true;
  pararContagem();
  botaoRegistrar.disabled = true;
  texto(statusPonto, "Obtendo posição…");
  const ponto = pontoAtual;
  navigator.geolocation.getCurrentPosition(
    (p) => {
      const item = fila.adicionar(
        montarRegistroPosicao({
          tipo: "ponto",
          posicao: posicaoMedida(p),
          ponto,
          aparelho: aparelho(),
          condicao: condicaoInformada(),
          observacao: campoObservacao.value.trim(),
          userAgent: navigator.userAgent,
          agora: new Date(),
        }),
      );
      registrando = false;
      botaoRegistrar.disabled = false;
      texto(statusPonto, "");
      ultimo = { ponto, medicao: medicoesFeitas(fila.registros(), ponto, aparelho()), id_cliente: item.id_cliente };
      mostrarVista("confirmar");
      cartaoEstado.tabIndex = -1;
      cartaoEstado.focus();
      enviarAgora();
    },
    (e) => {
      registrando = false;
      botaoRegistrar.disabled = false;
      texto(statusPonto, mensagemErroPosicao(e));
    },
    { enableHighAccuracy: true, maximumAge: 0, timeout: TIMEOUT_POSICAO_MS },
  );
}

function irParaProximo(): void {
  if (!ultimo) return;
  const feitas = medicoesFeitas(fila.registros(), ultimo.ponto, aparelho());
  if (feitas < MEDICOES_POR_PONTO) {
    definirPonto(ultimo.ponto);
    mostrarVista("medir");
    iniciarContagem(); // já está parado no ponto: a contagem começa sozinha
    return;
  }
  const seguinte = proximoPonto(ultimo.ponto);
  if (seguinte === null) return;
  definirPonto(seguinte);
  texto(dicaMedicao, `Ponto ${seguinte}. Vá até o ponto e toque em iniciar a contagem quando chegar.`);
  mostrarVista("medir");
  botaoContagem.focus();
}

function pularPonto(): void {
  const seguinte = proximoPonto(pontoAtual);
  if (seguinte === null) {
    texto(statusPonto, "Este é o último ponto (12).");
    return;
  }
  pararContagem();
  texto(statusPonto, `Ponto ${pontoAtual} pulado. Agora: ponto ${seguinte}.`);
  definirPonto(seguinte);
  desenhar();
}

// ---------- trajeto ----------

function gravarTrajeto(p: PosicaoMedida): void {
  const agora_ms = Date.now();
  if (!podeGravarTrajeto(ultimoTrajeto_ms, agora_ms)) return;
  ultimoTrajeto_ms = agora_ms;
  gravadosNoTrajeto += 1;
  fila.adicionar(
    montarRegistroPosicao({
      tipo: "trajeto",
      posicao: p,
      ponto: null,
      aparelho: aparelho(),
      condicao: null,
      observacao: campoObservacao.value.trim(),
      userAgent: navigator.userAgent,
      agora: new Date(agora_ms),
    }),
  );
  // O status só muda a cada 10 posições para o leitor de tela não tagarelar.
  if (gravadosNoTrajeto === 1 || gravadosNoTrajeto % 10 === 0) {
    texto(statusTrajeto, `Trajeto gravando: ${gravadosNoTrajeto} posições, precisão ${formatarMetros(p.accuracy)}.`);
  }
}

function alternarTrajeto(): void {
  if (trajetoLigado) {
    trajetoLigado = false;
    texto(botaoTrajeto, "Iniciar trajeto");
    botaoTrajeto.setAttribute("aria-pressed", "false");
    texto(statusTrajeto, `Trajeto parado. ${gravadosNoTrajeto} posições gravadas.`);
    faixaTrajeto.hidden = true;
    enviarAgora();
    return;
  }
  if (!("geolocation" in navigator)) {
    texto(statusRegistros, "Este navegador não tem geolocalização.");
    return;
  }
  if (!aparelho()) {
    exigirAparelho(statusRegistros);
    return;
  }
  gravadosNoTrajeto = 0;
  ultimoTrajeto_ms = null;
  trajetoLigado = true;
  texto(botaoTrajeto, "Parar trajeto");
  botaoTrajeto.setAttribute("aria-pressed", "true");
  faixaTrajeto.hidden = false;
  texto(statusTrajeto, "Trajeto iniciado. Aguardando a posição…");
  if (ultimaPosicao) gravarTrajeto(ultimaPosicao);
}

// ---------- bússola ----------

interface OrientacaoComIos extends DeviceOrientationEvent {
  webkitCompassHeading?: number;
}
type OrientacaoComPermissao = typeof DeviceOrientationEvent & {
  requestPermission?: () => Promise<"granted" | "denied">;
};

const amostrasBussola: { instante_ms: number; rumo_graus: number }[] = [];
let bussolaLigada = false;
let ultimaLeitura: { rumo_graus: number; fonte: string } | null = null;
let ultimoDesenho_ms = 0;

function aoOrientar(ev: Event): void {
  const o = ev as OrientacaoComIos;
  let rumo_graus: number | null = null;
  let fonte = "";
  let detalhe = "";
  if (typeof o.webkitCompassHeading === "number" && Number.isFinite(o.webkitCompassHeading)) {
    rumo_graus = o.webkitCompassHeading;
    fonte = "webkitCompassHeading";
    detalhe = "webkitCompassHeading (iOS)";
  } else if (typeof o.alpha === "number") {
    // alpha cresce no sentido anti-horário; o rumo da bússola cresce no horário.
    rumo_graus = (360 - o.alpha) % 360;
    fonte = o.absolute ? "alpha_absoluto" : "alpha_relativo";
    detalhe = `alpha ${Math.round(o.alpha)}° (${o.absolute ? "absoluto, referência: norte" : "relativo: NÃO aponta para o norte"})`;
  }
  if (rumo_graus === null) return;
  const agora_ms = Date.now();
  amostrasBussola.push({ instante_ms: agora_ms, rumo_graus });
  while (amostrasBussola.length > 0 && agora_ms - (amostrasBussola[0]?.instante_ms ?? agora_ms) > 3000) {
    amostrasBussola.shift();
  }
  ultimaLeitura = { rumo_graus, fonte };
  if (agora_ms - ultimoDesenho_ms >= 250) {
    ultimoDesenho_ms = agora_ms;
    texto(leituraBussola, `Rumo ${Math.round(rumo_graus)}°. Fonte: ${detalhe}.`);
    atualizarMapa(); // a seta só aparece se a fonte for absoluta (rumo.ts)
  }
}

async function ativarBussola(): Promise<void> {
  if (bussolaLigada) {
    window.removeEventListener("deviceorientationabsolute", aoOrientar);
    window.removeEventListener("deviceorientation", aoOrientar);
    bussolaLigada = false;
    ultimaLeitura = null;
    texto(botaoBussola, "Ativar bússola");
    botaoRegistrarBussola.disabled = true;
    texto(leituraBussola, "Bússola desligada.");
    texto(statusBussola, "Bússola desligada.");
    atualizarMapa();
    return;
  }
  if (typeof DeviceOrientationEvent === "undefined") {
    texto(statusBussola, "Resultado: este navegador não tem a API de orientação do aparelho.");
    return;
  }
  const classe = DeviceOrientationEvent as OrientacaoComPermissao;
  if (typeof classe.requestPermission === "function") {
    try {
      const resposta = await classe.requestPermission();
      if (resposta !== "granted") {
        texto(statusBussola, "Permissão da bússola negada. Feche e reabra a página para pedir de novo.");
        return;
      }
    } catch {
      texto(statusBussola, "Não foi possível pedir a permissão da bússola (precisa de HTTPS e de um toque).");
      return;
    }
  }
  // No Android o evento "absolute" é o que aponta para o norte; sem ele, o comum.
  const evento = "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
  window.addEventListener(evento, aoOrientar);
  bussolaLigada = true;
  amostrasBussola.length = 0;
  ultimaLeitura = null;
  texto(botaoBussola, "Desligar bússola");
  botaoRegistrarBussola.disabled = false;
  texto(leituraBussola, "Aguardando a primeira leitura…");
  texto(statusBussola, "Bússola ativada. Se nenhum valor aparecer, o aparelho não envia dados de orientação.");
}

function registrarBussola(): void {
  if (!aparelho()) {
    exigirAparelho(statusBussola);
    return;
  }
  if (!ultimaLeitura) {
    texto(statusBussola, "Ainda não há leitura da bússola para registrar.");
    return;
  }
  const oscilacao = oscilacaoBussola(amostrasBussola, Date.now());
  fila.adicionar(
    montarRegistroBussola({
      rumo_graus: Math.round(ultimaLeitura.rumo_graus * 100) / 100,
      fonte: ultimaLeitura.fonte,
      oscilacao,
      aparelho: aparelho(),
      userAgent: navigator.userAgent,
      agora: new Date(),
    }),
  );
  texto(
    statusBussola,
    oscilacao
      ? `Registrado: rumo ${Math.round(ultimaLeitura.rumo_graus)}°, oscilação de ${oscilacao.oscilacao_graus}° nos últimos 3 s (${oscilacao.amostras} leituras).`
      : `Registrado: rumo ${Math.round(ultimaLeitura.rumo_graus)}°, sem leituras nos últimos 3 s para medir a oscilação.`,
  );
  desenhar();
  enviarAgora();
}

// ---------- vibração ----------

function testarVibracao(): void {
  if (!aparelho()) {
    exigirAparelho(statusVibracao);
    return;
  }
  const existe = typeof navigator.vibrate === "function";
  let retorno: boolean | null = null;
  if (existe) {
    try {
      retorno = navigator.vibrate([200, 100, 200]);
    } catch {
      retorno = false;
    }
  }
  fila.adicionar(
    montarRegistroVibracao({ existe, retorno, aparelho: aparelho(), userAgent: navigator.userAgent, agora: new Date() }),
  );
  texto(
    statusVibracao,
    existe
      ? `Resultado: a API de vibração existe e retornou ${retorno ? "verdadeiro" : "falso"}. Confirme se o aparelho vibrou e anote.`
      : "Resultado: este aparelho não tem a API de vibração (esperado no iPhone). Registrado como resultado do teste.",
  );
  desenhar();
  enviarAgora();
}

// ---------- exportar e apagar ----------

function exportarCsv(): void {
  const registros = fila.registros();
  if (registros.length === 0) {
    texto(contagemRegistros, "Não há registros para exportar.");
    return;
  }
  const agora = new Date();
  const nome = nomeArquivoCsv(aparelho() || (registros[registros.length - 1]?.aparelho ?? ""), agora);
  const blob = new Blob([gerarCsv(registros)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  texto(contagemRegistros, `CSV gerado com ${registros.length} registros (enviados ou não): ${nome}.`);
}

function pedirConfirmacaoApagar(): void {
  if (fila.itens.length === 0) {
    texto(statusRegistros, "Não há registros para apagar.");
    return;
  }
  const naoEnviados = fila.itens.length - fila.contagem().enviado;
  textoConfirmar.textContent =
    `Apagar os ${fila.itens.length} registros deste aparelho? ` +
    (naoEnviados > 0 ? `${naoEnviados} ainda não foram enviados e serão perdidos. ` : "") +
    "Isso não pode ser desfeito. Exporte o CSV antes.";
  caixaConfirmar.hidden = false;
  botaoApagarNao.focus();
}

function fecharConfirmacao(): void {
  caixaConfirmar.hidden = true;
  botaoApagar.focus();
}

function apagarTudo(): void {
  fila.apagarTudo();
  ultimo = null;
  fecharConfirmacao();
  mostrarVista("medir");
  texto(statusRegistros, "Todos os registros foram apagados.");
}

// ---------- código da equipe ----------

function salvarCodigo(): void {
  const c = campoCodigo.value.trim();
  if (!c) {
    texto(statusRegistros, "Digite o código da equipe antes de salvar.");
    campoCodigo.focus();
    return;
  }
  gravarLocal(CHAVE_CODIGO, c);
  campoCodigo.value = "";
  fila.reabrirRecusadosPorCodigo();
  desenhar();
  texto(statusRegistros, "Código da equipe salvo. Enviando a fila.");
  botaoTrocarCodigo.focus();
  enviarAgora();
}

function trocarCodigo(): void {
  try {
    localStorage.removeItem(CHAVE_CODIGO);
  } catch {
    /* sem localStorage */
  }
  desenhar();
  campoCodigo.focus();
}

// ---------- inicialização ----------

if (window.isSecureContext === false) {
  el("aviso-https").hidden = false;
}

migrarRegistrosAntigos();
campoAparelho.value = lerLocal(CHAVE_APARELHO);
const condicaoSalva = lerLocal(CHAVE_CONDICAO);
if (condicaoSalva in ROTULO_CONDICAO) campoCondicao.value = condicaoSalva;
definirPonto(pontoValido(lerLocal(CHAVE_PONTO)) ?? 1);
detalhesConfig.open = !aparelho() || !codigoDaEquipe();

campoAparelho.addEventListener("change", () => {
  gravarLocal(CHAVE_APARELHO, aparelho());
  desenhar();
});
campoCondicao.addEventListener("change", () => {
  gravarLocal(CHAVE_CONDICAO, campoCondicao.value);
  desenhar();
});
campoPonto.addEventListener("change", () => {
  const n = pontoValido(campoPonto.value);
  if (n === null) {
    texto(statusRegistros, `Número do ponto inválido. Use um número inteiro de 1 a ${TOTAL_PONTOS}.`);
    campoPonto.value = String(pontoAtual);
    return;
  }
  pararContagem();
  definirPonto(n);
  desenhar();
});
botaoRegistrar.addEventListener("click", registrarPonto);
botaoContagem.addEventListener("click", alternarContagem);
botaoPular.addEventListener("click", pularPonto);
botaoProximo.addEventListener("click", irParaProximo);
botaoAbrirBussola.addEventListener("click", () => {
  const abrir = painelBussola.hidden;
  painelBussola.hidden = !abrir;
  botaoAbrirBussola.setAttribute("aria-expanded", String(abrir));
});
botaoTrajeto.addEventListener("click", alternarTrajeto);
botaoPararTrajeto.addEventListener("click", alternarTrajeto);
botaoBussola.addEventListener("click", () => void ativarBussola());
botaoRegistrarBussola.addEventListener("click", registrarBussola);
botaoVibrar.addEventListener("click", testarVibracao);
botaoExportar.addEventListener("click", exportarCsv);
botaoApagar.addEventListener("click", pedirConfirmacaoApagar);
botaoApagarSim.addEventListener("click", apagarTudo);
botaoApagarNao.addEventListener("click", fecharConfirmacao);
botaoSalvarCodigo.addEventListener("click", salvarCodigo);
botaoTrocarCodigo.addEventListener("click", trocarCodigo);

window.addEventListener("online", () => {
  fila.zerarRecuo();
  desenhar();
  enviarAgora();
});
window.addEventListener("offline", desenhar);

iniciarSeletorTema();
iniciarMapa();
desenharPrecisao(null);
pararContagem();
mostrarVista("medir");
iniciarVigia();
enviarAgora();
