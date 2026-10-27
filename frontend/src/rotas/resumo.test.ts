import assert from "node:assert/strict";
import { test } from "node:test";
import { paraLatLng, pontoParaLatLng } from "./geometria.ts";
import { anuncioDaRota, montarFalas, textoDistancia, textoDistanciaTotal, tituloDoResultado } from "./resumo.ts";
import { lerRota } from "./interpretar.ts";
import { ROTA_200 } from "./fixtures.ts";

const rota = lerRota(ROTA_200)!;

test("GeoJSON [lon,lat] vira Leaflet [lat,lon], na mesma ordem", () => {
  assert.deepEqual(paraLatLng([[-46.6527, -23.5478], [-46.6525, -23.5477]]), [[-23.5478, -46.6527], [-23.5477, -46.6525]]);
  assert.deepEqual(paraLatLng([]), []);
  assert.deepEqual(pontoParaLatLng({ latitude: -23.5, longitude: -46.6 }), [-23.5, -46.6]);
});

test("distância: 'metros' por extenso, arredondada, singular e menos de 1", () => {
  assert.equal(textoDistancia(182.4), "182 metros");
  assert.equal(textoDistancia(182.6), "183 metros");
  assert.equal(textoDistancia(1), "1 metro");
  assert.equal(textoDistancia(0.3), "menos de 1 metro");
  assert.equal(textoDistancia(1250), "1250 metros");
  assert.equal(textoDistanciaTotal(182.4), "Distância total: 182 metros.");
});

test("nenhum texto de voz usa 'm' solto ou símbolo de unidade", () => {
  const falas = montarFalas(rota).join(" ");
  assert.ok(!/\d\s?m\b/.test(falas), "número seguido de 'm'");
  assert.ok(!/[°→↑↓]/.test(falas));
});

test("título e anúncio único da rota", () => {
  assert.equal(tituloDoResultado(rota), "Rota de Portão da rua Piauí até Entrada do Prédio 31");
  assert.equal(anuncioDaRota(rota), "Rota traçada: cerca de 182 metros, 1 aviso. As instruções vêm a seguir.");
});

test("falas: começam pelo aviso de segurança e terminam na chegada", () => {
  const falas = montarFalas(rota);
  assert.equal(falas[0], rota.aviso_seguranca);
  assert.match(falas[1]!, /^Demonstração do protótipo\./);
  assert.ok(falas.includes("O caminho tem escada (cerca de 10 metros)."));
  assert.match(falas.at(-1)!, /^Você chegou/);
  assert.equal(falas.length, 2 + 1 + 3);
});

test("rota provisória: a primeira fala avisa 'Trecho provisório de demonstração.' e ainda traz o aviso de segurança", () => {
  const prov = lerRota({ ...ROTA_200, provisorio: true })!;
  const primeira = montarFalas(prov)[0]!;
  assert.ok(primeira.startsWith("Trecho provisório de demonstração."));
  assert.ok(primeira.includes(prov.aviso_seguranca));
});
