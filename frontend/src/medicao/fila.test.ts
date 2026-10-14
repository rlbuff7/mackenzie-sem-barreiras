import assert from "node:assert/strict";
import { test } from "node:test";
import {
  FilaEnvio,
  MAX_BYTES_LOTE,
  atrasoReenvio_ms,
  interpretar422,
  montarLote,
  novoUuid,
  paraMedicaoApi,
  type FetchSimulavel,
  type ItemFila,
  type RespostaMinima,
} from "./fila.ts";
import { montarRegistroBussola, montarRegistroPosicao, montarRegistroVibracao, type Registro } from "./medicao.ts";

const agora = new Date("2026-10-22T13:05:09.000Z");

function regPonto(n = 3, extra: Partial<Registro> = {}): Registro {
  return {
    ...montarRegistroPosicao({
      tipo: "ponto",
      posicao: { latitude: -23.5475, longitude: -46.6523, accuracy: 6.5, altitude: null, altitudeAccuracy: null, speed: null, heading: null },
      ponto: n,
      aparelho: "Galaxy A54",
      condicao: "entre_predios",
      observacao: "",
      userAgent: "UA-teste",
      agora,
    }),
    ...extra,
  };
}

function memoria() {
  let guardado: string | null = null;
  return {
    ler: () => guardado,
    gravar: (v: string) => {
      guardado = v;
    },
    get conteudo() {
      return guardado;
    },
  };
}

const resp = (status: number, corpo: unknown = {}): RespostaMinima => ({ status, json: async () => corpo });

interface Chamada {
  url: string;
  metodo: string;
  cabecalhos: Record<string, string>;
  corpo: { medicoes: Record<string, unknown>[] };
}

