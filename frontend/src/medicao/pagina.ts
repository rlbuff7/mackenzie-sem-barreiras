/*
 * Tela da página de medição de GPS (medicao.html). Liga a lógica pura de medicao.ts
 * às APIs do navegador: geolocalização, orientação do aparelho, vibração, localStorage
 * e download do CSV. Não chama a API do projeto nem nenhum terceiro.
 */
import "../estilos.css";
import "./medicao.css";
import { iniciarSeletorTema } from "../design/seletor-tema.ts";
import {
  ROTULO_CONDICAO,
  contarPontoRegistrado,
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

const CHAVE_REGISTROS = "msb-medicao-registros";
const CHAVE_APARELHO = "msb-medicao-aparelho";
const MEDICOES_POR_PONTO = 3;
const TIMEOUT_POSICAO_MS = 30000;
const MAX_ITENS_NA_LISTA = 50;

function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id);
  if (!e) throw new Error(`Elemento #${id} não encontrado`);
  return e as T;
}

const campoAparelho = el<HTMLInputElement>("campo-aparelho");
const campoPonto = el<HTMLInputElement>("campo-ponto");
const campoCondicao = el<HTMLSelectElement>("campo-condicao");
const campoObservacao = el<HTMLInputElement>("campo-observacao");
const botaoRegistrar = el<HTMLButtonElement>("botao-registrar");
const botaoTrajeto = el<HTMLButtonElement>("botao-trajeto");
const botaoBussola = el<HTMLButtonElement>("botao-bussola");
const botaoRegistrarBussola = el<HTMLButtonElement>("botao-registrar-bussola");
const botaoVibrar = el<HTMLButtonElement>("botao-vibrar");
const botaoExportar = el<HTMLButtonElement>("botao-exportar");
const botaoApagar = el<HTMLButtonElement>("botao-apagar");
const botaoApagarSim = el<HTMLButtonElement>("botao-apagar-sim");
const botaoApagarNao = el<HTMLButtonElement>("botao-apagar-nao");
const caixaConfirmar = el<HTMLDivElement>("confirmar-apagar");
const textoConfirmar = el<HTMLParagraphElement>("texto-confirmar");
const statusPonto = el<HTMLParagraphElement>("status-ponto");
const statusTrajeto = el<HTMLParagraphElement>("status-trajeto");
const statusBussola = el<HTMLParagraphElement>("status-bussola");
const statusVibracao = el<HTMLParagraphElement>("status-vibracao");
const statusRegistros = el<HTMLParagraphElement>("status-registros");
const contagemRegistros = el<HTMLParagraphElement>("contagem-registros");
const leituraBussola = el<HTMLParagraphElement>("leitura-bussola");
const listaRegistros = el<HTMLOListElement>("lista-registros");

// ---------- armazenamento ----------

let registros: Registro[] = [];
let armazenamentoOk = true;

function carregarRegistros(): Registro[] {
  try {
    const bruto = localStorage.getItem(CHAVE_REGISTROS);
    if (!bruto) return [];
    const lido: unknown = JSON.parse(bruto);
    return Array.isArray(lido) ? (lido as Registro[]) : [];
  } catch {
    armazenamentoOk = false;
    return [];
  }
}

function salvarRegistros(): void {
  try {
    localStorage.setItem(CHAVE_REGISTROS, JSON.stringify(registros));
  } catch {
    armazenamentoOk = false;
  }
}

function adicionarRegistro(r: Registro): void {
  registros.push(r);
  salvarRegistros();
  desenharLista();
}

function lerAparelhoSalvo(): string {
  try {
    return localStorage.getItem(CHAVE_APARELHO) ?? "";
  } catch {
    return "";
  }
}

function salvarAparelho(): void {
  try {
    localStorage.setItem(CHAVE_APARELHO, campoAparelho.value.trim());
  } catch {
    /* sem localStorage: o campo continua funcionando, só não é lembrado */
  }
}

// ---------- leitura dos campos ----------

const aparelho = (): string => campoAparelho.value.trim();

function pontoInformado(): number | null {
  const n = Number(campoPonto.value);
  return Number.isInteger(n) && n >= 1 && n <= 12 ? n : null;
}

