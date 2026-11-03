import assert from "node:assert/strict";
import { test } from "node:test";
import {
  AVISO_PROVISORIO,
  AVISO_SEGURANCA,
  LIMITE_MAPA_CAMPUS,
  RESULTADO_SEM_REDE,
  ROTULOS,
  TEXTO_GPS_NEGADO,
  TEXTO_SEM_CONEXAO,
  TITULO_AO_VIVO,
  VIBRACAO_ALTA,
  apresentacaoSemGps,
  dentroDoCampus,
  interpretarResposta,
  lerResposta,
  resultadoDoErroDeGps,
  telaAoParar,
  textoDeDistanciaRestante,
  vibracaoDaMensagem,
  TELA_AO_VIVO,
} from "./apresentacao.ts";
import { VIBRACAO_CHEGADA } from "../rotas/simulacao.ts";
import { tituloDaPagina } from "../a11y/orientacao.ts";

const ok = (estado: string, mensagem: unknown = null, extra: Record<string, unknown> = {}) => ({
  estado, confianca: "alta", mensagem, distancia_restante_m: 112.4, progresso_m: 70.1, direcao: null, fonte_rumo: null, ...extra,
});
const msg = (chave: string, texto: string, prioridade: string) => ({ chave, texto, prioridade });

test("os quatro estados têm rótulo e símbolo próprios (nunca só cor)", () => {
  assert.deepEqual(Object.keys(ROTULOS).sort(), ["chegou", "fora_da_rota", "na_rota", "precisao_insuficiente"]);
  assert.deepEqual(Object.values(ROTULOS).map((r) => r.rotulo), ["Na rota", "Você saiu da rota", "Sem GPS confiável", "Você chegou"]);
  const simbolos = Object.values(ROTULOS).map((r) => r.simbolo);
  assert.equal(new Set(simbolos).size, 4, "uma forma diferente por estado");
});

test("na rota: rótulo, distância e a mensagem da API, sem texto inventado", () => {
  const a = lerResposta(ok("na_rota", msg("curva_0", "Em 10 metros, vire à direita.", "media")))!;
  assert.equal(a.rotulo, "Na rota");
  assert.equal(a.distanciaTexto, "Faltam cerca de 112 metros");
  assert.equal(a.mensagem?.texto, "Em 10 metros, vire à direita.");
  assert.equal(a.textoParaDizer, "Em 10 metros, vire à direita.");
  assert.equal(a.urgente, false);
});

test("SILÊNCIO: mensagem null = nada a dizer, nada a vibrar, mesmo com direção na resposta", () => {
  const a = lerResposta(ok("na_rota", null, { direcao: "direita", fonte_rumo: "movimento" }))!;
  assert.equal(a.mensagem, null);
  assert.equal(a.textoParaDizer, "");
  assert.deepEqual(a.vibrar, []);
  assert.equal(a.urgente, false);
});

test("o campo `direcao` sozinho nunca vira frase no cliente (só a mensagem da API fala)", () => {
  for (const d of ["frente", "direita", "esquerda", "atras"]) {
    const a = lerResposta(ok("na_rota", null, { direcao: d }))!;
    assert.equal(a.textoParaDizer, "");
    assert.equal(a.mensagem, null);
  }
});

test("prioridade alta e perigo: urgente (assertive) e vibra [300,100,300]", () => {
  for (const p of ["alta", "perigo"]) {
    const a = lerResposta(ok("fora_da_rota", msg("fora_da_rota", "Você saiu da rota. Pare e aguarde.", p), { distancia_restante_m: null }))!;
    assert.equal(a.urgente, true, p);
    assert.deepEqual(a.vibrar, [300, 100, 300]);
    assert.deepEqual(VIBRACAO_ALTA, [300, 100, 300]);
  }
});

test("media e baixa: polite, não urgente", () => {
  for (const p of ["media", "baixa"]) assert.equal(lerResposta(ok("na_rota", msg("direcao_frente", "O caminho está à sua frente.", p)))!.urgente, false);
});

