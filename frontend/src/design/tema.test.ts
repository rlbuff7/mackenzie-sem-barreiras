import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  aplicarTema,
  CHAVE_TEMA,
  ehTemaEscolhido,
  lerTemaSalvo,
  salvarTema,
  temaParaAtributo,
  TEMAS,
} from "./tema.ts";

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

test("TEMAS lista Automático, Claro, Escuro e Alto contraste, nessa ordem", () => {
  assert.deepEqual(
    TEMAS.map((t) => t.valor),
    ["automatico", "claro", "escuro", "alto-contraste"],
  );
  assert.deepEqual(
    TEMAS.map((t) => t.rotulo),
    ["Automático (segue o aparelho)", "Claro", "Escuro", "Alto contraste"],
  );
});

test("ehTemaEscolhido aceita só os 4 valores", () => {
  for (const t of TEMAS) assert.equal(ehTemaEscolhido(t.valor), true);
  assert.equal(ehTemaEscolhido("roxo"), false);
  assert.equal(ehTemaEscolhido(""), false);
  assert.equal(ehTemaEscolhido(null), false);
  assert.equal(ehTemaEscolhido(undefined), false);
});

test("automático não leva data-tema; os outros levam o próprio nome", () => {
  assert.equal(temaParaAtributo("automatico"), null);
  assert.equal(temaParaAtributo("claro"), "claro");
  assert.equal(temaParaAtributo("escuro"), "escuro");
  assert.equal(temaParaAtributo("alto-contraste"), "alto-contraste");
});

test("aplicarTema põe e tira data-tema no html", () => {
  const raiz = raioFalso();
  aplicarTema(raiz, "escuro");
  assert.equal(raiz.atributos.get("data-tema"), "escuro");
  aplicarTema(raiz, "alto-contraste");
  assert.equal(raiz.atributos.get("data-tema"), "alto-contraste");
  aplicarTema(raiz, "automatico");
  assert.equal(raiz.atributos.has("data-tema"), false);
});

test("lerTemaSalvo devolve o salvo; valor estranho, vazio ou storage quebrado viram automático", () => {
  assert.equal(lerTemaSalvo(armazenamentoFalso({ [CHAVE_TEMA]: "escuro" })), "escuro");
  assert.equal(lerTemaSalvo(armazenamentoFalso({ [CHAVE_TEMA]: "alto-contraste" })), "alto-contraste");
  assert.equal(lerTemaSalvo(armazenamentoFalso({ [CHAVE_TEMA]: "roxo" })), "automatico");
  assert.equal(lerTemaSalvo(armazenamentoFalso()), "automatico");
  assert.equal(lerTemaSalvo(armazenamentoQueQuebra), "automatico");
  assert.equal(lerTemaSalvo(null), "automatico");
});

test("salvarTema grava; automático apaga a escolha; storage quebrado devolve false sem lançar", () => {
  const a = armazenamentoFalso();
  assert.equal(salvarTema(a, "claro"), true);
  assert.equal(a.dados.get(CHAVE_TEMA), "claro");
  assert.equal(salvarTema(a, "automatico"), true);
  assert.equal(a.dados.has(CHAVE_TEMA), false);
  assert.equal(salvarTema(armazenamentoQueQuebra, "escuro"), false);
  assert.equal(salvarTema(null, "escuro"), false);
});

for (const pagina of ["index.html", "medicao.html"]) {
  test(`${pagina}: tem o seletor "Tema" com as 4 opções e o script que evita o piscar`, () => {
    const html = readFileSync(new URL(`../../${pagina}`, import.meta.url), "utf8");
    assert.match(html, /<label[^>]*for="seletor-tema"[^>]*>\s*Tema\s*<\/label>/);
    const select = /<select[^>]*id="seletor-tema"[^>]*>([\s\S]*?)<\/select>/.exec(html);
    assert.ok(select, "falta <select id=\"seletor-tema\">");
    const opcoes = [...select[1]!.matchAll(/<option value="([^"]+)">([^<]+)<\/option>/g)].map((m) => [
      m[1],
      m[2]!.trim(),
    ]);
    assert.deepEqual(
      opcoes,
      TEMAS.map((t) => [t.valor, t.rotulo]),
    );
    assert.ok(html.includes(`localStorage.getItem("${CHAVE_TEMA}")`), "script do <head> com a chave errada");
  });
}
