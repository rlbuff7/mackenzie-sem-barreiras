import assert from "node:assert/strict";
import { test } from "node:test";
import {
  anuncioDaEtapa,
  anuncioRecomecou,
  classificarPrecisao,
  descreverEnvio,
  ETAPAS,
  etapaInicial,
  numeroDaEtapa,
  textoConfirmarRecomecar,
  textoEtapa,
  TOTAL_ETAPAS,
  tituloEtapa,
  formatarMetros,
  fracaoContagem,
  numeroDaProximaMedicao,
  pontosCompletos,
  medicoesFeitas,
  proximoPonto,
  registrosDaRodada,
  segmentosProgresso,
  segundosRestantes,
  textoMedicao,
  textoPrecisao,
  textoProgresso,
} from "./fluxo.ts";
import { montarRegistroPosicao, type Registro } from "./medicao.ts";

function ponto(n: number, aparelho = "Galaxy A54"): Registro {
  return montarRegistroPosicao({
    tipo: "ponto",
    posicao: { latitude: -23.5, longitude: -46.6, accuracy: 6, altitude: null, altitudeAccuracy: null, speed: null, heading: null },
    ponto: n,
    aparelho,
    condicao: "ceu_aberto",
    observacao: "",
    userAgent: "teste",
    agora: new Date(2026, 9, 22, 10, 0, 0),
  });
}

test("classificarPrecisao: até 10 m boa, até 20 m média, acima ruim", () => {
  assert.equal(classificarPrecisao(0), "boa");
  assert.equal(classificarPrecisao(10), "boa");
  assert.equal(classificarPrecisao(10.1), "media");
  assert.equal(classificarPrecisao(20), "media");
  assert.equal(classificarPrecisao(20.1), "ruim");
});

test("classificarPrecisao: sem número ou inválido não chuta nível", () => {
  assert.equal(classificarPrecisao(null), null);
  assert.equal(classificarPrecisao(Number.NaN), null);
  assert.equal(classificarPrecisao(-1), null);
});

test("textoPrecisao usa palavra e forma, não só cor", () => {
  assert.equal(textoPrecisao(6), "● boa");
  assert.equal(textoPrecisao(15), "▲ média");
  assert.equal(textoPrecisao(40), "■ ruim");
  assert.match(textoPrecisao(null), /Aguardando/);
});

test("formatarMetros arredonda e mostra traço sem posição", () => {
  assert.equal(formatarMetros(6.4), "6 m");
  assert.equal(formatarMetros(null), "– m");
});

test("numeroDaProximaMedicao conta só o ponto e o aparelho certos", () => {
  const rs = [ponto(3), ponto(3), ponto(2), ponto(3, "iPhone")];
  assert.equal(numeroDaProximaMedicao(rs, 3, "Galaxy A54"), 3);
  assert.equal(numeroDaProximaMedicao(rs, 1, "Galaxy A54"), 1);
});

test("textoMedicao: de 1 a 3 'N de 3'; depois, medição extra", () => {
  assert.equal(textoMedicao(2), "medição 2 de 3");
  assert.equal(textoMedicao(4), "medição extra (4)");
});

test("segmentosProgresso: 10 segmentos, completo com 3 medições, um atual", () => {
  const rs = [ponto(1), ponto(1), ponto(1), ponto(2), ponto(2)];
  const seg = segmentosProgresso(rs, "Galaxy A54", 2);
  assert.equal(seg.length, 10);
  assert.deepEqual(seg.filter((s) => s.completo).map((s) => s.ponto), [1]);
  assert.deepEqual(seg.filter((s) => s.atual).map((s) => s.ponto), [2]);
  assert.equal(pontosCompletos(seg), 1);
  assert.deepEqual(seg.filter((s) => s.pulado).map((s) => s.ponto), [], "nenhum ponto antes do atual ficou incompleto");
  assert.equal(textoProgresso(seg), "1 de 10 pontos completos. Ponto atual: 2.");
});

