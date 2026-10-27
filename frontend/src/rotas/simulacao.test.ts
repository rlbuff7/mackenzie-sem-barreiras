import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  comprimentoTotal_m, fatorValido, metrosPorPasso, padraoDeVibracao, planejarFalas, pontoNaDistancia, proximoEvento, textoDaCurva,
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

test("proximoEvento: instrução fala ao cruzar inicio_m, uma vez", () => {
  const ev = planejarFalas([{ texto: "A", inicio_m: 0 }, { texto: "B", inicio_m: 50 }, { texto: "Chegou", inicio_m: 100 }], 120, 5);
  const ja = new Set<string>();
  assert.equal(proximoEvento(ev, 0, ja)?.texto, "A");
  ja.add("i:0");
  assert.equal(proximoEvento(ev, 49, ja), null);
  assert.equal(proximoEvento(ev, 50, ja)?.texto, "B");
});

test("aviso de curva sai quando faltam 3 s de reprodução, nas três velocidades", () => {
  const ins = [{ texto: "Siga reto por um bom trecho.", inicio_m: 0, curva: "direita" as const }, { texto: "B", inicio_m: 200 }];
  for (const [fator, antes_m] of [[2, 6], [5, 15], [10, 30]] as const) {
    const ev = planejarFalas(ins, 300, fator);
    const aviso = ev.find((e) => e.chave === "a:0")!;
    assert.equal(aviso.m, 200 - antes_m, `fator ${fator}`);
    assert.equal(aviso.texto, `Em ${Math.round(antes_m / 5) * 5} metros, vire à direita.`);
    assert.deepEqual(aviso.vibrar, []);
    assert.equal(aviso.prioridade, "normal");
  }
  // 2×: 6 m reais -> 5 m arredondado; mínimo 5 m mesmo em velocidade baixa (1× = 3 m -> 5).
  assert.equal(planejarFalas(ins, 300, 1).find((e) => e.chave === "a:0")!.m, 195);
});

test("fala 'agora' ao fim da instrução com curva: prioridade alta e vibração", () => {
  const ins = [{ texto: "Siga reto por um bom trecho.", inicio_m: 0, curva: "leve_esquerda" as const }, { texto: "B", inicio_m: 100 }];
  const agora = planejarFalas(ins, 150, 5).find((e) => e.chave === "c:0")!;
  assert.equal(agora.m, 100);
  assert.equal(agora.texto, "Vire levemente à esquerda agora.");
  assert.equal(agora.prioridade, "alta");
  assert.deepEqual(agora.vibrar, [80]);
  const textos = (c: "retorno" | "escada" | "direita") =>
    planejarFalas([{ texto: "A. B.", inicio_m: 0, curva: c }, { texto: "C", inicio_m: 100 }], 150, 5).find((e) => e.chave === "c:0")!.texto;
  assert.equal(textos("retorno"), "Faça o retorno agora.");
  assert.equal(textos("escada"), "Escada agora. Use o corrimão se houver.");
  assert.equal(textos("direita"), "Vire à direita agora.");
});

test("início de instrução não atropela a curva: 1ª frase se < 4 s, pula se imediata", () => {
  // 5×: 15 m = 3 s -> só a primeira frase.
  const curta = planejarFalas([{ texto: "Vire. Depois siga.", inicio_m: 0, curva: "direita" as const }, { texto: "B", inicio_m: 15 }], 50, 5);
  assert.equal(curta.find((e) => e.chave === "i:0")!.texto, "Vire.");
  // 5×: 5 m = 1 s -> pula.
  const imediata = planejarFalas([{ texto: "Vire. Depois siga.", inicio_m: 0, curva: "direita" as const }, { texto: "B", inicio_m: 5 }], 50, 5);
  assert.equal(imediata.find((e) => e.chave === "i:0"), undefined);
  // Longa: texto inteiro.
  const longa = planejarFalas([{ texto: "Vire. Depois siga.", inicio_m: 0, curva: "direita" as const }, { texto: "B", inicio_m: 100 }], 150, 5);
  assert.equal(longa.find((e) => e.chave === "i:0")!.texto, "Vire. Depois siga.");
});

test("sem inicio_m: distribui igualmente e não avisa curva", () => {
  const ev = planejarFalas([{ texto: "A", curva: "esquerda" as const }, { texto: "B" }], 100, 5);
  assert.deepEqual(ev.map((e) => e.chave), ["i:0", "i:1"]);
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

test("velocidade: 5× por padrão; 2×, 5× e 10× válidas", () => {
  assert.equal(fatorValido("x"), 5);
  assert.equal(fatorValido("2"), 2);
  assert.equal(fatorValido("10"), 10);
  assert.equal(metrosPorPasso(10), 2.5);
  assert.equal(metrosPorPasso(2), 0.5);
});

test("HTML da simulação: botões, seletor, rótulo", () => {
  for (const id of ["botao-simular", "seletor-velocidade-simulacao", "botao-parar-simulacao", "aviso-simulacao"]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.ok(html.includes("Simulação: a posição é imaginária, não é o GPS."));
  assert.match(html, /<option value="2">2×<\/option>/);
  assert.match(html, /<option value="5" selected>/);
  assert.match(html, /<option value="10">10×<\/option>/);
  assert.ok(html.includes(">Simular caminhada<"));
});
