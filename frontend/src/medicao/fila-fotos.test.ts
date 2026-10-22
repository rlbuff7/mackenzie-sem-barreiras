import assert from "node:assert/strict";
import { test } from "node:test";
import { FilaFotos, type ArmazemFotos, type FetchFoto, type ItemFoto } from "./fila-fotos.ts";

function armazemFake(): ArmazemFotos & { dados: Map<string, ItemFoto> } {
  const dados = new Map<string, ItemFoto>();
  return {
    dados,
    listar: async () => [...dados.values()],
    gravar: async (i) => void dados.set(i.id_cliente, i),
    remover: async (id) => void dados.delete(id),
  };
}

const dados = (id: string) => ({ id_cliente: id, ponto: 3, aparelho: "Galaxy", tirada_em: "2026-10-22T10:00:00Z" });
const blob = { size: 1000, type: "image/jpeg" };
const resp = (status: number, corpo: unknown = null) => async () => ({ status, json: async () => corpo });

test("200 grava: sai do armazém e fica enviada; cabeçalhos e corpo conforme o contrato", async () => {
  const arm = armazemFake();
  const chamadas: { url: string; headers: Record<string, string>; body: unknown }[] = [];
  const f: FetchFoto = async (url, init) => {
    chamadas.push({ url, headers: init.headers, body: init.body });
    return { status: 200, json: async () => ({ gravada: true }) };
  };
  const fila = new FilaFotos({ armazem: arm, fetch: f, codigo: () => " segredo " });
  const r = await fila.adicionar(dados("u1"), blob);
  assert.equal(r.guardada, true);
  assert.equal(r.item?.estado, "enviada");
  assert.equal(arm.dados.size, 0);
  assert.equal(chamadas[0]!.headers["Content-Type"], "image/jpeg");
  assert.equal(chamadas[0]!.headers["X-Codigo-Equipe"], "segredo");
  assert.equal(chamadas[0]!.body, blob);
  assert.match(chamadas[0]!.url, /^\/api\/medicoes\/fotos\?id_cliente=u1&ponto=3&/);
});

test("sem sinal: fica guardada na fila e é reenviada depois; recuo cresce e zera", async () => {
  const arm = armazemFake();
  let online = false;
  const fila = new FilaFotos({
    armazem: arm,
    fetch: async () => {
      if (!online) throw new Error("rede");
      return { status: 200, json: async () => ({ gravada: false }) };
    },
    codigo: () => "c",
  });
  const r = await fila.adicionar(dados("u1"), blob);
  assert.equal(r.guardada, true);
  assert.equal(r.item?.estado, "na_fila");
  assert.equal(arm.dados.size, 1);
  assert.equal(fila.proximoAtraso_ms(), 5000);
  online = true;
  assert.equal(await fila.descarregar(), "enviado");
  assert.equal(r.item?.estado, "enviada");
  assert.equal(arm.dados.size, 0);
  assert.equal(fila.proximoAtraso_ms(), 10_000);
});

test("503 e 429 ficam na fila; 413/415/422 recusam com motivo e saem do armazém", async () => {
  for (const s of [503, 429]) {
    const fila = new FilaFotos({ armazem: armazemFake(), fetch: resp(s), codigo: () => "c" });
    const r = await fila.adicionar(dados("u"), blob);
    assert.equal(r.item?.estado, "na_fila", String(s));
  }
  for (const s of [413, 415, 422]) {
    const arm = armazemFake();
    const fila = new FilaFotos({ armazem: arm, fetch: resp(s, { mensagem: "motivo X" }), codigo: () => "c" });
    const r = await fila.adicionar(dados("u"), blob);
    assert.equal(r.item?.estado, "recusada", String(s));
    assert.ok(r.item?.motivo);
    assert.equal(arm.dados.size, 0);
  }
});

test("401 recusa tudo até o código mudar; depois volta para a fila", async () => {
  const arm = armazemFake();
  let status = 401;
  const fila = new FilaFotos({
    armazem: arm,
    fetch: async () => ({ status, json: async () => ({ gravada: true }) }),
    codigo: () => "c",
  });
  const a = await fila.adicionar(dados("u1"), blob);
  assert.equal(a.item?.estado, "recusada");
  assert.equal(a.item?.recusada_por_codigo, true);
  assert.equal(arm.dados.size, 1);
  status = 200;
  assert.equal(fila.reabrirRecusadasPorCodigo(), 1);
  assert.equal(await fila.descarregar(), "enviado");
  assert.equal(a.item?.estado, "enviada");
});

test("sem código: nada é enviado e a foto fica na fila com o motivo", async () => {
  let chamou = false;
  const fila = new FilaFotos({
    armazem: armazemFake(),
    fetch: async () => {
      chamou = true;
      return { status: 200, json: async () => ({}) };
    },
    codigo: () => "  ",
  });
  const r = await fila.adicionar(dados("u"), blob);
  assert.equal(chamou, false);
  assert.equal(r.item?.estado, "na_fila");
  assert.equal(r.item?.motivo, "falta o código da equipe");
});

test("sem IndexedDB: envia direto; se falhar, avisa que não deu para guardar", async () => {
  const ok = new FilaFotos({ armazem: null, fetch: resp(200, { gravada: true }), codigo: () => "c" });
  const a = await ok.adicionar(dados("u1"), blob);
  assert.equal(a.item?.estado, "enviada");
  assert.equal(a.guardada, false);
  assert.equal(a.motivo, null);

  const sem = new FilaFotos({ armazem: null, fetch: async () => { throw new Error("rede"); }, codigo: () => "c" });
  const b = await sem.adicionar(dados("u2"), blob);
  assert.equal(b.item, null);
  assert.equal(b.motivo, "não foi possível guardar a foto sem sinal");
  assert.equal(sem.itens.length, 0);
});

test("gravação no armazém falha: cai para o envio direto", async () => {
  const arm = armazemFake();
  arm.gravar = async () => { throw new Error("cota"); };
  const fila = new FilaFotos({ armazem: arm, fetch: async () => { throw new Error("rede"); }, codigo: () => "c" });
  const r = await fila.adicionar(dados("u"), blob);
  assert.equal(r.motivo, "não foi possível guardar a foto sem sinal");
  assert.equal(fila.temArmazem, false);
});

test("carregar traz o que ficou guardado", async () => {
  const arm = armazemFake();
  arm.dados.set("u9", { ...dados("u9"), blob, estado: "na_fila", motivo: null, recusada_por_codigo: false });
  const fila = new FilaFotos({ armazem: arm, fetch: resp(200, { gravada: true }), codigo: () => "c" });
  await fila.carregar();
  assert.equal(fila.itens.length, 1);
  assert.equal(await fila.descarregar(), "enviado");
});
