import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  aplicarMovimento,
  CHAVE_MOVIMENTO,
  lerMovimentoSalvo,
  movimentoReduzido,
  salvarMovimento,
} from "./movimento.ts";
import { CHAVE_TEMA } from "./tema.ts";

function raioFalso() {
  const atributos = new Map<string, string>();
  return {
    atributos,
    setAttribute: (nome: string, valor: string) => void atributos.set(nome, valor),
    removeAttribute: (nome: string) => void atributos.delete(nome),
  };
}

function armazenamentoFalso(inicial: Record<string, string> = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    dados,
    getItem: (chave: string) => dados.get(chave) ?? null,
    setItem: (chave: string, valor: string) => void dados.set(chave, valor),
    removeItem: (chave: string) => void dados.delete(chave),
  };
}

const armazenamentoQueQuebra = {
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

test("a chave é msb-movimento, diferente da do tema", () => {
  assert.equal(CHAVE_MOVIMENTO, "msb-movimento");
  assert.notEqual(CHAVE_MOVIMENTO, CHAVE_TEMA);
});

test("aplicarMovimento põe data-movimento=reduzido ou tira o atributo", () => {
  const raiz = raioFalso();
  aplicarMovimento(raiz, "reduzido");
  assert.equal(raiz.atributos.get("data-movimento"), "reduzido");
  aplicarMovimento(raiz, "padrao");
  assert.equal(raiz.atributos.has("data-movimento"), false);
});

test("lerMovimentoSalvo: só 'reduzido' vale; vazio, estranho ou storage quebrado viram padrão", () => {
  assert.equal(lerMovimentoSalvo(armazenamentoFalso({ [CHAVE_MOVIMENTO]: "reduzido" })), "reduzido");
  assert.equal(lerMovimentoSalvo(armazenamentoFalso({ [CHAVE_MOVIMENTO]: "padrao" })), "padrao");
  assert.equal(lerMovimentoSalvo(armazenamentoFalso({ [CHAVE_MOVIMENTO]: "roxo" })), "padrao");
  assert.equal(lerMovimentoSalvo(armazenamentoFalso()), "padrao");
  assert.equal(lerMovimentoSalvo(armazenamentoQueQuebra), "padrao");
  assert.equal(lerMovimentoSalvo(null), "padrao");
});

test("salvarMovimento grava 'reduzido', apaga a chave no padrão e nunca lança", () => {
  const a = armazenamentoFalso();
  assert.equal(salvarMovimento(a, "reduzido"), true);
  assert.equal(a.dados.get(CHAVE_MOVIMENTO), "reduzido");
  assert.equal(salvarMovimento(a, "padrao"), true);
  assert.equal(a.dados.has(CHAVE_MOVIMENTO), false);
  assert.equal(salvarMovimento(armazenamentoQueQuebra, "reduzido"), false);
  assert.equal(salvarMovimento(null, "reduzido"), false);
});

test("movimentoReduzido: o aparelho pedindo menos movimento vale mesmo com o interruptor desligado", () => {
  assert.equal(movimentoReduzido("padrao", false), false);
  assert.equal(movimentoReduzido("reduzido", false), true);
  assert.equal(movimentoReduzido("padrao", true), true);
  assert.equal(movimentoReduzido("reduzido", true), true);
});

for (const pagina of ["index.html", "medicao.html"]) {
  test(`${pagina}: tem o interruptor "Reduzir animações" e o script do <head> aplica data-movimento`, () => {
    const html = readFileSync(new URL(`../../${pagina}`, import.meta.url), "utf8");
    const entrada = /<input[^>]*id="interruptor-movimento"[^>]*>/.exec(html)?.[0] ?? "";
    assert.match(entrada, /type="checkbox"/);
    assert.match(entrada, /role="switch"/);
    assert.match(html, /<label[^>]*for="interruptor-movimento"[^>]*>\s*Reduzir animações\s*<\/label>/);
    const cabeca = /<head>([\s\S]*?)<\/head>/.exec(html)?.[1] ?? "";
    assert.ok(cabeca.includes(`localStorage.getItem("${CHAVE_MOVIMENTO}")`), "script do <head> sem a chave do movimento");
    assert.ok(cabeca.includes('setAttribute("data-movimento", "reduzido")'), "script do <head> não aplica data-movimento");
    // o interruptor mora ao lado do seletor de tema, no mesmo grupo
    assert.ok(html.indexOf('id="seletor-tema"') < html.indexOf('id="interruptor-movimento"'));
  });
}
