import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CABECALHO_CSV,
  contarPontoRegistrado,
  escaparCampoCsv,
  gerarCsv,
  horarioLocal,
  montarRegistroBussola,
  montarRegistroPosicao,
  montarRegistroVibracao,
  nomeArquivoCsv,
  oscilacaoBussola,
  podeGravarTrajeto,
  type Registro,
} from "./medicao.ts";

const agora = new Date(2026, 9, 22, 14, 5, 9); // horário local
const posicao = {
  latitude: -23.5475,
  longitude: -46.6523,
  accuracy: 8.5,
  altitude: null,
  altitudeAccuracy: null,
  speed: null,
  heading: null,
};

test("horarioLocal formata data e hora locais com zeros à esquerda", () => {
  assert.equal(horarioLocal(agora), "2026-10-22 14:05:09");
});

test("montarRegistroPosicao grava os campos e deixa vazio o que o aparelho não deu", () => {
  const r = montarRegistroPosicao({
    tipo: "ponto",
    posicao,
    ponto: 3,
    aparelho: "Galaxy A54",
    condicao: "entre_predios",
    observacao: "perto do bloco 9",
    userAgent: "UA-teste",
    agora,
  });
  assert.equal(r.tipo, "ponto");
  assert.equal(r.horario_iso, agora.toISOString());
  assert.equal(r.horario_local, "2026-10-22 14:05:09");
  assert.equal(r.ponto, 3);
  assert.equal(r.aparelho, "Galaxy A54");
  assert.equal(r.condicao, "entre_predios");
  assert.equal(r.latitude, -23.5475);
  assert.equal(r.precisao_m, 8.5);
  assert.equal(r.altitude_m, null);
  assert.equal(r.velocidade_ms, null);
  assert.equal(r.rumo_graus, null);
  assert.equal(r.user_agent, "UA-teste");
});

test("montarRegistroPosicao do trajeto não leva número de ponto", () => {
  const r = montarRegistroPosicao({
    tipo: "trajeto",
    posicao: { ...posicao, speed: 1.2, heading: 90, altitude: 760, altitudeAccuracy: 10 },
    ponto: null,
    aparelho: "iPhone 13",
    condicao: "ceu_aberto",
    observacao: "",
    userAgent: "UA",
    agora,
  });
  assert.equal(r.ponto, null);
  assert.equal(r.velocidade_ms, 1.2);
  assert.equal(r.rumo_graus, 90);
  assert.equal(r.altitude_m, 760);
  assert.equal(r.precisao_altitude_m, 10);
});

test("contarPontoRegistrado conta só medições de ponto daquele número", () => {
  const base = { aparelho: "A" } as Partial<Registro>;
  const regs = [
    { ...base, tipo: "ponto", ponto: 1 },
    { ...base, tipo: "ponto", ponto: 1 },
    { ...base, tipo: "ponto", ponto: 2 },
    { ...base, tipo: "trajeto", ponto: null },
    { ...base, tipo: "bussola", ponto: 1 },
  ] as Registro[];
  assert.equal(contarPontoRegistrado(regs, 1), 2);
  assert.equal(contarPontoRegistrado(regs, 2), 1);
  assert.equal(contarPontoRegistrado(regs, 3), 0);
});

test("contarPontoRegistrado separa por aparelho quando informado", () => {
  const regs = [
    { tipo: "ponto", ponto: 1, aparelho: "A" },
    { tipo: "ponto", ponto: 1, aparelho: "B" },
  ] as Registro[];
  assert.equal(contarPontoRegistrado(regs, 1, "A"), 1);
  assert.equal(contarPontoRegistrado(regs, 1), 2);
});

test("podeGravarTrajeto: primeira posição passa e depois só com 1 s de intervalo", () => {
  assert.equal(podeGravarTrajeto(null, 5000), true);
  assert.equal(podeGravarTrajeto(5000, 5400), false);
  assert.equal(podeGravarTrajeto(5000, 5999), false);
  assert.equal(podeGravarTrajeto(5000, 6000), true);
  assert.equal(podeGravarTrajeto(5000, 4000), false); // relógio voltou: não grava
});

test("oscilacaoBussola: leituras estáveis dão oscilação zero", () => {
  const o = oscilacaoBussola(
    [
      { instante_ms: 9000, rumo_graus: 100 },
      { instante_ms: 9500, rumo_graus: 100 },
    ],
    10000,
  );
  assert.deepEqual(o, { minimo_graus: 100, maximo_graus: 100, oscilacao_graus: 0, amostras: 2 });
});

