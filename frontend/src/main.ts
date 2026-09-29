import "./estilos.css";
import { iniciarMapa, type ItemListaBarreira, type PontoSelecionado } from "./mapa";
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

/**
 * Alternativa acessível aos marcadores do mapa (que ficam fora da ordem de
 * tabulação): a mesma lista de barreiras da bbox atual, como botões de
 * verdade. Nunca usa innerHTML com texto vindo do servidor — tudo aqui é
 * `createElement` + `textContent`.
 */
function renderizarListaBarreiras(
  lista: HTMLUListElement,
  contagem: HTMLParagraphElement,
  itens: ItemListaBarreira[],
  aoAtivarItem: (id: number) => void,
): void {
  if (itens.length === 0) {
    const vazio = document.createElement("li");
    vazio.className = "item-barreira-vazio";
    vazio.textContent = "Nenhuma barreira validada nesta área ainda.";
    lista.replaceChildren(vazio);
  } else {
    const fragmento = document.createDocumentFragment();
    for (const item of itens) {
      const li = document.createElement("li");
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "item-barreira";

      const tipo = document.createElement("span");
      tipo.className = "item-barreira__tipo";
      tipo.textContent = item.tipoNome;

      const status = document.createElement("span");
      status.className = "item-barreira__detalhe";
      status.textContent = `Status: ${item.status === "confirmada" ? "Confirmada" : "Pendente"}`;

      const confirmacoes = document.createElement("span");
      confirmacoes.className = "item-barreira__detalhe";
      confirmacoes.textContent =
        item.confirmacoes === 1 ? "1 confirmação" : `${item.confirmacoes} confirmações`;

      const acao = document.createElement("span");
      acao.className = "item-barreira__acao";
      acao.textContent = "Ver no mapa";

      botao.append(tipo, status, confirmacoes, acao);
      botao.addEventListener("click", () => aoAtivarItem(item.id));
      li.appendChild(botao);
      fragmento.appendChild(li);
    }
    lista.replaceChildren(fragmento);
  }

  const novaContagemTexto =
    itens.length === 0
      ? "Nenhuma barreira nesta área."
      : itens.length === 1
        ? "1 barreira nesta área."
        : `${itens.length} barreiras nesta área.`;

  // Só reescreve se o texto mudou, para a região aria-live não anunciar de
  // novo a cada recarga que resulta na mesma contagem.
  if (contagem.textContent !== novaContagemTexto) {
    contagem.textContent = novaContagemTexto;
  }
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
  const listaBarreiras = elementoObrigatorio<HTMLUListElement>("lista-barreiras");
  const contagemBarreiras = elementoObrigatorio<HTMLParagraphElement>("contagem-barreiras");

  const controladorMapa = await iniciarMapa("mapa");
  const controladorFormulario = await iniciarFormulario(controladorMapa);

  controladorMapa.aoSelecionarPonto((ponto) => {
    controladorFormulario.definirPontoSelecionado(ponto);
    pontoSelecionadoTexto.textContent = `Ponto selecionado: ${formatarPonto(ponto)}.`;
  });

  const atualizarListaBarreiras = (itens: ItemListaBarreira[]): void => {
    renderizarListaBarreiras(listaBarreiras, contagemBarreiras, itens, (id) => {
      controladorMapa.focarBarreira(id);
    });
  };
  atualizarListaBarreiras(controladorMapa.obterItensAtuais());
  controladorMapa.aoAtualizarBarreiras(atualizarListaBarreiras);

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
