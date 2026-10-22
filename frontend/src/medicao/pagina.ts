/*
 * Tela da página de medição de GPS (medicao.html), fluxo guiado: ponto N de 10, medição N de 3,
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
import { iniciarAjustes } from "../design/ajustes.ts";
import { iniciarSeletorTema } from "../design/seletor-tema.ts";
import { iniciarInterruptorMovimento } from "../design/interruptor-movimento.ts";
import {
  TAMANHO_ICONE_LOSANGO_PX,
  TAMANHO_ICONE_POSICAO_PX,
  htmlMarcadorPosicao,
  htmlMarcadorReferencia,
} from "../mapa/marcadores.ts";
import { rumoParaSeta } from "../mapa/rumo.ts";
import { criarArmazemFotos } from "./armazem-fotos.ts";
import { FilaFotos, type ItemFoto } from "./fila-fotos.ts";
import {
  altDaFoto,
  dimensoesReduzidas,
  MAX_BYTES_ALVO,
  MOTIVO_SEM_GUARDA,
  QUALIDADES_JPEG,
  textoEstadoFoto,
} from "./fotos.ts";
import { FilaEnvio, novoUuid, type FetchSimulavel, type ItemFila, type ResultadoRodada } from "./fila.ts";
import {
  DURACAO_CONTAGEM_S,
  MEDICOES_POR_PONTO,
  TOTAL_PONTOS,
  anuncioDaEtapa,
  anuncioRecomecou,
  classificarPrecisao,
  descreverEnvio,
  etapaInicial,
  deveAnunciarTrajeto,
  formatarMetros,
  textoPosicoes,
  textoTrajeto,
  fracaoContagem,
  medicoesFeitas,
  numeroDaProximaMedicao,
  pontosCompletos,
  proximoPonto,
  registrosDaRodada,
  segmentosProgresso,
  segundosRestantes,
  textoConfirmarRecomecar,
  textoMedicao,
  textoPrecisao,
  textoProgresso,
  type Etapa,
} from "./fluxo.ts";
import {
  gerarCsv,
  montarRegistroBussola,
  montarRegistroPosicao,
  montarRegistroVibracao,
  nomeArquivoCsv,
  oscilacaoBussola,
  podeGravarTrajeto,
  ROTULO_CONDICAO,
  type Condicao,
  type PosicaoMedida,
  type Registro,
} from "./medicao.ts";
import {
  CENTRO_CAMPUS as CENTRO_CAMPUS_REFERENCIA,
  distanciaMetros,
  opcoesDePontos,
  pontoDeControle,
  textoDistanciaReferencia,
  tituloDoPonto,
} from "./pontos-controle.ts";

const CHAVE_FILA = "msb-medicao-fila";
const CHAVE_REGISTROS_ANTIGA = "msb-medicao-registros";
const CHAVE_APARELHO = "msb-medicao-aparelho";
const CHAVE_CODIGO = "msb-medicao-codigo";
const CHAVE_PONTO = "msb-medicao-ponto-atual";
const CHAVE_RECOMECO = "msb-medicao-recomeco";
const TIMEOUT_POSICAO_MS = 30000;
const MAX_ULTIMOS = 6;

// Centro aproximado do campus (confirmar com o mapeamento): só o mapa inicial, antes do primeiro fix.
const CENTRO_CAMPUS: L.LatLngTuple = [CENTRO_CAMPUS_REFERENCIA[0], CENTRO_CAMPUS_REFERENCIA[1]];

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
const campoPonto = el<HTMLSelectElement>("campo-ponto");
const campoCondicao = el<HTMLSelectElement>("campo-condicao");
const campoObservacao = el<HTMLInputElement>("campo-observacao");
const resumoConfig = el<HTMLElement>("resumo-config");
const botaoAlterar = el<HTMLButtonElement>("botao-alterar");
const botaoContinuar = el<HTMLButtonElement>("botao-continuar");
const botaoCorrigirCodigo = el<HTMLButtonElement>("botao-corrigir-codigo");
const anuncioEtapa = el<HTMLParagraphElement>("anuncio-etapa");
const secoesEtapa: Record<Etapa, HTMLElement> = {
  preparar: el("etapa-preparar"),
  medir: el("etapa-medir"),
  resultado: el("etapa-resultado"),
};
const titulosEtapa: Record<Etapa, HTMLElement> = {
  preparar: el("titulo-etapa-preparar"),
  medir: el("titulo-etapa-medir"),
  resultado: el("titulo-etapa-resultado"),
};
const codigoSalvo = el<HTMLParagraphElement>("codigo-salvo");
const codigoEdicao = el<HTMLDivElement>("codigo-edicao");
const botaoSalvarCodigo = el<HTMLButtonElement>("botao-salvar-codigo");
const botaoTrocarCodigo = el<HTMLButtonElement>("botao-trocar-codigo");
const tituloPonto = el<HTMLElement>("titulo-ponto");
const tituloMedicao = el<HTMLElement>("titulo-medicao");
const progresso = el<HTMLDivElement>("progresso");
const faixaTrajeto = el<HTMLDivElement>("faixa-trajeto");
const statusTrajeto = el<HTMLParagraphElement>("status-trajeto");
const anuncioTrajeto = el<HTMLParagraphElement>("anuncio-trajeto");
const botaoPararTrajeto = el<HTMLButtonElement>("botao-parar-trajeto");
const painelPrecisao = el<HTMLDivElement>("painel-precisao");
const precisaoValor = el<HTMLElement>("precisao-valor");
const precisaoNivel = el<HTMLElement>("precisao-nivel");
const contagemValor = el<HTMLElement>("contagem-valor");
const contagemBarra = el<HTMLDivElement>("contagem-barra");
const botaoContagem = el<HTMLButtonElement>("botao-contagem");
const dicaMedicao = el<HTMLParagraphElement>("dica-medicao");
const pontoNome = el<HTMLParagraphElement>("ponto-nome");
const pontoObservacao = el<HTMLParagraphElement>("ponto-observacao");
const legendaReferencia = el<HTMLParagraphElement>("legenda-referencia");
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
const botaoRecomecar = el<HTMLButtonElement>("botao-recomecar");
const botaoRecomecarSim = el<HTMLButtonElement>("botao-recomecar-sim");
const botaoRecomecarNao = el<HTMLButtonElement>("botao-recomecar-nao");
const caixaConfirmar = el<HTMLDivElement>("confirmar-recomecar");
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
let etapa: Etapa = "preparar";
/** Instante do último "Recomeçar" (ISO): só os registros feitos depois contam no "ponto N de 10". */
let recomecoIso: string | null = null;
/** Registros da rodada atual: os que esperavam envio de antes do recomeço seguem na fila, mas não contam. */
const registrosDaRodadaAtual = (): Registro[] => registrosDaRodada(fila.registros(), recomecoIso);
/** Último ponto registrado nesta tela (para a etapa Resultado). */
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

