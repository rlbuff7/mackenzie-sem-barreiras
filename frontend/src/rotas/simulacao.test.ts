import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  comprimentoTotal_m, fatorValido, metrosPorPasso, padraoDeVibracao, pontoNaDistancia, proximaFala, textoDaCurva,
} from "./simulacao.ts";

const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");
// ~111 m por 0,001 grau de latitude.
const linha: [number, number][] = [[-46.65, -23.55], [-46.65, -23.549], [-46.649, -23.549]];

test("pontoNaDistancia: início, meio do primeiro trecho, fim e além do fim", () => {
  assert.deepEqual(pontoNaDistancia(linha, 0), linha[0]);
  const total = comprimentoTotal_m(linha);
  assert.ok(total > 200 && total < 220);
  const meio = pontoNaDistancia(linha, 55.6)!;
  assert.equal(meio[0], -46.65);
  assert.ok(Math.abs(meio[1] - -23.5495) < 0.0001);
  assert.deepEqual(pontoNaDistancia(linha, total + 50), linha[2]);
  assert.equal(pontoNaDistancia([], 5), null);
});

test("proximaFala: instrução fala ao cruzar inicio_m, uma vez", () => {
  const ins = [{ texto: "A", inicio_m: 0 }, { texto: "B", inicio_m: 50 }, { texto: "Chegou", inicio_m: 100 }];
  const ja = new Set<string>();
  assert.equal(proximaFala(ins, 0, ja, 120)?.texto, "A");
  ja.add("i:0");
  assert.equal(proximaFala(ins, 49, ja, 120), null);
  assert.equal(proximaFala(ins, 50, ja, 120)?.texto, "B");
});

test("proximaFala: aviso de curva 10 m antes do fim da instrução", () => {
  const ins = [{ texto: "A", inicio_m: 0, curva: "direita" as const }, { texto: "B", inicio_m: 50 }];
  const ja = new Set(["i:0"]);
  assert.equal(proximaFala(ins, 39, ja, 100), null);
  const f = proximaFala(ins, 40, ja, 100)!;
  assert.equal(f.texto, "Em 10 metros, vire à direita.");
  assert.equal(f.curva, "direita");
});

test("proximaFala: sem inicio_m distribui igualmente e não avisa curva", () => {
  const ins = [{ texto: "A", curva: "esquerda" as const }, { texto: "B" }];
  assert.equal(proximaFala(ins, 0, new Set(), 100)?.texto, "A");
  assert.equal(proximaFala(ins, 49, new Set(["i:0"]), 100), null);
  assert.equal(proximaFala(ins, 50, new Set(["i:0"]), 100)?.texto, "B");
});

test("padrões de vibração", () => {
  assert.deepEqual(padraoDeVibracao("direita"), [80, 80, 80]);
  assert.deepEqual(padraoDeVibracao("esquerda"), [300]);
  assert.deepEqual(padraoDeVibracao("leve_direita"), [80]);
  assert.deepEqual(padraoDeVibracao("leve_esquerda"), [80]);
  assert.deepEqual(padraoDeVibracao("retorno"), [300, 100, 300]);
  assert.deepEqual(padraoDeVibracao("escada"), [80, 60, 80, 60, 80]);
  assert.deepEqual(padraoDeVibracao(null), []);
  assert.match(textoDaCurva("retorno"), /retorno/);
});

test("velocidade: 10× por padrão, 2,5 m por passo", () => {
  assert.equal(fatorValido("x"), 10);
  assert.equal(fatorValido("5"), 5);
  assert.equal(metrosPorPasso(10), 2.5);
});

test("HTML da simulação: botões, seletor, rótulo", () => {
  for (const id of ["botao-simular", "seletor-velocidade-simulacao", "botao-parar-simulacao", "aviso-simulacao"]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.ok(html.includes("Simulação: a posição é imaginária, não é o GPS."));
  assert.match(html, /<option value="10" selected>/);
  assert.ok(html.includes(">Simular caminhada<"));
});
