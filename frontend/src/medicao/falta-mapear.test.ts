import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  estiloDaFeicao,
  filtrarPorTipo,
  htmlLetraPredio,
  tituloDoPredio,
  type ColecaoCamada,
} from "./falta-mapear.ts";

const dados = JSON.parse(readFileSync(new URL("./falta-mapear.json", import.meta.url), "utf8")) as ColecaoCamada;

test("o dado tem os 3 tipos", () => {
  assert.equal(filtrarPorTipo(dados, "falta_mapear").length, 1);
  assert.equal(filtrarPorTipo(dados, "limite_campus").length, 1);
  assert.equal(filtrarPorTipo(dados, "predio_sem_entrada").length, 18);
});

test("18 letras únicas de A a R", () => {
  const letras = filtrarPorTipo(dados, "predio_sem_entrada").map((f) => f.properties.letra);
  assert.equal(new Set(letras).size, 18);
  assert.deepEqual([...letras].sort().join(""), "ABCDEFGHIJKLMNOPQR");
});

test("estilos: nada interativo, lacuna sem borda, limite tracejado", () => {
  for (const t of ["falta_mapear", "limite_campus", "outro", undefined]) assert.equal(estiloDaFeicao(t).interactive, false);
  assert.equal(estiloDaFeicao("falta_mapear").stroke, false);
  assert.equal(estiloDaFeicao("falta_mapear").className, "mapa-lacuna-area");
  assert.ok(estiloDaFeicao("limite_campus").dashArray);
});

test("título e html da letra", () => {
  assert.equal(tituloDoPredio("C", undefined), "Prédio C: sem entrada mapeada");
  assert.match(tituloDoPredio("C", "Reitoria"), /\(Reitoria\)/);
  assert.match(htmlLetraPredio("C"), /aria-hidden="true">C</);
  assert.doesNotMatch(htmlLetraPredio("<b>"), /<b>/);
});