function criar(responder: (c: Chamada, n: number) => RespostaMinima | Promise<RespostaMinima>, codigo = "equipe-123") {
  const chamadas: Chamada[] = [];
  const fetch: FetchSimulavel = async (url, init) => {
    const c: Chamada = { url, metodo: init.method, cabecalhos: init.headers, corpo: JSON.parse(init.body) };
    chamadas.push(c);
    return responder(c, chamadas.length);
  };
  const arm = memoria();
  let n = 0;
  const ids = () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`;
  const estado = { codigo };
  const fila = new FilaEnvio({ armazenamento: arm, fetch, novoId: ids, codigo: () => estado.codigo });
  return { fila, chamadas, arm, estado, ids };
}

const okGravou = (c: Chamada): RespostaMinima => resp(200, { gravadas: c.corpo.medicoes.length, repetidas: 0 });

test("paraMedicaoApi usa os nomes exatos do contrato e omite o que não existe", () => {
  const m = paraMedicaoApi("id-1", regPonto(3, { observacao: " perto do 9 ", altitude_m: 760.2, precisao_altitude_m: 4, velocidade_ms: 0, rumo_graus: 90 }));
  assert.deepEqual(m, {
    id_cliente: "id-1",
    tipo: "ponto",
    medido_em: "2026-10-22T13:05:09.000Z",
    aparelho: "Galaxy A54",
    ponto: 3,
    condicao: "entre_predios",
    latitude: -23.5475,
    longitude: -46.6523,
    precisao_m: 6.5,
    altitude_m: 760.2,
    altitude_precisao_m: 4,
    velocidade_ms: 0,
    rumo_gps_graus: 90,
    observacao: "perto do 9",
    user_agent: "UA-teste",
  });
  assert.ok(!("bussola_graus" in m));
  assert.ok(!("vibracao_suportada" in m));
});

test("paraMedicaoApi: bússola e vibração mapeiam para bussola_* e vibracao_suportada", () => {
  const b = paraMedicaoApi(
    "id-b",
    montarRegistroBussola({
      rumo_graus: 359.999,
      fonte: "alpha_absoluto",
      oscilacao: { minimo_graus: 350, maximo_graus: 10, oscilacao_graus: 20, amostras: 5 },
      aparelho: "iPhone 13",
      userAgent: "ua",
      agora,
    }),
  );
  assert.equal(b.tipo, "bussola");
  assert.equal(b.bussola_graus, 359.999);
  assert.equal(b.bussola_fonte, "alpha_absoluto");
  assert.equal(b.bussola_oscilacao_graus, 20);
  const volta = paraMedicaoApi("id-c", montarRegistroBussola({ rumo_graus: 360, fonte: "alpha_absoluto", oscilacao: null, aparelho: "x", userAgent: "", agora }));
  assert.equal(volta.bussola_graus, 0, "o banco só aceita 0 <= x < 360");
  assert.ok(!("user_agent" in volta));
  const v = paraMedicaoApi("id-v", montarRegistroVibracao({ existe: false, retorno: null, aparelho: "iPhone 13", userAgent: "ua", agora }));
  assert.equal(v.vibracao_suportada, false);
  assert.ok(!("latitude" in v));
});

test("paraMedicaoApi corta aparelho, observação e user agent nos limites do contrato", () => {
  const m = paraMedicaoApi("i", regPonto(1, { aparelho: "a".repeat(120), observacao: "o".repeat(900), user_agent: "u".repeat(500) }));
  assert.equal(m.aparelho.length, 80);
  assert.equal(m.observacao?.length, 500);
  assert.equal(m.user_agent?.length, 300);
});

test("novoUuid usa randomUUID quando existe e cai para getRandomValues em HTTP puro", () => {
  assert.equal(novoUuid({ randomUUID: () => "fixo" }), "fixo");
  const u = novoUuid({ getRandomValues: (a) => a.fill(7) });
  assert.match(u, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.match(novoUuid({}), /^[0-9a-f]{8}-[0-9a-f]{4}-4/);
});

test("200 {gravadas, repetidas}: POST /api/medicoes com header e corpo do contrato; itens viram enviado", async () => {
  const { fila, chamadas } = criar(okGravou);
  fila.adicionar(regPonto(1));
  fila.adicionar(regPonto(1));
  const r = await fila.descarregar();
  assert.equal(r.situacao, "enviado");
  assert.equal(r.gravadas, 2);
  assert.equal(chamadas.length, 1);
  assert.equal(chamadas[0]!.url, "/api/medicoes");
  assert.equal(chamadas[0]!.metodo, "POST");
  assert.equal(chamadas[0]!.cabecalhos["X-Codigo-Equipe"], "equipe-123");
  assert.equal(chamadas[0]!.cabecalhos["Content-Type"], "application/json");
  assert.deepEqual(Object.keys(chamadas[0]!.corpo), ["medicoes"]);
  assert.equal(chamadas[0]!.corpo.medicoes[0]!.id_cliente, "00000000-0000-4000-8000-000000000001");
  assert.deepEqual(fila.contagem(), { na_fila: 0, enviado: 2, recusado: 0 });
  assert.equal(fila.falhasSeguidas, 0);
});

test("repetidas contam como enviado (reenvio idempotente)", async () => {
  const { fila } = criar(() => resp(200, { gravadas: 0, repetidas: 1 }));
  fila.adicionar(regPonto());
  const r = await fila.descarregar();
  assert.equal(r.repetidas, 1);
  assert.equal(fila.itens[0]!.estado, "enviado");
});

test("120 itens saem em lotes de no máximo 50", async () => {
  const { fila, chamadas } = criar(okGravou);
  for (let i = 0; i < 120; i++) fila.adicionar(regPonto(1, { user_agent: "" }));
  await fila.descarregar();
  assert.deepEqual(chamadas.map((c) => c.corpo.medicoes.length), [50, 50, 20]);
  assert.equal(fila.contagem().enviado, 120);
});

test("o lote também respeita o limite de bytes do corpo (16 KiB no servidor)", () => {
  const itens: ItemFila[] = Array.from({ length: 50 }, (_, i) => ({
    id_cliente: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
    registro: regPonto(1, { user_agent: "u".repeat(300), observacao: "o".repeat(200) }),
    estado: "na_fila",
    motivo: null,
    recusado_por_codigo: false,
    isolar: false,
  }));
  const lote = montarLote(itens);
  assert.ok(lote.length < 50 && lote.length > 0);
  const bytes = new TextEncoder().encode(JSON.stringify({ medicoes: lote.map((i) => paraMedicaoApi(i.id_cliente, i.registro)) })).length;
  assert.ok(bytes <= MAX_BYTES_LOTE, `corpo de ${bytes} bytes passou do limite`);
  assert.ok(MAX_BYTES_LOTE < 16 * 1024);
});

test("sem código da equipe: nada é enviado e os itens ficam na fila", async () => {
  const { fila, chamadas } = criar(okGravou, "  ");
  fila.adicionar(regPonto());
  const r = await fila.descarregar();
  assert.equal(r.situacao, "sem_codigo");
  assert.equal(r.mensagem, "falta o código da equipe");
  assert.equal(chamadas.length, 0);
  assert.equal(fila.itens[0]!.estado, "na_fila");
});

test("401: tudo vira recusado por código errado e volta para a fila quando o código muda", async () => {
  const { fila, estado, chamadas } = criar((c, n) => (n === 1 ? resp(401, { detail: "x" }) : okGravou(c)));
  fila.adicionar(regPonto(1));
  fila.adicionar(regPonto(2));
  const r = await fila.descarregar();
  assert.equal(r.situacao, "codigo_errado");
  assert.deepEqual(fila.itens.map((i) => [i.estado, i.motivo]), [
    ["recusado", "código da equipe errado"],
    ["recusado", "código da equipe errado"],
  ]);
  assert.equal(fila.falhasSeguidas, 0, "código errado não é falha de rede: não entra no recuo");
  assert.equal((await fila.descarregar()).situacao, "nada");
  estado.codigo = "novo-codigo";
  assert.equal(fila.reabrirRecusadosPorCodigo(), 2);
  const r2 = await fila.descarregar();
  assert.equal(r2.situacao, "enviado");
  assert.equal(chamadas[1]!.cabecalhos["X-Codigo-Equipe"], "novo-codigo");
});

test("422 com o índice do item: só aquele é recusado, com o campo no motivo; os outros seguem", async () => {
  const { fila, chamadas } = criar((c, n) =>
    n === 1
      ? resp(422, { detail: [{ loc: ["body", "medicoes", 1, "precisao_m"], msg: "Input should be >= 0", type: "x" }] })
      : okGravou(c),
  );
  fila.adicionar(regPonto(1));
  fila.adicionar(regPonto(2));
  fila.adicionar(regPonto(3));
  const r = await fila.descarregar();
  assert.equal(r.situacao, "enviado");
  assert.equal(chamadas.length, 2);
  assert.deepEqual(fila.itens.map((i) => i.estado), ["enviado", "recusado", "enviado"]);
  assert.equal(fila.itens[1]!.motivo, "campo precisao_m: Input should be >= 0");
});

test("422 sem dizer qual item: os itens vão um por vez e só o inválido é recusado", async () => {
  const { fila, chamadas } = criar((c) => {
    const ruim = c.corpo.medicoes.some((m) => m.ponto === 2);
    return ruim ? resp(422, { detail: "inválido" }) : okGravou(c);
  });
  fila.adicionar(regPonto(1));
  fila.adicionar(regPonto(2));
  fila.adicionar(regPonto(3));
  await fila.descarregar();
  assert.deepEqual(fila.itens.map((i) => i.estado), ["enviado", "recusado", "enviado"]);
  assert.equal(fila.itens[1]!.motivo, "inválido");
  assert.ok(chamadas.length >= 4);
});

test("422 com índice fora do lote não trava em laço infinito", async () => {
  const { fila } = criar(() => resp(422, { detail: [{ loc: ["body", "medicoes", 99, "x"], msg: "m" }] }));
  fila.adicionar(regPonto(1));
  fila.adicionar(regPonto(2));
  await fila.descarregar();
  assert.deepEqual(fila.itens.map((i) => i.estado), ["recusado", "recusado"]);
});

test("503: continua na fila, com o motivo 'medição desligada no servidor', e entra no recuo", async () => {
  const { fila } = criar(() => resp(503, { detail: "Medição desligada neste servidor." }));
  fila.adicionar(regPonto());
  const r = await fila.descarregar();
  assert.equal(r.situacao, "desligada");
  assert.equal(r.mensagem, "medição desligada no servidor");
  assert.equal(fila.itens[0]!.estado, "na_fila");
  assert.equal(fila.itens[0]!.motivo, "medição desligada no servidor");
  assert.equal(fila.falhasSeguidas, 1);
  assert.equal(fila.proximoAtraso_ms(), 5000);
});

test("sem sinal (fetch rejeita): fica na fila, recuo 5, 10, 30, 60 s e depois estável; sucesso zera", async () => {
  let ligado = false;
  const { fila } = criar((c) => {
    if (!ligado) throw new TypeError("Failed to fetch");
    return okGravou(c);
  });
  fila.adicionar(regPonto());
  const atrasos: number[] = [];
  for (let i = 0; i < 6; i++) {
    const r = await fila.descarregar();
    assert.equal(r.situacao, "sem_sinal");
    atrasos.push(fila.proximoAtraso_ms());
  }
  assert.deepEqual(atrasos, [5000, 10000, 30000, 60000, 60000, 60000]);
  assert.equal(fila.itens[0]!.estado, "na_fila");
  ligado = true;
  assert.equal((await fila.descarregar()).situacao, "enviado");
  assert.equal(fila.proximoAtraso_ms(), 10000);
});

test("atrasoReenvio_ms: 10 s sem erro", () => {
  assert.equal(atrasoReenvio_ms(0), 10000);
  assert.equal(atrasoReenvio_ms(2), 10000);
  assert.equal(atrasoReenvio_ms(3), 30000);
});

test("429 e 500 ficam na fila com o código no motivo", async () => {
  const { fila } = criar(() => resp(429));
  fila.adicionar(regPonto());
  assert.equal((await fila.descarregar()).situacao, "erro_servidor");
  assert.equal(fila.itens[0]!.motivo, "erro 429 do servidor");
  assert.equal(fila.itens[0]!.estado, "na_fila");
});

test("200 que não é a resposta do contrato não conta como enviado", async () => {
  const { fila } = criar(() => resp(200, "<html>proxy</html>"));
  fila.adicionar(regPonto());
  assert.equal((await fila.descarregar()).situacao, "erro_servidor");
  assert.equal(fila.itens[0]!.estado, "na_fila");
});

test("413: divide o lote ao meio até caber; item sozinho grande demais é recusado", async () => {
  const { fila, chamadas } = criar((c) => (c.corpo.medicoes.length > 2 ? resp(413) : okGravou(c)));
  for (let i = 0; i < 5; i++) fila.adicionar(regPonto(1));
  await fila.descarregar();
  assert.equal(fila.contagem().enviado, 5);
  assert.ok(chamadas.every((c, i) => i === 0 || c.corpo.medicoes.length <= 2));
  const g = criar(() => resp(413));
  g.fila.adicionar(regPonto(1));
  await g.fila.descarregar();
  assert.equal(g.fila.itens[0]!.estado, "recusado");
});

test("duas chamadas ao mesmo tempo: a segunda volta 'ocupado' e não duplica o POST", async () => {
  let liberar: (() => void) | null = null;
  const { fila, chamadas } = criar(
    (c) =>
      new Promise<RespostaMinima>((resolve) => {
        liberar = () => resolve(okGravou(c));
      }),
  );
  fila.adicionar(regPonto());
  const a = fila.descarregar();
  const b = await fila.descarregar();
  assert.equal(b.situacao, "ocupado");
  assert.equal(fila.estaEnviando, true);
  await Promise.resolve();
  liberar!();
  assert.equal((await a).situacao, "enviado");
  assert.equal(chamadas.length, 1);
  assert.equal(fila.estaEnviando, false);
});

test("registro adicionado durante o envio fica de fora daquele lote e sai na mesma rodada", async () => {
  let liberar: (() => void) | null = null;
  const { fila } = criar(
    (c) =>
      new Promise<RespostaMinima>((resolve) => {
        liberar = () => resolve(okGravou(c));
      }),
  );
  fila.adicionar(regPonto(1));
  const a = fila.descarregar();
  await Promise.resolve();
  const novo = fila.adicionar(regPonto(2));
  liberar!();
  await new Promise((r) => setTimeout(r, 0));
  liberar?.();
  await a;
  assert.equal(novo.estado, "enviado", "a mesma rodada pega o novo e o envia em seguida");
});

test("a fila sobrevive a recarregar a página (localStorage) e mantém os estados", async () => {
  const a = criar(okGravou);
  a.fila.adicionar(regPonto(1));
  await a.fila.descarregar();
  a.fila.adicionar(regPonto(2));
  const b = new FilaEnvio({ armazenamento: a.arm, fetch: async () => resp(200), codigo: () => "x", novoId: a.ids });
  assert.deepEqual(b.itens.map((i) => i.estado), ["enviado", "na_fila"]);
  assert.equal(b.registros().length, 2);
});

test("armazenamento quebrado ou lixo guardado: a fila começa vazia e avisa, sem lançar erro", () => {
  const ruim = { ler: () => "{lixo", gravar: () => { throw new Error("cheio"); } };
  const f = new FilaEnvio({ armazenamento: ruim, fetch: async () => resp(200), codigo: () => "x" });
  assert.equal(f.itens.length, 0);
  assert.equal(f.armazenamentoFunciona, false);
  f.adicionar(regPonto());
  assert.equal(f.itens.length, 1);
});

test("importarLegado põe os registros antigos na fila com id novo; apagarTudo limpa", () => {
  const { fila } = criar(okGravou);
  fila.importarLegado([regPonto(1), regPonto(2)]);
  assert.equal(fila.contagem().na_fila, 2);
  assert.notEqual(fila.itens[0]!.id_cliente, fila.itens[1]!.id_cliente);
  fila.apagarTudo();
  assert.equal(fila.itens.length, 0);
});

test("interpretar422 monta 'campo x: mensagem' por índice e tolera formatos estranhos", () => {
  const e = interpretar422({ detail: [{ loc: ["body", "medicoes", 0, "latitude"], msg: "fora da faixa" }, { loc: ["body"], msg: "geral ruim" }] });
  assert.equal(e.porIndice.get(0), "campo latitude: fora da faixa");
  assert.equal(e.geral, "geral ruim");
  assert.equal(interpretar422(null).geral, "dados recusados pelo servidor (422)");
  assert.equal(interpretar422({ detail: "texto" }).geral, "texto");
});
