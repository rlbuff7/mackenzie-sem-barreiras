import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CHAVE_VOZ_ATIVA,
  NOME_DO_APP,
  guardarVozAtiva,
  lerVozAtiva,
  notaDaVoz,
  estadoVisualDaVoz,
  ROTULO_DO_BOTAO_DE_VOZ,
  tituloDaPagina,
} from "./orientacao.ts";

function armazemFalso(inicial: Record<string, string> = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    dados,
    getItem: (c: string) => dados.get(c) ?? null,
    setItem: (c: string, v: string) => void dados.set(c, v),
    removeItem: (c: string) => void dados.delete(c),
  };
}

test("o título da página é '<Tela> · Navegação Acessível no Campus'", () => {
  assert.equal(NOME_DO_APP, "Navegação Acessível no Campus");
  assert.equal(tituloDaPagina("Rota traçada"), "Rota traçada · Navegação Acessível no Campus");
  assert.equal(tituloDaPagina("Etapa 2 de 3: Medir o ponto"), "Etapa 2 de 3: Medir o ponto · Navegação Acessível no Campus");
});

test("rótulo FIXO 'Voz do site'; o estado visual é Ligada/Desligada", () => {
  assert.equal(ROTULO_DO_BOTAO_DE_VOZ, "Voz do site");
  assert.equal(estadoVisualDaVoz(false), "Desligada");
  assert.equal(estadoVisualDaVoz(true), "Ligada");
  assert.notEqual(notaDaVoz(true), notaDaVoz(false));
});

test("preferência da voz: só '1' liga; sem armazenamento ou com erro, desligada", () => {
  assert.equal(CHAVE_VOZ_ATIVA, "msb-voz-ativa");
  assert.equal(lerVozAtiva(armazemFalso()), false);
  assert.equal(lerVozAtiva(armazemFalso({ [CHAVE_VOZ_ATIVA]: "1" })), true);
  assert.equal(lerVozAtiva(armazemFalso({ [CHAVE_VOZ_ATIVA]: "sim" })), false);
  assert.equal(lerVozAtiva(null), false);
  const quebrado = {
    getItem: () => {
      throw new Error("bloqueado");
    },
    setItem: () => {
      throw new Error("bloqueado");
    },
    removeItem: () => {
      throw new Error("bloqueado");
    },
  };
  assert.equal(lerVozAtiva(quebrado), false);
  assert.doesNotThrow(() => guardarVozAtiva(quebrado, true));
  assert.doesNotThrow(() => guardarVozAtiva(null, true));
});

test("guardarVozAtiva grava '1' ao ligar e apaga ao desligar", () => {
  const a = armazemFalso();
  guardarVozAtiva(a, true);
  assert.equal(a.dados.get(CHAVE_VOZ_ATIVA), "1");
  guardarVozAtiva(a, false);
  assert.equal(a.dados.has(CHAVE_VOZ_ATIVA), false);
});