const condicaoInformada = (): Condicao => campoCondicao.value as Condicao;

function textoContagemDoPonto(ponto: number): string {
  const n = contarPontoRegistrado(registros, ponto, aparelho());
  const faltam = Math.max(0, MEDICOES_POR_PONTO - n);
  const resto = faltam > 0 ? `faltam ${faltam}` : "completo";
  return `Ponto ${ponto}: ${n} de ${MEDICOES_POR_PONTO} medições deste aparelho (${resto}).`;
}

// ---------- lista ----------

function resumoRegistro(r: Registro): string {
  const hora = r.horario_local.slice(11);
  switch (r.tipo) {
    case "ponto": {
      const cond = r.condicao ? ROTULO_CONDICAO[r.condicao] : "sem condição";
      return `${hora}  Ponto ${r.ponto}, ${cond}, precisão ${r.precisao_m} m (${r.aparelho})`;
    }
    case "trajeto":
      return `${hora}  Trajeto, precisão ${r.precisao_m} m (${r.aparelho})`;
    case "bussola":
      return `${hora}  Bússola ${r.bussola_rumo_graus}°, oscilação ${r.bussola_oscilacao_graus ?? "sem dado"}° (${r.aparelho})`;
    case "vibracao":
      return `${hora}  Vibração: API ${r.vibracao_existe ? "existe" : "não existe"}, retorno ${
        r.vibracao_retorno === null ? "nenhum" : r.vibracao_retorno ? "verdadeiro" : "falso"
      } (${r.aparelho})`;
  }
}

function desenharLista(): void {
  const total = registros.length;
  const pontos = registros.filter((r) => r.tipo === "ponto").length;
  const trajeto = registros.filter((r) => r.tipo === "trajeto").length;
  contagemRegistros.textContent =
    `${total} registros: ${pontos} de ponto, ${trajeto} de trajeto, ${total - pontos - trajeto} de teste.` +
    (armazenamentoOk ? "" : " Atenção: este navegador não está guardando os registros; exporte o CSV antes de recarregar.");
  listaRegistros.replaceChildren();
  const recentes = registros.slice(-MAX_ITENS_NA_LISTA).reverse();
  for (const r of recentes) {
    const li = document.createElement("li");
    li.textContent = resumoRegistro(r);
    listaRegistros.append(li);
  }
  if (total > recentes.length) {
    const li = document.createElement("li");
    li.textContent = `Mostrando os ${recentes.length} mais recentes. O CSV leva todos.`;
    li.setAttribute("value", String(recentes.length + 1));
    listaRegistros.append(li);
  }
}

// ---------- ponto de controle ----------

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