/** A condição vem do ponto (plano do Maurício), pré-preenchida: a pessoa pode corrigir no campo. */
function preencherCondicaoDoPonto(n: number): void {
  const p = pontoDeControle(n);
  if (p) campoCondicao.value = p.condicao;
}

function definirPonto(n: number): void {
  const mudou = n !== pontoAtual;
  pontoAtual = n;
  if (mudou) preencherCondicaoDoPonto(n);
  campoPonto.value = String(n);
  gravarLocal(CHAVE_PONTO, String(n));
  if (mudou) {
    desenharReferencia();
    enquadrarMapa();
  }
}

// ---------- desenho ----------

function itemDaFila(id_cliente: string): ItemFila | undefined {
  return fila.itens.find((i) => i.id_cliente === id_cliente);
}

/** Cria as 10 opções uma vez; depois só troca o texto (" · feito") e a seleção, sem refazer a lista. */
function desenharOpcoesDePonto(completos: ReadonlySet<number>): void {
  const opcoes = opcoesDePontos(completos);
  if (campoPonto.options.length !== opcoes.length) {
    campoPonto.replaceChildren(...opcoes.map((o) => new Option(o.texto, o.valor)));
  } else {
    opcoes.forEach((o, i) => {
      const opcao = campoPonto.options[i];
      if (opcao && opcao.textContent !== o.texto) opcao.textContent = o.texto;
    });
  }
  campoPonto.value = String(pontoAtual);
}

