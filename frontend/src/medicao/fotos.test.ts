import assert from "node:assert/strict";
import { test } from "node:test";
import {
  altDaFoto,
  dimensoesReduzidas,
  interpretarRespostaFoto,
  textoEstadoFoto,
  urlDaFoto,
} from "./fotos.ts";

test("dimensões: lado maior vai a 1280 mantendo a proporção; foto menor não cresce", () => {
  assert.deepEqual(dimensoesReduzidas(4000, 3000), { largura_px: 1280, altura_px: 960 });
  assert.deepEqual(dimensoesReduzidas(3000, 4000), { largura_px: 960, altura_px: 1280 });
  assert.deepEqual(dimensoesReduzidas(1280, 720), { largura_px: 1280, altura_px: 720 });
  assert.deepEqual(dimensoesReduzidas(800, 600), { largura_px: 800, altura_px: 600 });
  assert.deepEqual(dimensoesReduzidas(10000, 3), { largura_px: 1280, altura_px: 1 });
});

test("URL: query com encodeURIComponent, opcionais só quando existem", () => {
  const u = urlDaFoto({
    id_cliente: "abc-123",
    ponto: 3,
    aparelho: "Galaxy A54 & cia/ção",
    tirada_em: "2026-10-22T14:03:00.000Z",
    largura_px: 1280,
    altura_px: 960,
  });
  assert.equal(
    u,
    "/api/medicoes/fotos?id_cliente=abc-123&ponto=3&aparelho=Galaxy%20A54%20%26%20cia%2F%C3%A7%C3%A3o" +
      "&tirada_em=2026-10-22T14%3A03%3A00.000Z&largura_px=1280&altura_px=960",
  );
  const sem = urlDaFoto({ id_cliente: "x", ponto: 1, aparelho: "A", tirada_em: "t" });
  assert.ok(!sem.includes("largura_px") && !sem.includes("observacao"));
  assert.ok(urlDaFoto({ id_cliente: "x", ponto: 1, aparelho: "A", tirada_em: "t", observacao: " a b " }).endsWith("observacao=a%20b"));
});

test("respostas: 200 gravada/repetida, 401, 413/415/422, resto fica na fila", () => {
  assert.deepEqual(interpretarRespostaFoto(200, { gravada: true }), { tipo: "enviada", repetida: false });
  assert.deepEqual(interpretarRespostaFoto(200, { gravada: false }), { tipo: "enviada", repetida: true });
  assert.equal(interpretarRespostaFoto(200, "<html>").tipo, "fila");
  assert.deepEqual(interpretarRespostaFoto(401, null), { tipo: "codigo_errado" });
  assert.deepEqual(interpretarRespostaFoto(413, null), { tipo: "recusada", motivo: "foto grande demais" });
  assert.equal(interpretarRespostaFoto(415, null).tipo, "recusada");
  const r = interpretarRespostaFoto(422, { mensagem: "A foto tem metadados (EXIF); envie pelo app, que remove.", erros: [] });
  assert.deepEqual(r, { tipo: "recusada", motivo: "A foto tem metadados (EXIF); envie pelo app, que remove." });
  for (const s of [503, 429, 500, 502, 404]) assert.equal(interpretarRespostaFoto(s, null).tipo, "fila", String(s));
  assert.equal(interpretarRespostaFoto(null, null).tipo, "fila");
});

test("texto do estado em palavra e alt da miniatura", () => {
  assert.equal(textoEstadoFoto("P03", "enviada", null), "Foto do P03: enviada ✓");
  assert.equal(textoEstadoFoto("P03", "na_fila", "sem sinal"), "Foto do P03: na fila, sem sinal");
  assert.equal(textoEstadoFoto("P03", "na_fila", "falta o código da equipe"), "Foto do P03: na fila, falta o código da equipe");
  assert.equal(textoEstadoFoto("P03", "recusada", "foto grande demais"), "Foto do P03: recusada: foto grande demais");
  assert.equal(altDaFoto("P03"), "Foto do ponto P03");
});
