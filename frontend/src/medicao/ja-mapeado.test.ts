import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ESTILO_TRAJETO_AO_VIVO,
  ITENS_LEGENDA,
  estiloJaMapeado,
  filtrarJaMapeado,
  htmlLegenda,
  tituloPontoControle,
  type ColecaoJaMapeado,
} from "./ja-mapeado.ts";

const dados = JSON.parse(readFileSync(new URL("./ja-mapeado.json", import.meta.url), "utf8")) as ColecaoJaMapeado;

test("dados: 1 trajeto da equipe, 26 caminhos v0 (com escada) e 10 pontos de controle", () => {
  assert.equal(filtrarJaMapeado(dados, "trajeto_equipe").length, 1);
  const v0 = filtrarJaMapeado(dados, "caminho_v0");
  assert.equal(v0.length, 26);
  assert.ok(v0.some((f) => f.properties.subtipo === "escada"));
  assert.ok(v0.some((f) => f.properties.subtipo === "calcada"));
  const pontos = filtrarJaMapeado(dados, "ponto_controle");
  assert.equal(pontos.length, 10);
  for (const p of pontos) assert.equal(p.geometry.type, "Point");
});

test("estilo: nenhuma linha é interativa; escada é tracejada e mais grossa que a calçada", () => {
  const escada = estiloJaMapeado("caminho_v0", "escada");
  const calcada = estiloJaMapeado("caminho_v0", "calcada");
  const equipe = estiloJaMapeado("trajeto_equipe");
  for (const e of [escada, calcada, equipe, ESTILO_TRAJETO_AO_VIVO, estiloJaMapeado(undefined)]) assert.equal(e.interactive, false);
  assert.ok(escada.dashArray);
  assert.equal(calcada.dashArray, undefined);
  assert.ok(escada.weight > calcada.weight);
});

test("estilo: trajeto ao vivo é sólido e mais forte que o da equipe", () => {
  assert.equal(ESTILO_TRAJETO_AO_VIVO.dashArray, undefined);
  assert.ok(ESTILO_TRAJETO_AO_VIVO.weight > estiloJaMapeado("trajeto_equipe").weight);
  assert.notEqual(ESTILO_TRAJETO_AO_VIVO.className, estiloJaMapeado("trajeto_equipe").className);
});

test("título do ponto de controle", () => {
  assert.equal(tituloPontoControle("P03", "Praça", 3), "P03 · Praça · 3 medições");
  assert.equal(tituloPontoControle("P03", undefined, 1), "P03 · 1 medição");
});

test("legenda: 9 itens, cada um com amostra e texto", () => {
  assert.equal(ITENS_LEGENDA.length, 9);
  const html = htmlLegenda();
  assert.equal(html.match(/<li /g)?.length, 9);
  assert.equal(html.match(/<svg /g)?.length, 9);
  assert.match(html, /até 26\/10 21:30/);
});
