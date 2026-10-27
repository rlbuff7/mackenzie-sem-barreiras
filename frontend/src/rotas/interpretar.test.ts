import assert from "node:assert/strict";
import { test } from "node:test";
import {
  BBOX_CAMPUS,
  MENSAGEM_REDE,
  MENSAGEM_SEM_ROTA,
  interpretarRespostaDePontos,
  interpretarRespostaDeRota,
  montarRequisicaoDeRota,
  pontosDeDestino,
  pontosDePartida,
  problemaNaEscolha,
  rotaTemEscada,
  urlDosPontos,
} from "./interpretar.ts";
import { buscarPontos, tracarRota } from "./api.ts";
import { PONTOS_200, ROTA_200, ROTA_CADEIRANTE_200, ROTA_VISUAL_200, SEM_ROTA_404 } from "./fixtures.ts";

test("o pedido tem só os três campos do contrato e vai por POST em JSON", () => {
  const { url, init } = montarRequisicaoDeRota({ origem_id: 3, destino_id: 7, perfil: "cadeirante" });
  assert.equal(url, "/api/rotas");
  assert.equal(init.method, "POST");
  assert.equal(init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(init.body), { origem_id: 3, destino_id: 7, perfil: "cadeirante" });
});

test("a URL dos pontos leva o bbox obrigatório do campus na ordem minLon,minLat,maxLon,maxLat", () => {
  const url = urlDosPontos();
  assert.equal(url, `/api/pontos-interesse?bbox=${BBOX_CAMPUS.join(",")}`);
  const [minLon, minLat, maxLon, maxLat] = BBOX_CAMPUS;
  assert.ok(minLon < maxLon && minLat < maxLat);
  assert.ok(minLon < -46 && minLat < -23, "SP: lon e lat negativas");
});

test("200 válido vira rota com coordenadas, instruções ordenadas e rótulo", () => {
  const r = interpretarRespostaDeRota(200, ROTA_200);
  assert.equal(r.tipo, "ok");
  if (r.tipo !== "ok") return;
  assert.equal(r.rota.coordenadas.length, 4);
  assert.equal(r.rota.instrucoes.length, 3);
  assert.match(r.rota.rotulo, /ainda não conferidos a pé/);
  assert.equal(r.rota.origem.nome, "Portão da rua Piauí");
  assert.equal(r.rota.provisorio, false);
});

test("200 com geometria faltando, torta ou com um ponto só NÃO desenha nada (silêncio)", () => {
  for (const geometria of [undefined, { type: "Point", coordinates: [0, 0] }, { type: "LineString", coordinates: [[-46.65, -23.54]] }, { type: "LineString", coordinates: [[-46.65, "x"], [1, 2]] }, { type: "LineString", coordinates: [[-46.65, -23.54], [999, 2]] }]) {
    const r = interpretarRespostaDeRota(200, { ...ROTA_200, geometria });
    assert.equal(r.tipo, "erro");
    if (r.tipo === "erro") assert.equal(r.mensagem, MENSAGEM_SEM_ROTA);
  }
});

test("200 sem instruções ou com instrução vazia também não vira rota", () => {
  assert.equal(interpretarRespostaDeRota(200, { ...ROTA_200, instrucoes: [] }).tipo, "erro");
  assert.equal(interpretarRespostaDeRota(200, { ...ROTA_200, instrucoes: [{ ordem: 1, texto: " " }] }).tipo, "erro");
  assert.equal(interpretarRespostaDeRota(200, null).tipo, "erro");
});

test("404 sem_rota: a frase combinada e nenhum palpite", () => {
  const r = interpretarRespostaDeRota(404, { mensagem: "Não há caminho mapeado entre esses dois pontos.", codigo: "sem_rota" });
  assert.deepEqual(r, { tipo: "erro", motivo: "sem_rota", mensagem: "Não encontrei um caminho seguro entre esses pontos." });
});

test("404 de ponto inexistente é outro erro (não diz que não há caminho)", () => {
  const r = interpretarRespostaDeRota(404, { mensagem: "Ponto de interesse não encontrado.", campo: "destino_id" });
  assert.equal(r.tipo, "erro");
  if (r.tipo === "erro") {
    assert.equal(r.motivo, "invalido");
    assert.match(r.mensagem, /não foi encontrado/);
  }
});

test("422 usa o detalhe do servidor em português; 503 e outros têm frase própria", () => {
  const r422 = interpretarRespostaDeRota(422, { mensagem: "Pedido de rota inválido.", erros: [{ campo: "destino_id", erro: "Escolha uma entrada de prédio." }] });
  assert.ok(r422.tipo === "erro" && r422.mensagem.includes("Escolha uma entrada de prédio."));
  const r503 = interpretarRespostaDeRota(503, { mensagem: "x" });
  assert.ok(r503.tipo === "erro" && r503.motivo === "indisponivel" && /não está disponível/.test(r503.mensagem));
  const r500 = interpretarRespostaDeRota(500, null);
  assert.ok(r500.tipo === "erro" && r500.motivo === "outro");
  assert.equal(interpretarRespostaDeRota(422, null).tipo, "erro");
});

