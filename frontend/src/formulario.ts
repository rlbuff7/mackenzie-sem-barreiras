/**
 * Formulário de envio de alerta: carrega os tipos de barreira, valida o
 * essencial no cliente (tipo escolhido e ponto selecionado) e delega toda a
 * validação de negócio à API, mostrando a `mensagem` do servidor (ou a lista
 * de erros por campo, em caso de 422) numa região `aria-live="polite"`.
 */

import { buscarTiposBarreira, enviarAlerta, type PayloadAlerta } from "./api";
import { obterSessaoId } from "./sessao";
import type { ControladorMapa, PontoSelecionado } from "./mapa";

const LIMITE_DESCRICAO = 500;

export interface ControladorFormulario {
  /** Chamado pelo main.ts sempre que o ponto do alerta muda no mapa. */
  definirPontoSelecionado(ponto: PontoSelecionado): void;
}

function elementoObrigatorio<T extends HTMLElement>(id: string): T {
  const elemento = document.getElementById(id);
  if (!elemento) {
    throw new Error(`Elemento obrigatório não encontrado: #${id}`);
  }
  return elemento as T;
}

function lerSeveridadeSelecionada(formulario: HTMLFormElement): number | null {
  const marcada = formulario.querySelector<HTMLInputElement>(
    'input[name="severidade"]:checked',
  );
  return marcada ? Number(marcada.value) : null;
}

function formatarMensagemErro(mensagem: string, erros: Array<{ campo: string; erro: string }>): string {
  if (erros.length === 0) {
    return mensagem;
  }
  const detalhes = erros.map((item) => `${item.campo}: ${item.erro}`).join(" ");
  return `${mensagem} ${detalhes}`;
}

export async function iniciarFormulario(
  controladorMapa: ControladorMapa,
): Promise<ControladorFormulario> {
  const formulario = elementoObrigatorio<HTMLFormElement>("formulario-alerta");
  const campoTipo = elementoObrigatorio<HTMLSelectElement>("campo-tipo");
  const campoDescricao = elementoObrigatorio<HTMLTextAreaElement>("campo-descricao");
  const contadorDescricao = elementoObrigatorio<HTMLParagraphElement>("contador-descricao");
  const statusEnvio = elementoObrigatorio<HTMLParagraphElement>("status-envio");
  const pontoSelecionadoTexto = elementoObrigatorio<HTMLParagraphElement>("ponto-selecionado");
  const botaoEnviar = formulario.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (!botaoEnviar) {
    throw new Error("Botão de envio não encontrado no formulário.");
  }

  let pontoAtual: PontoSelecionado | null = null;

  campoDescricao.addEventListener("input", () => {
    contadorDescricao.textContent = `${campoDescricao.value.length} / ${LIMITE_DESCRICAO} caracteres`;
  });

  try {
    const tipos = await buscarTiposBarreira();
    campoTipo.innerHTML = "";
    for (const tipo of tipos) {
      const opcao = document.createElement("option");
      opcao.value = tipo.codigo;
      opcao.textContent = tipo.nome;
      // Sem descrição, nenhum `title`: atribuir null escreveria o texto "null".
      if (tipo.descricao) {
        opcao.title = tipo.descricao;
      }
      campoTipo.appendChild(opcao);
    }
  } catch (erro) {
    console.error("Falha ao carregar tipos de barreira:", erro);
    campoTipo.innerHTML = '<option value="">Não foi possível carregar os tipos</option>';
    statusEnvio.textContent =
      "Não foi possível carregar os tipos de barreira. Recarregue a página para tentar de novo.";
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    if (!campoTipo.value) {
      statusEnvio.textContent = "Escolha o tipo de barreira antes de enviar.";
      campoTipo.focus();
      return;
    }

    if (!pontoAtual) {
      statusEnvio.textContent =
        "Selecione um ponto no mapa, use sua localização ou o centro do mapa antes de enviar.";
      // O aviso pede uma escolha de ponto: leva o foco aos botões que a fazem
      // (o primeiro deles), em vez de deixá-lo no botão "Enviar".
      elementoObrigatorio<HTMLButtonElement>("botao-localizacao").focus();
      return;
    }

    const ponto = pontoAtual;
    botaoEnviar.disabled = true;
    const rotuloOriginal = botaoEnviar.textContent;
    botaoEnviar.textContent = "Enviando…";
    statusEnvio.textContent = "Enviando alerta…";

    try {
      // Dentro do `try`: se a sessão não puder ser criada, a falha aparece na
      // mensagem do `catch` e o botão volta, em vez de o envio sumir calado.
      const payload: PayloadAlerta = {
        latitude: ponto.latitude,
        longitude: ponto.longitude,
        tipo: campoTipo.value,
        severidade: lerSeveridadeSelecionada(formulario),
        descricao: campoDescricao.value.trim() === "" ? null : campoDescricao.value,
        sessao_id: obterSessaoId(),
      };
      const resultado = await enviarAlerta(payload);

      if (resultado.tipo === "sucesso") {
        statusEnvio.textContent = resultado.dados.mensagem;
        formulario.reset();
        contadorDescricao.textContent = `0 / ${LIMITE_DESCRICAO} caracteres`;
        pontoAtual = null;
        controladorMapa.limparSelecao();
        pontoSelecionadoTexto.textContent =
          "Alerta enviado. Selecione um novo ponto para reportar outra barreira.";
      } else if (resultado.tipo === "erro_validacao") {
        statusEnvio.textContent = formatarMensagemErro(
          resultado.dados.mensagem,
          resultado.dados.erros,
        );
      } else {
        statusEnvio.textContent = resultado.mensagem;
      }
    } catch (erro) {
      // enviarAlerta já trata rede e JSON malformado internamente; este catch
      // é uma rede de segurança para não deixar o botão travado em "Enviando…"
      // caso surja alguma falha imprevista aqui na própria interface (inclusive
      // ao criar o identificador da sessão).
      console.error("Falha inesperada ao processar o envio do alerta:", erro);
      statusEnvio.textContent =
        "Não foi possível concluir o envio por um erro inesperado. Tente novamente.";
    } finally {
      botaoEnviar.disabled = false;
      botaoEnviar.textContent = rotuloOriginal;
    }
  });

  return {
    definirPontoSelecionado(ponto: PontoSelecionado): void {
      pontoAtual = ponto;
    },
  };
}