function registrarPonto(): void {
  const ponto = pontoInformado();
  if (ponto === null) {
    statusPonto.textContent = "Número do ponto inválido. Use um número inteiro de 1 a 12.";
    campoPonto.focus();
    return;
  }
  if (!aparelho()) {
    statusPonto.textContent = "Preencha o campo Aparelho antes de registrar.";
    campoAparelho.focus();
    return;
  }
  if (!("geolocation" in navigator)) {
    statusPonto.textContent = "Este navegador não tem geolocalização.";
    return;
  }
  botaoRegistrar.disabled = true;
  statusPonto.textContent = "Obtendo posição…";
  navigator.geolocation.getCurrentPosition(
    (p) => {
      adicionarRegistro(
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
      botaoRegistrar.disabled = false;
      statusPonto.textContent =
        `Registrado: precisão ${Math.round(p.coords.accuracy * 10) / 10} m. ${textoContagemDoPonto(ponto)} ` +
        "Para a próxima medição, espere de novo 20 a 30 s parado.";
    },
    (e) => {
      botaoRegistrar.disabled = false;
      statusPonto.textContent = mensagemErroPosicao(e);
    },
    { enableHighAccuracy: true, maximumAge: 0, timeout: TIMEOUT_POSICAO_MS },
  );
}

// ---------- trajeto ----------

let idVigia: number | null = null;
let ultimoTrajeto_ms: number | null = null;
let gravadosNoTrajeto = 0;

function alternarTrajeto(): void {
  if (idVigia !== null) {
    navigator.geolocation.clearWatch(idVigia);
    idVigia = null;
    botaoTrajeto.textContent = "Iniciar trajeto";
    botaoTrajeto.setAttribute("aria-pressed", "false");
    statusTrajeto.textContent = `Trajeto parado. ${gravadosNoTrajeto} posições gravadas.`;
    return;
  }
  if (!("geolocation" in navigator)) {
    statusTrajeto.textContent = "Este navegador não tem geolocalização.";
    return;
  }
  if (!aparelho()) {
    statusTrajeto.textContent = "Preencha o campo Aparelho antes de iniciar o trajeto.";
    campoAparelho.focus();
    return;
  }
  gravadosNoTrajeto = 0;
  ultimoTrajeto_ms = null;
  botaoTrajeto.textContent = "Parar trajeto";
  botaoTrajeto.setAttribute("aria-pressed", "true");
  statusTrajeto.textContent = "Trajeto iniciado. Aguardando a primeira posição…";
  idVigia = navigator.geolocation.watchPosition(
    (p) => {
      const agora_ms = Date.now();
      if (!podeGravarTrajeto(ultimoTrajeto_ms, agora_ms)) return;
      ultimoTrajeto_ms = agora_ms;
      gravadosNoTrajeto += 1;
      adicionarRegistro(
        montarRegistroPosicao({
          tipo: "trajeto",
          posicao: posicaoMedida(p),
          ponto: null,
          aparelho: aparelho(),
          condicao: null,
          observacao: campoObservacao.value.trim(),
          userAgent: navigator.userAgent,
          agora: new Date(agora_ms),
        }),
      );
      // Só o contador muda a cada segundo; o status não é anunciado a cada posição
      // (role=status é polite, mas o texto muda só a cada 10 posições para não tagarelar).
      if (gravadosNoTrajeto === 1 || gravadosNoTrajeto % 10 === 0) {
        statusTrajeto.textContent = `Gravando: ${gravadosNoTrajeto} posições, precisão atual ${Math.round(p.coords.accuracy * 10) / 10} m.`;
      }
    },
    (e) => {
      statusTrajeto.textContent = mensagemErroPosicao(e) + " O trajeto continua tentando.";
    },
    { enableHighAccuracy: true, maximumAge: 0, timeout: TIMEOUT_POSICAO_MS },
  );
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
    leituraBussola.textContent = `Rumo ${Math.round(rumo_graus)}°. Fonte: ${detalhe}.`;
  }
}

async function ativarBussola(): Promise<void> {
  if (bussolaLigada) {
    window.removeEventListener("deviceorientationabsolute", aoOrientar);
    window.removeEventListener("deviceorientation", aoOrientar);
    bussolaLigada = false;
    botaoBussola.textContent = "Ativar bússola";
    botaoRegistrarBussola.disabled = true;
    leituraBussola.textContent = "Bússola desligada.";
    statusBussola.textContent = "Bússola desligada.";
    return;
  }
  if (typeof DeviceOrientationEvent === "undefined") {
    statusBussola.textContent = "Resultado: este navegador não tem a API de orientação do aparelho.";
    return;
  }
  const classe = DeviceOrientationEvent as OrientacaoComPermissao;
  if (typeof classe.requestPermission === "function") {
    try {
      const resposta = await classe.requestPermission();
      if (resposta !== "granted") {
        statusBussola.textContent = "Permissão da bússola negada. Feche e reabra a página para pedir de novo.";
        return;
      }
    } catch {
      statusBussola.textContent = "Não foi possível pedir a permissão da bússola (precisa de HTTPS e de um toque).";
      return;
    }
  }
  // No Android o evento "absolute" é o que aponta para o norte; sem ele, o comum.
  const evento = "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
  window.addEventListener(evento, aoOrientar);
  bussolaLigada = true;
  amostrasBussola.length = 0;
  ultimaLeitura = null;
  botaoBussola.textContent = "Desligar bússola";
  botaoRegistrarBussola.disabled = false;
  leituraBussola.textContent = "Aguardando a primeira leitura…";
  statusBussola.textContent = "Bússola ativada. Se nenhum valor aparecer, o aparelho não envia dados de orientação.";
}