test("vibração de curva segue os padrões da simulação, lida do texto da API", () => {
  assert.deepEqual(vibracaoDaMensagem(msg("curva_0", "Em 10 metros, vire à direita.", "media") as never), [80, 80, 80]);
  assert.deepEqual(vibracaoDaMensagem(msg("curva_1", "Em 5 metros, vire à esquerda.", "media") as never), [300]);
  assert.deepEqual(vibracaoDaMensagem(msg("curva_2", "Em 8 metros, vire levemente à direita.", "media") as never), [80]);
  assert.deepEqual(vibracaoDaMensagem(msg("curva_3", "Em 8 metros, faça o retorno.", "media") as never), [300, 100, 300]);
  assert.deepEqual(vibracaoDaMensagem(msg("curva_4", "Frase que não se entende", "media") as never), [], "sem padrão: não vibra");
});

test("vibração de direção por setor; 'frente' (confirmação) não vibra", () => {
  assert.deepEqual(vibracaoDaMensagem(msg("direcao_direita", "O caminho está à sua direita.", "media") as never), [80, 80, 80]);
  assert.deepEqual(vibracaoDaMensagem(msg("direcao_esquerda", "O caminho está à sua esquerda.", "media") as never), [300]);
  assert.deepEqual(vibracaoDaMensagem(msg("direcao_atras", "O caminho está atrás de você.", "media") as never), [300, 100, 300]);
  assert.deepEqual(vibracaoDaMensagem(msg("direcao_frente", "O caminho está à sua frente.", "baixa") as never), []);
  assert.deepEqual(vibracaoDaMensagem(msg("chegada", "Você chegou à entrada do Prédio 29.", "media") as never), []);
});

test("chegou: vibra [200,100,200], para sozinho (chegou=true), diz a frase da API e 'Orientação encerrada'", () => {
  const a = lerResposta(ok("chegou", msg("chegada", "Você chegou à entrada do Prédio 29.", "media"), { distancia_restante_m: 3 }))!;
  assert.equal(a.chegou, true);
  assert.deepEqual(a.vibrar, VIBRACAO_CHEGADA);
  assert.deepEqual(VIBRACAO_CHEGADA, [200, 100, 200]);
  assert.equal(a.textoParaDizer, "Você chegou à entrada do Prédio 29. Orientação encerrada.");
  assert.equal(a.distanciaTexto, null, "'Faltam 3 metros' contradiria 'Você chegou'");
  const sem = lerResposta(ok("chegou", null))!;
  assert.equal(sem.textoParaDizer, "Você chegou. Orientação encerrada.");
});

test("sem GPS confiável e fora da rota: sem distância quando a API manda null", () => {
  const a = lerResposta(ok("precisao_insuficiente", msg("sem_posicao", "Não sei onde você está agora. Fique parado por alguns segundos.", "alta"), { distancia_restante_m: null, progresso_m: null }))!;
  assert.equal(a.rotulo, "Sem GPS confiável");
  assert.equal(a.distanciaTexto, null);
  assert.equal(a.urgente, true);
  assert.equal(apresentacaoSemGps().textoParaDizer, "");
  assert.deepEqual(apresentacaoSemGps().vibrar, []);
});

test("distância: arredonda, singular, menos de 1 metro, e ignora o que não é número", () => {
  assert.equal(textoDeDistanciaRestante(112.4), "Faltam cerca de 112 metros");
  assert.equal(textoDeDistanciaRestante(112.6), "Faltam cerca de 113 metros");
  assert.equal(textoDeDistanciaRestante(1.2), "Falta cerca de 1 metro");
  assert.equal(textoDeDistanciaRestante(0.3), "Falta menos de 1 metro");
  for (const v of [null, undefined, NaN, Infinity, -5, "12", {}]) assert.equal(textoDeDistanciaRestante(v), null);
});

