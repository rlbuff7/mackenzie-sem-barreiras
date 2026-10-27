import { test } from "node:test";
import assert from "node:assert/strict";
import { deveReenquadrar, mapaSoltoApos, soltarPorGesto, type MotivoEnquadramento } from "./enquadramento.ts";

test("mapa preso: tudo reenquadra", () => {
  const todos: MotivoEnquadramento[] = ["inicio", "ponto", "etapa", "primeira_posicao", "posicao_fora", "botao_centralizar", "botao_campus"];
  for (const m of todos) assert.equal(deveReenquadrar(m, false), true, m);
});

test("mapa solto: GPS não puxa a vista de volta", () => {
  assert.equal(deveReenquadrar("posicao_fora", true), false);
  assert.equal(deveReenquadrar("primeira_posicao", true), false);
});

test("mapa solto: ponto, etapa, início e botões ainda movem", () => {
  for (const m of ["inicio", "ponto", "etapa", "botao_centralizar", "botao_campus"] as const) {
    assert.equal(deveReenquadrar(m, true), true, m);
  }
});

test("estado depois: centralizar e troca de ponto soltam o controle; campus segura", () => {
  assert.equal(mapaSoltoApos("botao_centralizar", true), false);
  assert.equal(mapaSoltoApos("ponto", true), false);
  assert.equal(mapaSoltoApos("botao_campus", false), true);
  assert.equal(mapaSoltoApos("posicao_fora", true), true);
  assert.equal(mapaSoltoApos("primeira_posicao", false), false);
});

test("só gesto da pessoa solta o mapa", () => {
  assert.equal(soltarPorGesto(false, false), true);
  assert.equal(soltarPorGesto(true, false), false);
  assert.equal(soltarPorGesto(true, true), true);
});
