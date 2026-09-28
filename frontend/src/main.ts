import "./estilos.css";
import { iniciarMapa, type PontoSelecionado } from "./mapa";
import { iniciarFormulario } from "./formulario";

function elementoObrigatorio<T extends HTMLElement>(id: string): T {
  const elemento = document.getElementById(id);
  if (!elemento) {
    throw new Error(`Elemento obrigatório não encontrado: #${id}`);
  }
  return elemento as T;
}

function formatarPonto(ponto: PontoSelecionado): string {
  return `${ponto.latitude.toFixed(5)}, ${ponto.longitude.toFixed(5)}`;
}

/** Mensagem em português para cada motivo de falha de geolocalização. */
function mensagemErroGeolocalizacao(erro: GeolocationPositionError): string {
  switch (erro.code) {
    case erro.PERMISSION_DENIED:
      return "Permissão de localização negada. Use o botão \"Usar o centro do mapa\" ou toque num ponto do mapa.";
    case erro.POSITION_UNAVAILABLE:
      return "Não foi possível determinar sua localização agora. Tente novamente ou escolha um ponto no mapa.";
    case erro.TIMEOUT:
      return "A localização demorou demais para responder. Tente novamente ou escolha um ponto no mapa.";
    default:
      return "Não foi possível obter sua localização. Escolha um ponto no mapa.";
  }
}

function obterLocalizacaoAtual(): Promise<PontoSelecionado> {
  return new Promise((resolver, rejeitar) => {
    if (!("geolocation" in navigator)) {
      rejeitar(new Error("Este navegador não oferece geolocalização. Escolha um ponto no mapa."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (posicao) => {
        resolver({ latitude: posicao.coords.latitude, longitude: posicao.coords.longitude });
      },
      (erro) => rejeitar(new Error(mensagemErroGeolocalizacao(erro))),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  });
}

async function principal(): Promise<void> {
  const pontoSelecionadoTexto = elementoObrigatorio<HTMLParagraphElement>("ponto-selecionado");
  const botaoLocalizacao = elementoObrigatorio<HTMLButtonElement>("botao-localizacao");
  const botaoCentro = elementoObrigatorio<HTMLButtonElement>("botao-centro");

  const controladorMapa = await iniciarMapa("mapa");
  const controladorFormulario = await iniciarFormulario(controladorMapa);

  controladorMapa.aoSelecionarPonto((ponto) => {
    controladorFormulario.definirPontoSelecionado(ponto);
    pontoSelecionadoTexto.textContent = `Ponto selecionado: ${formatarPonto(ponto)}.`;
  });

  botaoCentro.addEventListener("click", () => {
    controladorMapa.selecionarPonto(controladorMapa.obterCentro());
  });

  botaoLocalizacao.addEventListener("click", async () => {
    pontoSelecionadoTexto.textContent = "Obtendo sua localização…";
    try {
      const ponto = await obterLocalizacaoAtual();
      controladorMapa.selecionarPonto(ponto);
    } catch (erro) {
      pontoSelecionadoTexto.textContent =
        erro instanceof Error ? erro.message : "Não foi possível obter sua localização.";
    }
  });
}

void principal();