test("resposta torta vira 'pausada' (sem fala, sem vibração, nunca palpite)", () => {
  for (const corpo of [null, [], "x", {}, ok("voando"), { ...ok("na_rota"), mensagem: undefined }, ok("na_rota", { chave: "", texto: "x", prioridade: "alta" }), ok("na_rota", msg("a", "", "alta")), ok("na_rota", msg("a", "b", "urgentissima")), ok("na_rota", "texto solto")]) {
    const r = interpretarResposta(200, corpo);
    assert.equal(r.tipo, "erro", JSON.stringify(corpo));
    if (r.tipo === "erro") assert.equal(r.parar, false);
  }
  assert.equal(lerResposta(ok("na_rota", msg("a", "b", "alta")))!.mensagem?.texto, "b");
});

test("erros HTTP: 404 sem_rota usa a mensagem da API e para; outro 404, 422 e 413 param", () => {
  const sem = interpretarResposta(404, { codigo: "sem_rota", mensagem: "Não há caminho entre esses pontos." });
  assert.deepEqual(sem, { tipo: "erro", motivo: "sem_rota", mensagem: "Não há caminho entre esses pontos.", parar: true });
  const semMsg = interpretarResposta(404, { codigo: "sem_rota" });
  assert.equal(semMsg.tipo === "erro" && semMsg.parar, true);
  assert.equal(semMsg.tipo === "erro" && semMsg.mensagem.length > 0, true);
  for (const s of [404, 422, 413, 400]) {
    const r = interpretarResposta(s, null);
    assert.equal(r.tipo === "erro" && r.parar, true, String(s));
  }
});

test("5xx e rede: 'Sem conexão: orientação pausada', sem parar (tenta de novo no próximo ciclo)", () => {
  for (const s of [500, 502, 503, 504, 408, 429]) {
    const r = interpretarResposta(s, null);
    assert.deepEqual(r, { tipo: "erro", motivo: "servidor", mensagem: "Sem conexão: orientação pausada", parar: false }, String(s));
  }
  assert.equal(TEXTO_SEM_CONEXAO, "Sem conexão: orientação pausada");
  assert.equal(RESULTADO_SEM_REDE.tipo === "erro" && RESULTADO_SEM_REDE.parar, false);
});

test("GPS: negado explica como liberar e para; indisponível e tempo esgotado só esperam", () => {
  const negado = resultadoDoErroDeGps(1);
  assert.equal(negado.parar, true);
  assert.equal(negado.mensagem, TEXTO_GPS_NEGADO);
  assert.match(TEXTO_GPS_NEGADO, /Localização/);
  assert.ok(TEXTO_GPS_NEGADO.length < 400, "texto curto");
  for (const c of [2, 3]) assert.equal(resultadoDoErroDeGps(c).parar, false);
});

test("títulos e anúncios de tela", () => {
  assert.equal(TITULO_AO_VIVO, "Orientação ao vivo · Navegação Acessível no Campus");
  assert.equal(tituloDaPagina(TELA_AO_VIVO.nome), TITULO_AO_VIVO);
  const t = telaAoParar({ avisos: [], distancia_m: 182 });
  assert.equal(tituloDaPagina(t.nome), "Rota traçada · Navegação Acessível no Campus");
  assert.match(t.acao, /^Orientação encerrada\./);
});

test("avisos permanentes têm o texto combinado", () => {
  assert.equal(AVISO_SEGURANCA, "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade.");
  assert.equal(AVISO_PROVISORIO, "Direções provisórias, calculadas pelo mapa aberto.");
});

test("mapa: só acompanha a pessoa dentro do campus (fora, os blocos do mapa não revelam onde ela está)", () => {
  assert.equal(dentroDoCampus(-23.5475, -46.6522), true);
  assert.equal(dentroDoCampus(-23.5, -46.6522), false);
  assert.equal(dentroDoCampus(-23.5475, -46.7), false);
  assert.equal(dentroDoCampus(NaN, -46.65), false);
  assert.equal(LIMITE_MAPA_CAMPUS.length, 4);
});