function desenharCabecalho(): void {
  const registros = registrosDaRodadaAtual();
  const ap = aparelho();
  let ponto = pontoAtual;
  let medicao = numeroDaProximaMedicao(registros, pontoAtual, ap);
  if (etapa === "resultado" && ultimo) {
    ponto = ultimo.ponto;
    medicao = ultimo.medicao;
  }
  texto(tituloPonto, `Ponto ${ponto} de ${TOTAL_PONTOS}`);
  const dados = pontoDeControle(ponto);
  texto(pontoNome, dados ? tituloDoPonto(dados) : "");
  texto(pontoObservacao, dados ? `${ROTULO_CONDICAO[dados.condicao]}. ${dados.observacao}` : "");
  texto(tituloMedicao, textoMedicao(medicao));

  const segmentos = segmentosProgresso(registros, ap, ponto);
  const filhos = progresso.children;
  segmentos.forEach((s, i) => {
    const filho = filhos[i];
    if (!filho) return;
    filho.setAttribute("data-completo", String(s.completo));
    filho.setAttribute("data-atual", String(s.atual));
    filho.setAttribute("data-pulado", String(s.pulado));
  });
  desenharOpcoesDePonto(new Set(segmentos.filter((s) => s.completo).map((s) => s.ponto)));
  progresso.setAttribute("aria-valuenow", String(pontosCompletos(segmentos)));
  progresso.setAttribute("aria-valuetext", textoProgresso(segmentos));

  texto(resumoConfig, `${ap || "Aparelho sem nome"} · ${codigoDaEquipe() ? "código salvo" : "sem código"}`);
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
    const feitas = medicoesFeitas(registrosDaRodadaAtual(), ultimo.ponto, aparelho());
    const completo = feitas >= MEDICOES_POR_PONTO;
    const detalhe =
      `Ponto ${ultimo.ponto} ${completo ? "completo" : "em andamento"} · ${Math.min(feitas, MEDICOES_POR_PONTO)} de ${MEDICOES_POR_PONTO} medições · ${formatarMetros(doUltimo.registro.precisao_m)}` +
      (t.cartao === "fila" ? ". Envio automático quando der." : "") +
      (doUltimo.recusado_por_codigo ? ". Corrija o código da equipe." : "");
    texto(cartaoDetalhe, detalhe);
    // Falta ou erro de código: atalho direto para a etapa Preparar (sem passar por Medir).
    botaoCorrigirCodigo.hidden = !(!temCodigo || doUltimo.recusado_por_codigo);
    texto(botaoCorrigirCodigo, temCodigo ? "Corrigir o código da equipe" : "Informar o código da equipe");

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

// ---------- etapas: uma por tela ----------

let anuncioPendente: number | null = null;

/** Fala uma frase só, uma vez: limpa a região e escreve no quadro seguinte (repetir a mesma frase também é lido). */
function anunciar(frase: string): void {
  if (anuncioPendente !== null) window.clearTimeout(anuncioPendente);
  anuncioEtapa.textContent = "";
  anuncioPendente = window.setTimeout(() => {
    anuncioEtapa.textContent = frase;
    anuncioPendente = null;
  }, 60);
}

function frasePadraoDaEtapa(nova: Etapa): string {
  if (nova === "resultado" && ultimo) return anuncioDaEtapa(nova, ultimo.ponto, ultimo.medicao);
  const medicao = numeroDaProximaMedicao(registrosDaRodadaAtual(), pontoAtual, aparelho());
  return anuncioDaEtapa(nova, pontoAtual, medicao);
}

/**
 * Troca a etapa. Os textos são desenhados ANTES de a etapa aparecer (região aria-live que já nasce
 * escrita não fala sozinha); depois o foco vai para o título da etapa (tabindex=-1) e UMA frase é
 * anunciada. `anuncio`: omitido = frase padrão da etapa; texto = essa frase; null = nenhuma
 * (quando outro aviso já vai falar). `foco: "nenhum"` deixa o foco onde o chamador pôr.
 */
function irParaEtapa(nova: Etapa, opcoes: { foco?: "titulo" | "nenhum"; anuncio?: string | null } = {}): void {
  etapa = nova;
  desenhar();
  for (const id of Object.keys(secoesEtapa) as Etapa[]) secoesEtapa[id].hidden = id !== nova;
  barraMedir.hidden = nova !== "medir";
  barraConfirmar.hidden = nova !== "resultado";
  if (nova === "medir") {
    mapa?.invalidateSize({ animate: false });
    enquadrarMapa();
  }
  if (opcoes.foco !== "nenhum") titulosEtapa[nova].focus();
  if (opcoes.anuncio !== null) anunciar(opcoes.anuncio ?? frasePadraoDaEtapa(nova));
}

// ---------- mapa pequeno ----------

/** O mapa nunca anima (público cego e com baixa visão): nada de zoom, fade, inércia nem salto no limite. */
const SEM_ANIMACAO = {
  zoomAnimation: false,
  fadeAnimation: false,
  markerZoomAnimation: false,
  inertia: false,
  bounceAtZoomLimits: false,
} as const;

let mapa: L.Map | null = null;
let marcador: L.Marker | null = null;
let halo: L.Circle | null = null;
let rumoDoMarcador: number | null | undefined;
let marcadorReferencia: L.Marker | null = null;

function referenciaAtual(): L.LatLng | null {
  const p = pontoDeControle(pontoAtual);
  return p ? L.latLng(p.referencia_lat, p.referencia_lon) : null;
}

/** Legenda em texto do ◆ e a distância até ele. Só informa: a posição medida nunca é "corrigida" por ela. */
function desenharReferencia(): void {
  const ref = referenciaAtual();
  const distancia_m =
    ref && ultimaPosicao ? distanciaMetros(ultimaPosicao.latitude, ultimaPosicao.longitude, ref.lat, ref.lng) : null;
  texto(legendaReferencia, `◆ no mapa: referência do ponto. ${textoDistanciaReferencia(distancia_m)}`);
}

/** Mapa centrado entre a posição (com a precisão) e a referência do ponto, sem animação. */
function enquadrarMapa(): void {
  const ref = referenciaAtual();
  if (!mapa || !ref) return;
  if (marcadorReferencia) marcadorReferencia.setLatLng(ref);
  else {
    const metade = TAMANHO_ICONE_LOSANGO_PX / 2;
    marcadorReferencia = L.marker(ref, {
      icon: L.divIcon({
        className: "",
        html: htmlMarcadorReferencia(),
        iconSize: [TAMANHO_ICONE_LOSANGO_PX, TAMANHO_ICONE_LOSANGO_PX],
        iconAnchor: [metade, metade],
      }),
      interactive: false,
      keyboard: false,
    }).addTo(mapa);
  }
  const limites = L.latLngBounds([ref]);
  if (halo) limites.extend(halo.getBounds());
  else if (ultimaPosicao) limites.extend(L.latLng(ultimaPosicao.latitude, ultimaPosicao.longitude));
  if (limites.getSouthWest().equals(limites.getNorthEast())) mapa.setView(ref, 18, { animate: false });
  else mapa.fitBounds(limites, { maxZoom: 19, padding: [20, 20], animate: false });
}

function iniciarMapa(): void {
  try {
    mapa = L.map(el("mapa-medicao"), {
      center: CENTRO_CAMPUS,
      zoom: 17,
      minZoom: 15,
      maxZoom: 19,
      ...SEM_ANIMACAO,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>',
    }).addTo(mapa);
    enquadrarMapa();
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
    desenharReferencia();
    enquadrarMapa();
    return;
  }
  desenharReferencia();
  halo.setLatLng(ll);
  halo.setRadius(p.accuracy);
  marcador.setLatLng(ll);
  if (rumo !== rumoDoMarcador) {
    marcador.setIcon(iconePosicao(rumo));
    rumoDoMarcador = rumo;
  }
  if (!mapa.getBounds().contains(ll)) mapa.panTo(ll, { animate: false });
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
      if (trajetoLigado) {
        const aviso = `${mensagemErroPosicao(e)} O trajeto continua tentando.`;
        mostrarTrajeto(aviso, statusTrajeto.textContent !== aviso);
      }
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

/** `prefixo`: contexto falado junto, quando a contagem começa sozinha ao entrar na etapa (um só anúncio). */
function iniciarContagem(prefixo = ""): void {
  if (relogioContagem !== null) return;
  if (!aparelho()) {
    exigirAparelho();
    return;
  }
  contagemInicio_ms = Date.now();
  texto(botaoContagem, "Cancelar contagem");
  texto(dicaMedicao, `${prefixo}Fique parado: ${DURACAO_CONTAGEM_S} s. Registra sozinho quando chegar a zero.`);
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

function exigirAparelho(): void {
  irParaEtapa("preparar", { foco: "nenhum", anuncio: null });
  texto(statusRegistros, "Preencha o campo Aparelho antes de registrar.");
  campoAparelho.focus();
}

function registrarPonto(): void {
  if (registrando) return;
  if (!aparelho()) {
    exigirAparelho();
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
      ultimo = { ponto, medicao: medicoesFeitas(registrosDaRodadaAtual(), ponto, aparelho()), id_cliente: item.id_cliente };
      irParaEtapa("resultado");
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
  const feitas = medicoesFeitas(registrosDaRodadaAtual(), ultimo.ponto, aparelho());
  if (feitas < MEDICOES_POR_PONTO) {
    definirPonto(ultimo.ponto);
    // Já está parado no ponto: a contagem começa sozinha e a própria dica fala o contexto (um só anúncio).
    irParaEtapa("medir", { anuncio: null });
    iniciarContagem(`${frasePadraoDaEtapa("medir")} `);
    return;
  }
  const seguinte = proximoPonto(ultimo.ponto);
  if (seguinte === null) return;
  definirPonto(seguinte);
  texto(dicaMedicao, `Ponto ${seguinte}. Vá até o ponto e toque em iniciar a contagem quando chegar.`);
  irParaEtapa("medir", { foco: "nenhum", anuncio: null });
  botaoContagem.focus();
}

function pularPonto(): void {
  const seguinte = proximoPonto(pontoAtual);
  if (seguinte === null) {
    texto(statusPonto, `Este é o último ponto (${TOTAL_PONTOS}).`);
    return;
  }
  pararContagem();
  texto(statusPonto, `Ponto ${pontoAtual} pulado. Agora: ponto ${seguinte}.`);
  definirPonto(seguinte);
  desenhar();
}

// ---------- trajeto ----------

/** Texto visível da faixa (sem aria-live) + anúncio opcional na região separada. */
function mostrarTrajeto(visivel: string, anunciar: boolean): void {
  texto(statusTrajeto, visivel);
  if (anunciar) {
    anuncioTrajeto.textContent = "";
    window.setTimeout(() => {
      anuncioTrajeto.textContent = visivel;
    }, 60);
  }
}

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
  // O texto visível muda a cada posição; o leitor de tela só fala na 1ª e a cada 10.
  mostrarTrajeto(textoTrajeto(gravadosNoTrajeto, p.accuracy), deveAnunciarTrajeto(gravadosNoTrajeto));
}

function alternarTrajeto(): void {
  if (trajetoLigado) {
    trajetoLigado = false;
    texto(botaoTrajeto, "Iniciar trajeto");
    botaoTrajeto.setAttribute("aria-pressed", "false");
    mostrarTrajeto(`Trajeto parado. ${textoPosicoes(gravadosNoTrajeto)} gravadas.`, true);
    faixaTrajeto.hidden = true;
    enviarAgora();
    return;
  }
  if (!("geolocation" in navigator)) {
    texto(statusRegistros, "Este navegador não tem geolocalização.");
    return;
  }
  if (!aparelho()) {
    exigirAparelho();
    return;
  }
  gravadosNoTrajeto = 0;
  ultimoTrajeto_ms = null;
  trajetoLigado = true;
  texto(botaoTrajeto, "Parar trajeto");
  botaoTrajeto.setAttribute("aria-pressed", "true");
  faixaTrajeto.hidden = false;
  mostrarTrajeto("Trajeto iniciado. Aguardando a posição…", true);
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
    exigirAparelho();
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
    exigirAparelho();
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

// ---------- exportar e recomeçar ----------

/** Baixa o CSV de tudo o que está neste aparelho e devolve a frase para mostrar (ou null se não há nada). */
function baixarCsv(): string {
  const registros = fila.registros();
  if (registros.length === 0) return "Não há registros para exportar.";
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
  return `CSV gerado com ${registros.length} registros (enviados ou não): ${nome}.`;
}

function exportarCsv(): void {
  texto(contagemRegistros, baixarCsv());
}

/**
 * "Recomeçar" volta ao ponto 1, zera a contagem de pontos (marca `recomecoIso`), para contagem e
 * trajeto e leva à etapa Preparar. NÃO apaga o que ainda não foi enviado: esses registros seguem na
 * fila e saem sozinhos, com o mesmo recuo de 5-10-30-60 s. Sai da lista local só o que já foi
 * enviado (o banco já tem). Continuam salvos o aparelho, o código da equipe, a condição, o tema e a
 * preferência de movimento. Nada é apagado no servidor.
 */
function pedirConfirmacaoRecomecar(): void {
  textoConfirmar.textContent = textoConfirmarRecomecar(fila.contagem().na_fila);
  caixaConfirmar.hidden = false;
  botaoRecomecar.setAttribute("aria-expanded", "true");
  botaoRecomecarNao.focus(); // o padrão seguro é "Não": Enter por engano não muda nada
}

function fecharConfirmacao(devolverFoco: boolean): void {
  caixaConfirmar.hidden = true;
  botaoRecomecar.setAttribute("aria-expanded", "false");
  if (devolverFoco) botaoRecomecar.focus();
}

function recomecar(): void {
  pararContagem();
  if (trajetoLigado) {
    trajetoLigado = false;
    texto(botaoTrajeto, "Iniciar trajeto");
    botaoTrajeto.setAttribute("aria-pressed", "false");
    faixaTrajeto.hidden = true;
  }
  const esperando = fila.contagem().na_fila;
  fila.limparEnviados();
  recomecoIso = new Date().toISOString();
  gravarLocal(CHAVE_RECOMECO, recomecoIso);
  ultimo = null;
  definirPonto(1);
  texto(statusRegistros, "");
  texto(statusPonto, "");
  fecharConfirmacao(false);
  irParaEtapa("preparar", { anuncio: anuncioRecomecou(esperando) });
}

// ---------- foto do ponto ----------

const campoFoto = el<HTMLInputElement>("campo-foto");
const estadoFoto = el<HTMLParagraphElement>("estado-foto");
const listaFotos = el<HTMLUListElement>("lista-fotos");

const filaFotos = new FilaFotos({
  armazem: criarArmazemFotos(),
  fetch: async (url, init) => {
    const r = await fetch(url, { ...init, body: init.body as Blob });
    return { status: r.status, json: () => r.json() as Promise<unknown> };
  },
  codigo: codigoDaEquipe,
});
const miniaturas = new Map<string, string>();
let relogioFotos: number | null = null;

const codigoDoPonto = (n: number): string => pontoDeControle(n)?.codigo ?? `P${String(n).padStart(2, "0")}`;
const estadoVisualFoto = (i: ItemFoto): "enviada" | "fila" | "recusada" =>
  i.estado === "na_fila" ? "fila" : i.estado;

function desenharFotos(): void {
  const recentes = filaFotos.itens.slice(-4).reverse();
  const manter = new Set(recentes.map((i) => i.id_cliente));
  for (const [id, url] of miniaturas) {
    if (!manter.has(id)) {
      URL.revokeObjectURL(url);
      miniaturas.delete(id);
    }
  }
  listaFotos.replaceChildren(
    ...recentes.map((i) => {
      let url = miniaturas.get(i.id_cliente);
      if (!url && i.blob instanceof Blob) {
        url = URL.createObjectURL(i.blob);
        miniaturas.set(i.id_cliente, url);
      }
      const li = document.createElement("li");
      li.className = "medicao__foto-item";
      li.dataset.estado = estadoVisualFoto(i);
      if (url) {
        const img = document.createElement("img");
        img.src = url;
        img.alt = altDaFoto(codigoDoPonto(i.ponto));
        li.append(img);
      }
      const p = document.createElement("p");
      p.textContent = textoEstadoFoto(codigoDoPonto(i.ponto), i.estado, i.motivo);
      li.append(p);
      return li;
    }),
  );
}

/** Um só aria-live: diz o estado da foto mais recente que mudou. */
function dizerEstadoFoto(i: ItemFoto): void {
  texto(estadoFoto, textoEstadoFoto(codigoDoPonto(i.ponto), i.estado, i.motivo));
}

async function enviarFotos(): Promise<void> {
  const antes = filaFotos.itens.map((i) => i.estado);
  await filaFotos.descarregar();
  filaFotos.itens.forEach((i, n) => {
    if (antes[n] !== i.estado) dizerEstadoFoto(i);
  });
  desenharFotos();
  if (relogioFotos !== null) window.clearTimeout(relogioFotos);
  relogioFotos = null;
  if (filaFotos.pendentes().length > 0) {
    relogioFotos = window.setTimeout(() => void enviarFotos(), filaFotos.proximoAtraso_ms());
  }
}

/** Canvas descarta EXIF/GPS. Lado maior <= 1280 px; JPEG 0,8 e, se passar de 1 MB, 0,6. */
async function reduzirFoto(arquivo: File): Promise<{ blob: Blob; largura_px: number; altura_px: number }> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(arquivo, { imageOrientation: "from-image" });
  } catch {
    bitmap = await createImageBitmap(arquivo);
  }
  const { largura_px, altura_px } = dimensoesReduzidas(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = largura_px;
  canvas.height = altura_px;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas indisponível");
  ctx.drawImage(bitmap, 0, 0, largura_px, altura_px);
  bitmap.close?.();
  let blob: Blob | null = null;
  for (const q of QUALIDADES_JPEG) {
    blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", q));
    if (blob && blob.size <= MAX_BYTES_ALVO) break;
  }
  if (!blob) throw new Error("não foi possível gerar o JPEG");
  return { blob, largura_px, altura_px };
}

async function aoFotografar(): Promise<void> {
  const arquivo = campoFoto.files?.[0];
  campoFoto.value = "";
  if (!arquivo) return;
  if (!aparelho()) {
    texto(estadoFoto, "Preencha o campo Aparelho antes de fotografar.");
    return;
  }
  texto(estadoFoto, "Preparando a foto…");
  let reduzida: Awaited<ReturnType<typeof reduzirFoto>>;
  try {
    reduzida = await reduzirFoto(arquivo);
  } catch {
    texto(estadoFoto, "Não foi possível ler a foto. Tire de novo.");
    return;
  }
  const r = await filaFotos.adicionar(
    {
      id_cliente: novoUuid(),
      ponto: pontoAtual,
      aparelho: aparelho(),
      tirada_em: new Date().toISOString(),
      largura_px: reduzida.largura_px,
      altura_px: reduzida.altura_px,
    },
    reduzida.blob,
  );
  if (r.item) {
    dizerEstadoFoto(r.item);
    if (r.guardada && r.item.estado === "na_fila") agendarFotosSeguinte();
  } else {
    texto(estadoFoto, `Foto do ${codigoDoPonto(pontoAtual)}: ${r.motivo ?? MOTIVO_SEM_GUARDA}. Tire de novo quando tiver sinal.`);
  }
  desenharFotos();
}

function agendarFotosSeguinte(): void {
  if (relogioFotos !== null) window.clearTimeout(relogioFotos);
  relogioFotos = window.setTimeout(() => void enviarFotos(), filaFotos.proximoAtraso_ms());
}

campoFoto.addEventListener("change", () => void aoFotografar());

// ---------- código da equipe ----------

/** Grava o código digitado (se houver) e reabre o que foi recusado por código errado. */
function gravarCodigoDigitado(): boolean {
  const c = campoCodigo.value.trim();
  if (!c) return false;
  gravarLocal(CHAVE_CODIGO, c);
  campoCodigo.value = "";
  fila.reabrirRecusadosPorCodigo();
  filaFotos.reabrirRecusadasPorCodigo();
  void enviarFotos();
  return true;
}

function salvarCodigo(): void {
  if (!gravarCodigoDigitado()) {
    texto(statusRegistros, "Digite o código da equipe antes de salvar.");
    campoCodigo.focus();
    return;
  }
  desenhar();
  texto(statusRegistros, "Código da equipe salvo. Enviando a fila.");
  botaoTrocarCodigo.focus();
  enviarAgora();
}

/** Etapa 1 -> 2: o aparelho é obrigatório; um código digitado e ainda não salvo é salvo aqui. */
function continuarParaMedicao(): void {
  if (!aparelho()) {
    texto(statusRegistros, "Preencha o campo Aparelho antes de continuar.");
    campoAparelho.focus();
    return;
  }
  if (gravarCodigoDigitado()) enviarAgora();
  texto(statusRegistros, "");
  irParaEtapa("medir");
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
recomecoIso = lerLocal(CHAVE_RECOMECO) || null;
definirPonto(pontoValido(lerLocal(CHAVE_PONTO)) ?? 1);
preencherCondicaoDoPonto(pontoAtual);
desenharReferencia();

campoAparelho.addEventListener("change", () => {
  gravarLocal(CHAVE_APARELHO, aparelho());
  desenhar();
});
campoCondicao.addEventListener("change", () => {
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
botaoRecomecar.addEventListener("click", () => {
  if (caixaConfirmar.hidden) pedirConfirmacaoRecomecar();
  else fecharConfirmacao(true);
});
caixaConfirmar.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") fecharConfirmacao(true);
});
botaoRecomecarSim.addEventListener("click", recomecar);
botaoRecomecarNao.addEventListener("click", () => fecharConfirmacao(true));
botaoContinuar.addEventListener("click", continuarParaMedicao);
botaoAlterar.addEventListener("click", () => irParaEtapa("preparar"));
botaoCorrigirCodigo.addEventListener("click", () => {
  irParaEtapa("preparar", { foco: "nenhum", anuncio: null });
  trocarCodigo();
});
botaoSalvarCodigo.addEventListener("click", salvarCodigo);
botaoTrocarCodigo.addEventListener("click", trocarCodigo);

window.addEventListener("online", () => {
  filaFotos.zerarRecuo();
  void enviarFotos();
  fila.zerarRecuo();
  desenhar();
  enviarAgora();
});
window.addEventListener("offline", desenhar);

iniciarAjustes();
iniciarSeletorTema();
iniciarInterruptorMovimento();
iniciarMapa();
desenharPrecisao(null);
pararContagem();
irParaEtapa(etapaInicial({ temAparelho: aparelho() !== "", temCodigo: codigoDaEquipe() !== "" }), {
  foco: "nenhum",
  anuncio: null,
});
iniciarVigia();
enviarAgora();
void filaFotos.carregar().then(() => {
  filaFotos.reabrirRecusadasPorCodigo();
  desenharFotos();
  void enviarFotos();
});
