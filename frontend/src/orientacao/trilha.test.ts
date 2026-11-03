import assert from "node:assert/strict";
import { test } from "node:test";
import { JANELA_TRILHA_S, MAXIMO_RECENTES, MAXIMO_TRILHA, Recentes, Trilha, fixValido, type Fix } from "./trilha.ts";

const fix = (t_s: number, lat = -23.547, lon = -46.652, precisao_m = 6): Fix => ({ lat, lon, precisao_m, instante_ms: t_s * 1000 });

test("a trilha amostra a cada ~1,5 s: posições mais juntas que isso não entram", () => {
  const t = new Trilha();
  for (const s of [0, 0.5, 1, 1.4, 1.5, 2, 3]) t.adicionar(fix(s));
  assert.equal(t.tamanho(), 3); // 0, 1.5 e 3
});

test("trilha: só os últimos 15 s, no máximo 10 pontos, mais antigo primeiro", () => {
  const t = new Trilha();
  for (let s = 0; s <= 40; s += 1.5) t.adicionar(fix(s, -23.5 + s / 10000));
  assert.ok(t.tamanho() <= MAXIMO_TRILHA);
  const atual = fix(40);
  const lista = t.paraEnvio(atual);
  assert.ok(lista.length <= MAXIMO_TRILHA);
  assert.ok(lista.length > 0);
  for (const p of lista) assert.ok(p.ha_segundos > 0 && p.ha_segundos <= JANELA_TRILHA_S);
  const has = lista.map((p) => p.ha_segundos);
  assert.deepEqual(has, [...has].sort((a, b) => b - a), "mais antigo primeiro (ha_segundos decrescente)");
});

test("ha_segundos é calculado no envio, em relação à posição enviada, e nunca é 0 nem negativo", () => {
  const t = new Trilha();
  t.adicionar(fix(0));
  t.adicionar(fix(1.5));
  t.adicionar(fix(3));
  const lista = t.paraEnvio(fix(3));
  assert.deepEqual(lista.map((p) => p.ha_segundos), [3, 1.5]); // o ponto de ha 0 (a própria posição) não vai
  assert.deepEqual(t.paraEnvio(fix(4.5)).map((p) => p.ha_segundos), [4.5, 3, 1.5]);
  // posição "do passado" (relógio estranho): nada de ha negativo
  assert.deepEqual(t.paraEnvio(fix(-5)), []);
});

test("trilha vazia ou com um ponto só: lista vazia (a API fica sem direção, em silêncio)", () => {
  const t = new Trilha();
  assert.deepEqual(t.paraEnvio(fix(5)), []);
  t.adicionar(fix(5));
  assert.deepEqual(t.paraEnvio(fix(5)), []);
});

test("limpar apaga a trilha toda", () => {
  const t = new Trilha();
  t.adicionar(fix(0));
  t.adicionar(fix(2));
  t.limpar();
  assert.equal(t.tamanho(), 0);
  assert.deepEqual(t.paraEnvio(fix(3)), []);
});

test("posição inválida (NaN, fora da faixa, precisão negativa) não entra", () => {
  const t = new Trilha();
  t.adicionar({ lat: NaN, lon: 0, precisao_m: 5, instante_ms: 0 });
  t.adicionar({ lat: 91, lon: 0, precisao_m: 5, instante_ms: 0 });
  t.adicionar({ lat: 0, lon: 0, precisao_m: -1, instante_ms: 0 });
  assert.equal(t.tamanho(), 0);
  assert.equal(fixValido(null), false);
  assert.equal(fixValido(fix(0)), true);
});

test("recentes: guarda a chave com ha_segundos, repetir a chave só atualiza o instante", () => {
  const r = new Recentes();
  r.registrar("curva_0", 1000);
  r.registrar("perigo_escada_1", 4000);
  r.registrar("curva_0", 8000);
  assert.deepEqual(r.paraEnvio(10_000), [
    { chave: "perigo_escada_1", ha_segundos: 6 },
    { chave: "curva_0", ha_segundos: 2 },
  ]);
});

test("recentes: no máximo 20 (as mais novas) e some o que passou da retenção", () => {
  const r = new Recentes();
  for (let i = 0; i < 30; i++) r.registrar(`k${i}`, i * 1000);
  const lista = r.paraEnvio(30_000);
  assert.equal(lista.length, MAXIMO_RECENTES);
  assert.equal(lista[lista.length - 1]!.chave, "k29");
  assert.equal(lista[0]!.chave, "k10");
  assert.deepEqual(r.paraEnvio(30_000 + 200_000), []);
});

test("recentes: chave vazia ou com mais de 64 caracteres é ignorada; limpar apaga tudo", () => {
  const r = new Recentes();
  r.registrar("", 0);
  r.registrar("x".repeat(65), 0);
  assert.equal(r.tamanho(), 0);
  r.registrar("ok", 0);
  r.limpar();
  assert.equal(r.tamanho(), 0);
});
