/**
 * Estrutura da página de medição em etapas, conferida no HTML (a página depende do DOM e não roda
 * no node:test): três etapas com título focável, um só anúncio em aria-live, "Recomeçar" sempre à
 * vista (fora das etapas) e o que o E2E (backend/scripts/ponta_a_ponta.py) confere.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { ETAPAS, textoEtapa, tituloEtapa } from "./fluxo.ts";
import { PONTOS_CONTROLE } from "./pontos-controle.ts";

const html = readFileSync(new URL("../../medicao.html", import.meta.url), "utf8");

function secao(id: string): string {
  const m = new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>\\s*(?=<section|<!--|</main>)`).exec(html);
  assert.ok(m, `falta <section id="${id}">`);
  return m[1]!;
}

test("o que o E2E confere continua na página: <title> e o botão 'Registrar agora'", () => {
  assert.ok(html.includes("<title>Medição de GPS — Mackenzie</title>"));
  assert.match(html, /<button[^>]*id="botao-registrar"[^>]*>Registrar agora<\/button>/);
});

for (const etapa of ETAPAS) {
  test(`etapa ${etapa.id}: seção com título h2 focável (tabindex=-1) e o contador "${textoEtapa(etapa.id)}"`, () => {
    const abertura = new RegExp(`<section[^>]*id="etapa-${etapa.id}"[^>]*>`).exec(html)?.[0] ?? "";
    assert.match(abertura, new RegExp(`aria-labelledby="titulo-etapa-${etapa.id}"`));
    assert.match(abertura, /class="[^"]*medicao__etapa[^"]*"/);
    const titulo = new RegExp(`<h2[^>]*id="titulo-etapa-${etapa.id}"[^>]*>([\\s\\S]*?)</h2>`).exec(html);
    assert.ok(titulo, `falta o h2 da etapa ${etapa.id}`);
    assert.match(titulo[0], /tabindex="-1"/);
    assert.ok(titulo[1]!.includes(textoEtapa(etapa.id)), "o contador da etapa tem de estar no título");
    assert.ok(titulo[1]!.includes(tituloEtapa(etapa.id)), "o nome da etapa tem de estar no título");
  });
}

test("só a etapa de entrada pode estar sem hidden; as outras duas começam escondidas", () => {
  const sem = ETAPAS.filter((e) => !new RegExp(`<section[^>]*id="etapa-${e.id}"[^>]*\\shidden[\\s>]`).test(html));
  assert.ok(sem.length <= 1, `mais de uma etapa visível no HTML: ${sem.map((e) => e.id).join(", ")}`);
});

test("há um único anúncio de etapa em aria-live polite e um único h1", () => {
  assert.equal(html.match(/id="anuncio-etapa"/g)?.length, 1);
  const anuncio = /<p[^>]*id="anuncio-etapa"[^>]*>/.exec(html)?.[0] ?? "";
  assert.match(anuncio, /aria-live="polite"/);
  assert.match(anuncio, /role="status"/);
  assert.match(anuncio, /oculto-visualmente/);
  assert.equal(html.match(/<h1[\s>]/g)?.length, 1);
});

test("'Recomeçar' está sempre à vista: no cabeçalho, fora das etapas e sem hidden", () => {
  const botao = /<button[^>]*id="botao-recomecar"[^>]*>\s*Recomeçar\s*<\/button>/.exec(html);
  assert.ok(botao, "falta o botão Recomeçar");
  const pos = html.indexOf(botao[0]);
  for (const e of ETAPAS) {
    const ini = html.indexOf(`id="etapa-${e.id}"`);
    const fim = html.indexOf("</section>", ini);
    assert.ok(pos < ini || pos > fim, `Recomeçar está dentro da etapa ${e.id}`);
  }
  assert.ok(pos < html.indexOf("<main"), "Recomeçar deve ficar antes do conteúdo das etapas, no cabeçalho");
  assert.doesNotMatch(botao[0], /hidden/);
});

test("a confirmação de Recomeçar começa escondida, é um grupo nomeado e tem 'Sim' e 'Não'", () => {
  const caixa = /<div[^>]*id="confirmar-recomecar"[^>]*>/.exec(html)?.[0] ?? "";
  assert.match(caixa, /role="group"/);
  assert.match(caixa, /aria-labelledby="texto-confirmar"/);
  assert.match(caixa, /\shidden[\s>]/);
  assert.match(html, /id="botao-recomecar-sim"[^>]*>\s*Sim, recomeçar\s*<\/button>/);
  assert.match(html, /id="botao-recomecar-nao"[^>]*>\s*Não, continuar\s*<\/button>/);
  assert.doesNotMatch(html, /botao-recomecar-exportar/, "Recomeçar não apaga mais o que não foi enviado: sem 'Exportar antes'");
});

test("campos no lugar certo: aparelho, código e ponto em Preparar; condição e observação em Medir", () => {
  const preparar = secao("etapa-preparar");
  for (const id of ["campo-aparelho", "campo-codigo", "campo-ponto", "botao-continuar"]) {
    assert.ok(preparar.includes(`id="${id}"`), `${id} deveria estar em Preparar`);
  }
  const medir = secao("etapa-medir");
  for (const id of ["campo-condicao", "campo-observacao", "mapa-medicao", "painel-precisao", "painel-contagem"]) {
    assert.ok(medir.includes(`id="${id}"`), `${id} deveria estar em Medir`);
  }
  const resultado = secao("etapa-resultado");
  for (const id of ["cartao-estado", "botao-proximo", "lista-registros"]) {
    assert.ok(resultado.includes(`id="${id}"`), `${id} deveria estar em Resultado`);
  }
});

test("o texto do Recomeçar não promete apagar o servidor (a confirmação vem de fluxo.ts)", () => {
  assert.doesNotMatch(html, /apagar todos os registros/i);
});

test("só a etapa Preparar entra com fade: Medir (mapa e leituras) e Resultado (avisos de envio) nunca animam", () => {
  const classe = (id: string) => new RegExp(`<section[^>]*id="${id}"[^>]*class="([^"]*)"`).exec(html)?.[1] ?? "";
  assert.match(classe("etapa-preparar"), /medicao__etapa--suave/);
  assert.doesNotMatch(classe("etapa-medir"), /suave/);
  assert.doesNotMatch(classe("etapa-resultado"), /suave/);
});

test("pontos de controle: 10 segmentos, 'de 10' e nome, observação e legenda do ◆ na etapa Medir", () => {
  const total = String(PONTOS_CONTROLE.length);
  assert.equal(html.match(/class="medicao__segmento"/g)?.length, PONTOS_CONTROLE.length);
  assert.match(html, new RegExp(`aria-valuemax="${total}"`));
  assert.match(html, new RegExp(`Ponto 1 de ${total}`));
  assert.match(html, new RegExp(`max="${total}"`));
  assert.doesNotMatch(html, /de 12\b|a 12\)|max="12"/);
  const medir = secao("etapa-medir");
  for (const id of ["ponto-nome", "ponto-observacao", "legenda-referencia"]) {
    assert.ok(medir.includes(`id="${id}"`), `${id} deveria estar em Medir`);
  }
});