test("oscilacaoBussola: só usa os últimos 3 s", () => {
  const o = oscilacaoBussola(
    [
      { instante_ms: 1000, rumo_graus: 10 }, // fora da janela
      { instante_ms: 8000, rumo_graus: 100 },
      { instante_ms: 9000, rumo_graus: 110 },
    ],
    10000,
  );
  assert.ok(o);
  assert.equal(o.minimo_graus, 100);
  assert.equal(o.maximo_graus, 110);
  assert.equal(o.oscilacao_graus, 10);
  assert.equal(o.amostras, 2);
});

test("oscilacaoBussola: volta de 359 para 0 não vira oscilação de 359", () => {
  const o = oscilacaoBussola(
    [
      { instante_ms: 9000, rumo_graus: 358 },
      { instante_ms: 9300, rumo_graus: 1 },
      { instante_ms: 9600, rumo_graus: 4 },
    ],
    10000,
  );
  assert.ok(o);
  assert.equal(o.oscilacao_graus, 6);
  assert.equal(o.minimo_graus, 358);
  assert.equal(o.maximo_graus, 4);
});

test("oscilacaoBussola: sem amostras na janela devolve null", () => {
  assert.equal(oscilacaoBussola([], 10000), null);
  assert.equal(oscilacaoBussola([{ instante_ms: 1, rumo_graus: 5 }], 10000), null);
});

test("montarRegistroBussola e montarRegistroVibracao", () => {
  const b = montarRegistroBussola({
    rumo_graus: 359.5,
    fonte: "webkitCompassHeading",
    oscilacao: { minimo_graus: 358, maximo_graus: 2, oscilacao_graus: 4, amostras: 5 },
    aparelho: "iPhone 13",
    userAgent: "UA",
    agora,
  });
  assert.equal(b.tipo, "bussola");
  assert.equal(b.bussola_rumo_graus, 359.5);
  assert.equal(b.bussola_oscilacao_graus, 4);
  assert.equal(b.bussola_fonte, "webkitCompassHeading");
  const v = montarRegistroVibracao({ existe: false, retorno: null, aparelho: "iPhone 13", userAgent: "UA", agora });
  assert.equal(v.tipo, "vibracao");
  assert.equal(v.vibracao_existe, false);
  assert.equal(v.vibracao_retorno, null);
});

test("escaparCampoCsv: aspas, vírgulas e quebras de linha", () => {
  assert.equal(escaparCampoCsv("simples"), "simples");
  assert.equal(escaparCampoCsv("a,b"), '"a,b"');
  assert.equal(escaparCampoCsv('diz "oi"'), '"diz ""oi"""');
  assert.equal(escaparCampoCsv("linha1\nlinha2"), '"linha1\nlinha2"');
  assert.equal(escaparCampoCsv("linha1\r\nlinha2"), '"linha1\r\nlinha2"');
  assert.equal(escaparCampoCsv(null), "");
  assert.equal(escaparCampoCsv(-23.5475), "-23.5475");
  assert.equal(escaparCampoCsv(true), "true");
  assert.equal(escaparCampoCsv(false), "false");
});

test("gerarCsv: cabeçalho fixo, uma linha por registro, ponto decimal", () => {
  const r = montarRegistroPosicao({
    tipo: "ponto",
    posicao,
    ponto: 3,
    aparelho: "Galaxy, A54",
    condicao: "coberto",
    observacao: 'disse "ok"\nsegunda linha',
    userAgent: "UA",
    agora,
  });
  const csv = gerarCsv([r]);
  const [cabecalho] = csv.split("\n");
  assert.equal(cabecalho, CABECALHO_CSV.join(","));
  assert.ok(csv.includes('"Galaxy, A54"'));
  assert.ok(csv.includes('"disse ""ok""\nsegunda linha"'));
  assert.ok(csv.includes(",-23.5475,-46.6523,8.5,"));
  assert.equal(gerarCsv([]), CABECALHO_CSV.join(",") + "\n");
});

test("gerarCsv: toda linha tem o mesmo número de colunas do cabeçalho", () => {
  const r = montarRegistroVibracao({ existe: true, retorno: true, aparelho: "A", userAgent: "UA", agora });
  const linha = gerarCsv([r]).trimEnd().split("\n")[1] ?? "";
  assert.equal(linha.split(",").length, CABECALHO_CSV.length);
});

test("nomeArquivoCsv limpa o aparelho e leva a data", () => {
  assert.equal(nomeArquivoCsv("Galaxy A54", agora), "medicao-gps-galaxy-a54-2026-10-22.csv");
  assert.equal(nomeArquivoCsv("  iPhone/13 ?? ", agora), "medicao-gps-iphone-13-2026-10-22.csv");
  assert.equal(nomeArquivoCsv("", agora), "medicao-gps-sem-aparelho-2026-10-22.csv");
});
