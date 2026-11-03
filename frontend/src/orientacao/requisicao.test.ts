import assert from "node:assert/strict";
import { test } from "node:test";
import {
  IDADE_MAXIMA_FIX_MS,
  INTERVALO_ENVIO_MS,
  JanelaDeBussola,
  URL_ORIENTACOES,
  deveEnviar,
  gpsPerdido,
  lerEventoDeOrientacao,
  montarCorpo,
  montarRequisicao,
  type DadosDoPedido,
} from "./requisicao.ts";
import type { Fix } from "./trilha.ts";

const fix: Fix = { lat: -23.547012345, lon: -46.651712345, precisao_m: 8.04, instante_ms: 100_000 };
const base: DadosDoPedido = { origem_id: 4, destino_id: 6, perfil: "cegueira", fix, bussola: null, trilha: [], recentes: [] };

test("pedido mínimo: só origem, destino, perfil e posição (sem campos vazios)", () => {
  const corpo = montarCorpo(base)!;
  assert.deepEqual(Object.keys(corpo).sort(), ["destino_id", "origem_id", "perfil", "posicao"]);
  assert.deepEqual(corpo.posicao, { lat: -23.547012, lon: -46.651712, precisao_m: 8 });
});

test("a requisição vai por POST JSON para /api/orientacoes", () => {
  const r = montarRequisicao(base)!;
  assert.equal(r.url, URL_ORIENTACOES);
  assert.equal(URL_ORIENTACOES, "/api/orientacoes");
  assert.equal(r.init.method, "POST");
  assert.equal(r.init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(r.init.body).posicao.lat, -23.547012);
});

test("bússola só com rumo E oscilação; rumo é normalizado em 0..360", () => {
  const c = montarCorpo({ ...base, bussola: { rumo_graus: 312.04, oscilacao_graus: 6.06 } })!;
  assert.deepEqual(c.posicao, { lat: -23.547012, lon: -46.651712, precisao_m: 8, rumo_bussola_graus: 312, rumo_bussola_oscilacao_graus: 6.1 });
  const neg = montarCorpo({ ...base, bussola: { rumo_graus: -10, oscilacao_graus: 2 } })!;
  assert.equal((neg.posicao as Record<string, number>).rumo_bussola_graus, 350);
});

test("bússola ausente ou torta (NaN, -1 de oscilação) é OMITIDA: nunca -1, null nem NaN", () => {
  for (const b of [null, { rumo_graus: NaN, oscilacao_graus: 3 }, { rumo_graus: 10, oscilacao_graus: NaN }, { rumo_graus: 10, oscilacao_graus: -1 }, { rumo_graus: Infinity, oscilacao_graus: 1 }]) {
    const p = montarCorpo({ ...base, bussola: b as never })!.posicao as Record<string, unknown>;
    assert.ok(!("rumo_bussola_graus" in p) && !("rumo_bussola_oscilacao_graus" in p), JSON.stringify(b));
  }
});

test("nenhum número do pedido é -1, NaN ou null; chaves antigas não existem", () => {
  const texto = montarRequisicao({
    ...base,
    bussola: { rumo_graus: 90, oscilacao_graus: 3 },
    trilha: [{ lat: -23.5, lon: -46.6, precisao_m: 5, ha_segundos: 6 }],
    recentes: [{ chave: "curva_0", ha_segundos: 3 }],
  })!.init.body;
  assert.ok(!/null|NaN|-1\b/.test(texto.replace(/-23\.\d+|-46\.\d+/g, "")), texto);
  for (const removido of ['"rumo_graus"', '"rumo_oscilacao_graus"', "velocidade_ms"]) assert.ok(!texto.includes(removido), removido);
});

test("trilha e recentes só vão se houver; ponto de trilha torto é descartado", () => {
  const c = montarCorpo({
    ...base,
    trilha: [
      { lat: -23.5, lon: -46.6, precisao_m: 5, ha_segundos: 6 },
      { lat: NaN, lon: -46.6, precisao_m: 5, ha_segundos: 3 },
      { lat: -23.5, lon: -46.6, precisao_m: 5, ha_segundos: 0 },
    ],
    recentes: [{ chave: "curva_0", ha_segundos: 12.5 }, { chave: "", ha_segundos: 1 }],
  })!;
  assert.equal((c.trilha as unknown[]).length, 1);
  assert.deepEqual(c.recentes, [{ chave: "curva_0", ha_segundos: 12.5 }]);
  const sem = montarCorpo({ ...base, trilha: [], recentes: [] })!;
  assert.ok(!("trilha" in sem) && !("recentes" in sem));
});

