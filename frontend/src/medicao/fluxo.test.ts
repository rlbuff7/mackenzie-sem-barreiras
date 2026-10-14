import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ANUNCIO_RECOMECOU,
  anuncioDaEtapa,
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
  proximoPonto,
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

test("segmentosProgresso: 12 segmentos, completo com 3 medições, um atual", () => {
  const rs = [ponto(1), ponto(1), ponto(1), ponto(2), ponto(2)];
  const seg = segmentosProgresso(rs, "Galaxy A54", 2);
  assert.equal(seg.length, 12);
  assert.deepEqual(seg.filter((s) => s.completo).map((s) => s.ponto), [1]);
  assert.deepEqual(seg.filter((s) => s.atual).map((s) => s.ponto), [2]);
  assert.equal(pontosCompletos(seg), 1);
  assert.deepEqual(seg.filter((s) => s.pulado).map((s) => s.ponto), [], "nenhum ponto antes do atual ficou incompleto");
  assert.equal(textoProgresso(seg), "1 de 12 pontos completos. Ponto atual: 2.");
});

test("segmentosProgresso marca como pulado o ponto incompleto antes do atual", () => {
  const seg = segmentosProgresso([ponto(1), ponto(1), ponto(1), ponto(2)], "Galaxy A54", 4);
  assert.deepEqual(seg.filter((s) => s.pulado).map((s) => s.ponto), [2, 3]);
  assert.ok(seg.filter((s) => s.completo || s.atual).every((s) => !s.pulado));
});

test("proximoPonto para no 12", () => {
  assert.equal(proximoPonto(3), 4);
  assert.equal(proximoPonto(12), null);
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
  assert.equal(anuncioDaEtapa("medir", 3, 2), "Ponto 3 de 12, medição 2 de 3.");
  assert.equal(anuncioDaEtapa("medir", 5, 4), "Ponto 5 de 12, medição extra (4).");
  assert.equal(anuncioDaEtapa("resultado", 3, 2), "Ponto 3 registrado, medição 2 de 3.");
  assert.match(anuncioDaEtapa("preparar", 1, 1), /aparelho/);
  for (const e of ETAPAS) {
    assert.ok(!anuncioDaEtapa(e.id, 1, 1).includes(e.titulo), `o anúncio de ${e.id} repete o título`);
  }
});

test("textoConfirmarRecomecar: diz o que se apaga, o que fica e que o servidor não é tocado", () => {
  const t = textoConfirmarRecomecar(7, 2);
  assert.match(t, /7 registros/);
  assert.match(t, /2 ainda não foram enviados e serão perdidos/);
  assert.match(t, /volta ao ponto 1/);
  assert.match(t, /continua lá/);
  assert.match(t, /nada é apagado no servidor/);
  assert.match(t, /aparelho, o código da equipe e a condição/);
});

test("textoConfirmarRecomecar: singular, tudo enviado e nada guardado", () => {
  const um = textoConfirmarRecomecar(1, 1);
  assert.match(um, /o 1 registro guardado/);
  assert.match(um, /1 ainda não foi enviado e será perdido/);
  const enviados = textoConfirmarRecomecar(4, 0);
  assert.doesNotMatch(enviados, /perdido/);
  assert.match(enviados, /Todos já foram enviados/);
  const vazio = textoConfirmarRecomecar(0, 0);
  assert.match(vazio, /Não há registros guardados/);
  assert.match(vazio, /nada é apagado no servidor/);
});

test("ANUNCIO_RECOMECOU confirma a volta ao ponto 1 e que o servidor não foi tocado", () => {
  assert.match(ANUNCIO_RECOMECOU, /ponto 1/);
  assert.match(ANUNCIO_RECOMECOU, /continua lá/);
});
