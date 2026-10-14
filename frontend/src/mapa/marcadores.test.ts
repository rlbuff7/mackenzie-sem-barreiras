import assert from "node:assert/strict";
import { test } from "node:test";
import { htmlMarcadorPosicao, htmlPinoEntradaAcessivel } from "./marcadores.ts";

test("sem rumo, o marcador é só a bola (sem seta)", () => {
  const html = htmlMarcadorPosicao(null);
  assert.ok(html.includes("mapa-bola"));
  assert.ok(!html.includes("mapa-seta"));
});

test("com rumo, a seta vem girada pelo rumo em graus", () => {
  const html = htmlMarcadorPosicao(135);
  assert.ok(html.includes("mapa-seta"));
  assert.ok(html.includes("rotate(135deg)"));
});

test("rumo 0 (norte) também mostra a seta: zero não é 'sem rumo'", () => {
  assert.ok(htmlMarcadorPosicao(0).includes("mapa-seta"));
});

test("o pino de entrada acessível é outra forma, não a bola", () => {
  const html = htmlPinoEntradaAcessivel();
  assert.ok(html.includes("mapa-pino"));
  assert.ok(!html.includes("mapa-bola"));
});