test("posição inválida: nenhum pedido (silêncio)", () => {
  assert.equal(montarRequisicao({ ...base, fix: { ...fix, lat: NaN } }), null);
  assert.equal(montarRequisicao({ ...base, fix: { ...fix, precisao_m: -1 } }), null);
  assert.equal(montarRequisicao({ ...base, origem_id: 1.5 }), null);
});

test("deveEnviar: respeita o intervalo, nunca duas em voo, e só com posição recente", () => {
  const agora = 200_000;
  const f: Fix = { ...fix, instante_ms: agora - 500 };
  assert.equal(deveEnviar({ agora_ms: agora, ultimoEnvio_ms: null, emVoo: false, fix: f }), true);
  assert.equal(deveEnviar({ agora_ms: agora, ultimoEnvio_ms: agora - (INTERVALO_ENVIO_MS - 1), emVoo: false, fix: f }), false);
  assert.equal(deveEnviar({ agora_ms: agora, ultimoEnvio_ms: agora - INTERVALO_ENVIO_MS, emVoo: false, fix: f }), true);
  assert.equal(deveEnviar({ agora_ms: agora, ultimoEnvio_ms: null, emVoo: true, fix: f }), false);
  assert.equal(deveEnviar({ agora_ms: agora, ultimoEnvio_ms: null, emVoo: false, fix: null }), false);
  const velha: Fix = { ...fix, instante_ms: agora - IDADE_MAXIMA_FIX_MS - 1 };
  assert.equal(deveEnviar({ agora_ms: agora, ultimoEnvio_ms: null, emVoo: false, fix: velha }), false);
  assert.equal(gpsPerdido(velha, agora), true);
  assert.equal(gpsPerdido(f, agora), false);
  assert.equal(gpsPerdido(null, agora), true);
});

test("bússola: iPhone usa webkitCompassHeading; Android só alpha ABSOLUTO (rumo = 360 - alpha); alpha relativo é descartado", () => {
  assert.deepEqual(lerEventoDeOrientacao({ webkitCompassHeading: 45 }), { rumo_graus: 45, fonte: "webkitCompassHeading" });
  assert.deepEqual(lerEventoDeOrientacao({ alpha: 90, absolute: true }), { rumo_graus: 270, fonte: "alpha_absoluto" });
  assert.deepEqual(lerEventoDeOrientacao({ alpha: 0, absolute: true }), { rumo_graus: 0, fonte: "alpha_absoluto" });
  assert.equal(lerEventoDeOrientacao({ alpha: 90, absolute: false }), null, "relativo não aponta para o norte");
  assert.equal(lerEventoDeOrientacao({ alpha: 90 }), null);
  assert.equal(lerEventoDeOrientacao({ alpha: null, webkitCompassHeading: null }), null);
  assert.equal(lerEventoDeOrientacao({ webkitCompassHeading: NaN }), null);
});

test("oscilação: janela de ~2 s, circular (350° e 10° oscilam 20°, não 340°)", () => {
  const j = new JanelaDeBussola();
  j.adicionar(350, 0);
  j.adicionar(10, 500);
  j.adicionar(0, 1000);
  const r = j.resumo(1000)!;
  assert.equal(r.oscilacao_graus, 20);
  assert.ok(r.rumo_graus < 5 || r.rumo_graus > 355, `média circular perto do norte: ${r.rumo_graus}`);
});

test("oscilação: leituras fora da janela saem; poucas leituras = sem bússola (null), não oscilação 0", () => {
  const j = new JanelaDeBussola();
  j.adicionar(100, 0);
  j.adicionar(100, 100);
  assert.equal(j.resumo(100), null, "2 leituras não bastam");
  j.adicionar(100, 200);
  assert.deepEqual(j.resumo(200), { rumo_graus: 100, oscilacao_graus: 0 });
  assert.equal(j.resumo(5000), null, "tudo velho");
  j.limpar();
  assert.equal(j.resumo(200), null);
});

test("bússola instável mede oscilação grande (a API decide o silêncio)", () => {
  const j = new JanelaDeBussola();
  [0, 40, 80, 20].forEach((g, i) => j.adicionar(g, i * 400));
  assert.ok(j.resumo(1200)!.oscilacao_graus >= 60);
});