test("segmentosProgresso marca como pulado o ponto incompleto antes do atual", () => {
  const seg = segmentosProgresso([ponto(1), ponto(1), ponto(1), ponto(2)], "Galaxy A54", 4);
  assert.deepEqual(seg.filter((s) => s.pulado).map((s) => s.ponto), [2, 3]);
  assert.ok(seg.filter((s) => s.completo || s.atual).every((s) => !s.pulado));
});

test("proximoPonto para no 10", () => {
  assert.equal(proximoPonto(3), 4);
  assert.equal(proximoPonto(10), null);
});

test("segundosRestantes arredonda para cima, não fica negativo e ignora relógio que voltou", () => {
  assert.equal(segundosRestantes(1000, 1000), 30);
  assert.equal(segundosRestantes(1000, 1500), 30);
  assert.equal(segundosRestantes(1000, 1000 + 12_000), 18);
  assert.equal(segundosRestantes(1000, 1000 + 30_000), 0);
  assert.equal(segundosRestantes(1000, 1000 + 99_000), 0);
  assert.equal(segundosRestantes(5000, 1000), 30);
});

test("fracaoContagem vai de 0 a 1", () => {
  assert.equal(fracaoContagem(30), 0);
  assert.equal(fracaoContagem(15), 0.5);
  assert.equal(fracaoContagem(0), 1);
});

const base = { motivo: null, temCodigo: true, online: true };

test("descreverEnvio: enviado, recusado com motivo e na fila, cada um com ícone e palavra", () => {
  assert.deepEqual(descreverEnvio({ ...base, estado: "enviado" }), {
    cartao: "enviado", icone: "✓", titulo: "Enviado para a equipe", curto: "✓ enviado",
  });
  const r = descreverEnvio({ ...base, estado: "recusado", motivo: "código da equipe errado" });
  assert.equal(r.titulo, "Recusado: código da equipe errado");
  assert.equal(r.curto, "✕ recusado: código da equipe errado");
  assert.equal(r.icone, "✕");
});

test("descreverEnvio: na fila sem sinal, offline, servidor desligado e falta de código", () => {
  assert.equal(descreverEnvio({ ...base, estado: "na_fila", motivo: "sem sinal" }).titulo, "Na fila, sem sinal");
  assert.equal(descreverEnvio({ ...base, estado: "na_fila", online: false }).titulo, "Na fila, sem sinal");
  assert.equal(
    descreverEnvio({ ...base, estado: "na_fila", motivo: "medição desligada no servidor" }).titulo,
    "Na fila: medição desligada no servidor",
  );
  assert.equal(descreverEnvio({ ...base, estado: "na_fila" }).titulo, "Na fila, enviando");
  assert.equal(
    descreverEnvio({ ...base, estado: "na_fila", temCodigo: false }).titulo,
    "Não enviado: falta o código da equipe",
  );
});

// ---------- etapas: uma por tela ----------

test("são 3 etapas, nesta ordem: preparar, medir o ponto, resultado do ponto", () => {
  assert.equal(TOTAL_ETAPAS, 3);
  assert.deepEqual(
    ETAPAS.map((e) => e.id),
    ["preparar", "medir", "resultado"],
  );
  assert.equal(tituloEtapa("preparar"), "Preparar");
  assert.equal(tituloEtapa("medir"), "Medir o ponto");
  assert.equal(tituloEtapa("resultado"), "Resultado do ponto");
});

test("textoEtapa diz 'Etapa X de Y' e numeroDaEtapa conta de 1", () => {
  assert.equal(numeroDaEtapa("preparar"), 1);
  assert.equal(numeroDaEtapa("resultado"), 3);
  assert.equal(textoEtapa("preparar"), "Etapa 1 de 3");
  assert.equal(textoEtapa("medir"), "Etapa 2 de 3");
  assert.equal(textoEtapa("resultado"), "Etapa 3 de 3");
});