test("pontos: lê as Features, inverte para latitude/longitude e separa partida e destino", () => {
  const r = interpretarRespostaDePontos(200, PONTOS_200);
  assert.equal(r.tipo, "ok");
  if (r.tipo !== "ok") return;
  assert.equal(r.pontos.length, 3);
  const p = r.pontos[0]!;
  assert.equal(p.latitude, -23.5478);
  assert.equal(p.longitude, -46.6527);
  assert.deepEqual(pontosDePartida(r.pontos).map((x) => x.id), [3, 7]);
  assert.deepEqual(pontosDeDestino(r.pontos).map((x) => x.id), [7], "destino só entrada com nó");
});

test("pontos: feature torta é ignorada; resposta que não é coleção vira erro", () => {
  const r = interpretarRespostaDePontos(200, { features: [{}, PONTOS_200.features[0]] });
  assert.ok(r.tipo === "ok" && r.pontos.length === 1);
  assert.equal(interpretarRespostaDePontos(200, { x: 1 }).tipo, "erro");
  assert.equal(interpretarRespostaDePontos(503, null).tipo, "erro");
});

test("escolha: vazia, só um lado, igual e válida", () => {
  assert.match(problemaNaEscolha(null, null) ?? "", /partida e o destino/);
  assert.match(problemaNaEscolha(null, 7) ?? "", /partida/);
  assert.match(problemaNaEscolha(3, null) ?? "", /destino/);
  assert.match(problemaNaEscolha(3, 3) ?? "", /mesmo ponto/);
  assert.equal(problemaNaEscolha(3, 7), null);
});

test("rede caiu: frase em palavra, sem lançar", async () => {
  const cai = (): Promise<Response> => Promise.reject(new TypeError("fetch failed"));
  const rota = await tracarRota({ origem_id: 1, destino_id: 2, perfil: "sem_restricao" }, cai);
  assert.deepEqual(rota, { tipo: "erro", motivo: "rede", mensagem: MENSAGEM_REDE });
  const pontos = await buscarPontos(cai);
  assert.ok(pontos.tipo === "erro" && pontos.motivo === "rede");
});

test("tracarRota lê status e JSON da resposta; corpo que não é JSON não quebra", async () => {
  const ok = await tracarRota({ origem_id: 3, destino_id: 7, perfil: "sem_restricao" }, async () => new Response(JSON.stringify(ROTA_200), { status: 200 }));
  assert.equal(ok.tipo, "ok");
  const html = await tracarRota({ origem_id: 3, destino_id: 7, perfil: "sem_restricao" }, async () => new Response("<html>413</html>", { status: 413 }));
  assert.ok(html.tipo === "erro" && html.motivo === "outro");
});

test("cadeirante: rota sem escada aparece; sem restrição pode ter escada com aviso", () => {
  assert.equal(interpretarRespostaDeRota(200, ROTA_CADEIRANTE_200, "cadeirante").tipo, "ok");
  const livre = interpretarRespostaDeRota(200, ROTA_200, "sem_restricao");
  assert.ok(livre.tipo === "ok" && livre.rota.avisos.length === 1);
});

test("cadeirante: 200 com escada (trecho, aviso, instrução ou acessível=false) vira sem_rota e nada é desenhado", () => {
  const casos = [
    ROTA_200,
    { ...ROTA_CADEIRANTE_200, trechos: ROTA_200.trechos },
    { ...ROTA_CADEIRANTE_200, avisos: ["O caminho tem escada (cerca de 10 metros)."] },
    { ...ROTA_CADEIRANTE_200, instrucoes: [...ROTA_CADEIRANTE_200.instrucoes.slice(0, 2), { ordem: 3, texto: "Suba a Escada." }] },
    { ...ROTA_CADEIRANTE_200, acessivel_cadeirante: false },
  ];
  for (const corpo of casos) {
    const r = interpretarRespostaDeRota(200, corpo, "cadeirante");
    assert.deepEqual(r, { tipo: "erro", motivo: "sem_rota", mensagem: MENSAGEM_SEM_ROTA });
  }
  // vale também quando só a resposta diz cadeirante
  assert.equal(interpretarRespostaDeRota(200, { ...ROTA_200, perfil: "cadeirante" }).tipo, "erro");
});

test("cadeirante sem alternativa: 404 sem_rota do contrato vira a frase combinada", () => {
  const r = interpretarRespostaDeRota(404, SEM_ROTA_404, "cadeirante");
  assert.ok(r.tipo === "erro" && r.mensagem === MENSAGEM_SEM_ROTA && r.motivo === "sem_rota");
});

test("deficiencia_visual: o pedido leva o perfil e a rota COM escada aparece com os avisos (a defesa é só do cadeirante)", () => {
  const { init } = montarRequisicaoDeRota({ origem_id: 3, destino_id: 7, perfil: "deficiencia_visual" });
  assert.equal(JSON.parse(init.body).perfil, "deficiencia_visual");
  const r = interpretarRespostaDeRota(200, ROTA_VISUAL_200, "deficiencia_visual");
  assert.ok(r.tipo === "ok" && r.rota.perfil === "deficiencia_visual" && r.rota.avisos.length === 2);
  assert.ok(r.tipo === "ok" && r.rota.avisos[0].includes("piso tátil") && rotaTemEscada(r.rota));
  // sem o perfil pedido, vale o perfil da resposta
  assert.equal(interpretarRespostaDeRota(200, ROTA_VISUAL_200).tipo, "ok");
  // o cadeirante continua protegido
  assert.equal(interpretarRespostaDeRota(200, ROTA_VISUAL_200, "cadeirante").tipo, "erro");
});
