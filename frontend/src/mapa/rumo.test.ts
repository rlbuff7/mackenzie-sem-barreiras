import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizarRumo_graus, rumoParaSeta } from "./rumo.ts";

const semNada = { rumo_gps_graus: null, velocidade_ms: null, bussola: null };

test("sem GPS em movimento e sem bússola: nada de seta", () => {
  assert.equal(rumoParaSeta(semNada), null);
});

test("heading do GPS com o aparelho em movimento vira seta", () => {
  assert.equal(rumoParaSeta({ ...semNada, rumo_gps_graus: 90, velocidade_ms: 1.2 }), 90);
});

test("heading do GPS parado (velocidade baixa, nula ou NaN) é ignorado", () => {
  assert.equal(rumoParaSeta({ ...semNada, rumo_gps_graus: 90, velocidade_ms: 0.1 }), null);
  assert.equal(rumoParaSeta({ ...semNada, rumo_gps_graus: 90, velocidade_ms: null }), null);
  assert.equal(rumoParaSeta({ ...semNada, rumo_gps_graus: Number.NaN, velocidade_ms: 2 }), null);
});

test("bússola absoluta vira seta; relativa nunca", () => {
  assert.equal(rumoParaSeta({ ...semNada, bussola: { rumo_graus: 200, fonte: "alpha_absoluto" } }), 200);
  assert.equal(rumoParaSeta({ ...semNada, bussola: { rumo_graus: 200, fonte: "webkitCompassHeading" } }), 200);
  assert.equal(rumoParaSeta({ ...semNada, bussola: { rumo_graus: 200, fonte: "alpha_relativo" } }), null);
  assert.equal(rumoParaSeta({ ...semNada, bussola: { rumo_graus: 200, fonte: "qualquer_outra" } }), null);
});

test("em movimento, o GPS vence a bússola; parado, vale a bússola absoluta", () => {
  const bussola = { rumo_graus: 10, fonte: "alpha_absoluto" };
  assert.equal(rumoParaSeta({ rumo_gps_graus: 180, velocidade_ms: 1.5, bussola }), 180);
  assert.equal(rumoParaSeta({ rumo_gps_graus: null, velocidade_ms: 0, bussola }), 10);
});

test("normalizarRumo_graus mantém 0 <= x < 360 (359,6 não vira 360)", () => {
  assert.equal(normalizarRumo_graus(359.6), 0);
  assert.equal(normalizarRumo_graus(-90), 270);
  assert.equal(normalizarRumo_graus(725), 5);
});