test("etapaInicial: sem aparelho ou sem código começa em Preparar; com os dois, volta direto a Medir", () => {
  assert.equal(etapaInicial({ temAparelho: false, temCodigo: false }), "preparar");
  assert.equal(etapaInicial({ temAparelho: true, temCodigo: false }), "preparar");
  assert.equal(etapaInicial({ temAparelho: false, temCodigo: true }), "preparar");
  assert.equal(etapaInicial({ temAparelho: true, temCodigo: true }), "medir");
});

test("anuncioDaEtapa: uma frase por etapa, sem repetir o título (o foco já lê o título)", () => {
  assert.equal(anuncioDaEtapa("medir", 3, 2), "Ponto 3 de 10, medição 2 de 3.");
  assert.equal(anuncioDaEtapa("medir", 5, 4), "Ponto 5 de 10, medição extra (4).");
  assert.equal(anuncioDaEtapa("resultado", 3, 2), "Ponto 3 registrado, medição 2 de 3.");
  assert.match(anuncioDaEtapa("preparar", 1, 1), /aparelho/);
  for (const e of ETAPAS) {
    assert.ok(!anuncioDaEtapa(e.id, 1, 1).includes(e.titulo), `o anúncio de ${e.id} repete o título`);
  }
});

test("textoConfirmarRecomecar com pendentes: diz quantos esperam internet, que CONTINUAM e saem sozinhos", () => {
  const t = textoConfirmarRecomecar(3);
  assert.match(t, /volta ao ponto 1/);
  assert.match(t, /3 registros ainda esperam internet e CONTINUAM neste aparelho/);
  assert.match(t, /serão enviados sozinhos quando houver sinal/);
  assert.match(t, /continua lá/);
  assert.match(t, /nada é apagado no servidor/);
  assert.match(t, /aparelho, o código da equipe e a condição/);
  assert.doesNotMatch(t, /apaga os|serão perdidos|perdido/);
});

test("textoConfirmarRecomecar no singular", () => {
  const t = textoConfirmarRecomecar(1);
  assert.match(t, /1 registro ainda espera internet e CONTINUA neste aparelho/);
  assert.match(t, /será enviado sozinho quando houver sinal/);
});

test("textoConfirmarRecomecar sem pendentes: não menciona fila nem internet", () => {
  const t = textoConfirmarRecomecar(0);
  assert.doesNotMatch(t, /fila|internet|sinal|CONTINUA/);
  assert.match(t, /volta ao ponto 1/);
  assert.match(t, /nada é apagado no servidor/);
});

test("anuncioRecomecou: com pendentes diz que seguem e saem sozinhos; sem pendentes não fala de fila", () => {
  assert.match(anuncioRecomecou(2), /2 registros ainda esperam internet e serão enviados sozinhos/);
  assert.match(anuncioRecomecou(1), /1 registro ainda espera internet e será enviado sozinho/);
  for (const n of [0, 1, 2]) {
    assert.match(anuncioRecomecou(n), /ponto 1/);
    assert.match(anuncioRecomecou(n), /continua lá/);
  }
  assert.doesNotMatch(anuncioRecomecou(0), /fila|internet/);
});

test("registrosDaRodada: sem marca valem todos; com marca valem só os feitos depois do recomeço", () => {
  const antigo = ponto(1);
  const novo = ponto(1);
  antigo.horario_iso = "2026-10-22T10:00:00.000Z";
  novo.horario_iso = "2026-10-22T11:00:00.000Z";
  assert.equal(registrosDaRodada([antigo, novo], null).length, 2);
  assert.deepEqual(registrosDaRodada([antigo, novo], "2026-10-22T10:30:00.000Z"), [novo]);
  // o que esperava envio de antes do recomeço não conta no ponto 1 da rodada nova
  assert.equal(medicoesFeitas(registrosDaRodada([antigo], "2026-10-22T10:30:00.000Z"), 1, "Galaxy A54"), 0);
});