function registrarBussola(): void {
  if (!aparelho()) {
    statusBussola.textContent = "Preencha o campo Aparelho antes de registrar.";
    campoAparelho.focus();
    return;
  }
  if (!ultimaLeitura) {
    statusBussola.textContent = "Ainda não há leitura da bússola para registrar.";
    return;
  }
  const oscilacao = oscilacaoBussola(amostrasBussola, Date.now());
  adicionarRegistro(
    montarRegistroBussola({
      rumo_graus: Math.round(ultimaLeitura.rumo_graus * 100) / 100,
      fonte: ultimaLeitura.fonte,
      oscilacao,
      aparelho: aparelho(),
      userAgent: navigator.userAgent,
      agora: new Date(),
    }),
  );
  statusBussola.textContent = oscilacao
    ? `Registrado: rumo ${Math.round(ultimaLeitura.rumo_graus)}°, oscilação de ${oscilacao.oscilacao_graus}° nos últimos 3 s (${oscilacao.amostras} leituras).`
    : `Registrado: rumo ${Math.round(ultimaLeitura.rumo_graus)}°, sem leituras nos últimos 3 s para medir a oscilação.`;
}

// ---------- vibração ----------

function testarVibracao(): void {
  if (!aparelho()) {
    statusVibracao.textContent = "Preencha o campo Aparelho antes de testar.";
    campoAparelho.focus();
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
  adicionarRegistro(
    montarRegistroVibracao({ existe, retorno, aparelho: aparelho(), userAgent: navigator.userAgent, agora: new Date() }),
  );
  statusVibracao.textContent = existe
    ? `Resultado: a API de vibração existe e retornou ${retorno ? "verdadeiro" : "falso"}. Confirme se o aparelho vibrou e anote.`
    : "Resultado: este aparelho não tem a API de vibração (esperado no iPhone). Registrado como resultado do teste.";
}

// ---------- exportar e apagar ----------

function exportarCsv(): void {
  if (registros.length === 0) {
    statusRegistros.textContent = "Não há registros para exportar.";
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
  statusRegistros.textContent = `CSV gerado com ${registros.length} registros: ${nome}.`;
}

function pedirConfirmacaoApagar(): void {
  if (registros.length === 0) {
    statusRegistros.textContent = "Não há registros para apagar.";
    return;
  }
  textoConfirmar.textContent = `Apagar os ${registros.length} registros deste aparelho? Isso não pode ser desfeito. Exporte o CSV antes.`;
  caixaConfirmar.hidden = false;
  botaoApagarNao.focus();
}

function fecharConfirmacao(): void {
  caixaConfirmar.hidden = true;
  botaoApagar.focus();
}

function apagarTudo(): void {
  registros = [];
  salvarRegistros();
  desenharLista();
  fecharConfirmacao();
  statusRegistros.textContent = "Todos os registros foram apagados.";
}

// ---------- inicialização ----------

if (window.isSecureContext === false) {
  el("aviso-https").hidden = false;
}

registros = carregarRegistros();
campoAparelho.value = lerAparelhoSalvo();
desenharLista();

campoAparelho.addEventListener("change", () => {
  salvarAparelho();
  const p = pontoInformado();
  if (p !== null) statusPonto.textContent = textoContagemDoPonto(p);
});
campoPonto.addEventListener("change", () => {
  const p = pontoInformado();
  statusPonto.textContent = p === null ? "Número do ponto inválido. Use de 1 a 12." : textoContagemDoPonto(p);
});
botaoRegistrar.addEventListener("click", registrarPonto);
botaoTrajeto.addEventListener("click", alternarTrajeto);
botaoBussola.addEventListener("click", () => void ativarBussola());
botaoRegistrarBussola.addEventListener("click", registrarBussola);
botaoVibrar.addEventListener("click", testarVibracao);
botaoExportar.addEventListener("click", exportarCsv);
botaoApagar.addEventListener("click", pedirConfirmacaoApagar);
botaoApagarSim.addEventListener("click", apagarTudo);
botaoApagarNao.addEventListener("click", fecharConfirmacao);

iniciarSeletorTema();
