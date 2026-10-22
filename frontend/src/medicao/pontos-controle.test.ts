import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CENTRO_CAMPUS,
  PONTOS_CONTROLE,
  RAIO_CAMPUS_M,
  distanciaMetros,
  opcoesDePontos,
  textoOpcaoPonto,
  pontoDeControle,
  textoDistanciaReferencia,
  tituloDoPonto,
} from "./pontos-controle.ts";
import { ROTULO_CONDICAO } from "./medicao.ts";
import { TOTAL_PONTOS } from "./fluxo.ts";

test("são 10 pontos de controle, numerados de 1 a 10 sem repetir", () => {
  assert.equal(PONTOS_CONTROLE.length, 10);
  assert.deepEqual(PONTOS_CONTROLE.map((p) => p.numero), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.equal(new Set(PONTOS_CONTROLE.map((p) => p.codigo)).size, 10);
  assert.equal(TOTAL_PONTOS, PONTOS_CONTROLE.length);
});

test("código P01..P10 acompanha o número", () => {
  for (const p of PONTOS_CONTROLE) assert.equal(p.codigo, `P${String(p.numero).padStart(2, "0")}`);
});

test("todas as referências ficam dentro do campus (recorte provisório de 500 m do seed 002)", () => {
  for (const p of PONTOS_CONTROLE) {
    const d = distanciaMetros(CENTRO_CAMPUS[0], CENTRO_CAMPUS[1], p.referencia_lat, p.referencia_lon);
    assert.ok(d <= RAIO_CAMPUS_M, `${p.codigo} a ${Math.round(d)} m do centro`);
  }
});

test("condição é uma das que a API aceita", () => {
  for (const p of PONTOS_CONTROLE) {
    assert.ok(p.condicao in ROTULO_CONDICAO, p.codigo);
    assert.ok(p.nome.length > 0 && p.observacao.length > 0, p.codigo);
  }
  assert.equal(pontoDeControle(1)?.condicao, "ceu_aberto");
  assert.equal(pontoDeControle(3)?.condicao, "entre_predios");
  for (const n of [4, 5, 6]) assert.equal(pontoDeControle(n)?.condicao, "entrada_predio");
});

test("pontoDeControle: fora de 1..10 é undefined", () => {
  assert.equal(pontoDeControle(0), undefined);
  assert.equal(pontoDeControle(11), undefined);
  assert.equal(pontoDeControle(3)?.codigo, "P03");
});

test("tituloDoPonto: 'P03 · Passagem entre os Prédios 6 e 24'", () => {
  assert.equal(tituloDoPonto(pontoDeControle(3)!), "P03 · Passagem entre os Prédios 6 e 24");
});

test("distanciaMetros: zero no mesmo ponto; 0,001 grau de latitude é cerca de 111 m", () => {
  assert.equal(distanciaMetros(-23.5, -46.6, -23.5, -46.6), 0);
  const d = distanciaMetros(-23.5, -46.6, -23.499, -46.6);
  assert.ok(d > 110 && d < 112, String(d));
});

test("textoDistanciaReferencia: metros por extenso, plural certo e aviso de estimativa", () => {
  assert.match(textoDistanciaReferencia(14.4), /^Referência a 14 metros\./);
  assert.match(textoDistanciaReferencia(1.2), /^Referência a 1 metro\./);
  assert.match(textoDistanciaReferencia(0.3), /^Referência a menos de 1 metro\./);
  for (const t of [textoDistanciaReferencia(14), textoDistanciaReferencia(null)]) {
    assert.match(t, /estimativa por imagem de satélite/);
  }
  assert.doesNotMatch(textoDistanciaReferencia(null), /metro/);
});

test("opcoesDePontos: 10 opções 'P01 · nome curto', '· feito' só nos pontos completos", () => {
  const ops = opcoesDePontos(new Set([2, 10]));
  assert.equal(ops.length, 10);
  assert.deepEqual(ops.map((o) => o.valor), ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]);
  assert.equal(ops[0]?.texto, "P01 · Praça do Prédio 18");
  assert.equal(ops[1]?.texto, "P02 · Biblioteca Central · feito");
  assert.equal(ops[9]?.texto, "P10 · Circulação do Auditório · feito");
  assert.equal(ops.filter((o) => o.texto.endsWith(" · feito")).length, 2);
  assert.equal(opcoesDePontos(new Set()).filter((o) => o.texto.includes("feito")).length, 0);
});

test("nomes curtos: até 24 caracteres e a opção mais longa cabe em ~36 caracteres", () => {
  for (const p of PONTOS_CONTROLE) assert.ok(p.nome_curto.length > 0 && p.nome_curto.length <= 24, p.codigo);
  for (const p of PONTOS_CONTROLE) assert.ok(textoOpcaoPonto(p, true).length <= 38, p.codigo);
});
