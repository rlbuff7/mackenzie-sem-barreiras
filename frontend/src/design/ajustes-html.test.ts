/**
 * O topo das duas páginas: "Ajustes" é um botão com aria-expanded e aria-controls que abre um painel
 * (começa fechado) com o seletor de tema e o interruptor "Reduzir animações". Conferido no HTML.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

for (const pagina of ["index.html", "medicao.html"]) {
  const html = readFileSync(new URL(`../../${pagina}`, import.meta.url), "utf8");

  test(`${pagina}: botão Ajustes com aria-expanded=false e aria-controls do painel`, () => {
    const botao = /<button[^>]*id="botao-ajustes"[^>]*>\s*Ajustes\s*<\/button>/.exec(html)?.[0] ?? "";
    assert.ok(botao, "falta o botão Ajustes");
    assert.match(botao, /type="button"/);
    assert.match(botao, /aria-expanded="false"/);
    assert.match(botao, /aria-controls="painel-ajustes"/);
  });

  test(`${pagina}: o painel começa escondido e guarda o tema e o interruptor de movimento`, () => {
    const abertura = /<div[^>]*id="painel-ajustes"[^>]*>/.exec(html);
    assert.ok(abertura, "falta o painel de ajustes");
    assert.match(abertura[0], /\shidden[\s>]/);
    assert.match(abertura[0], /aria-labelledby="botao-ajustes"/);
    const depois = html.slice(html.indexOf(abertura[0]));
    const painel = depois.slice(0, depois.indexOf('id="nota-movimento"'));
    assert.ok(painel.includes('id="seletor-tema"'), "o tema tem de estar dentro do painel");
    assert.ok(painel.includes('id="interruptor-movimento"'), "o interruptor tem de estar dentro do painel");
  });
}

test("medicao.html: o topo tem numa linha só '← Início', 'Ajustes' e 'Recomeçar'", () => {
  const html = readFileSync(new URL("../../medicao.html", import.meta.url), "utf8");
  const linha = /<div class="medicao__linha">([\s\S]*?)<\/div>/.exec(html)?.[1] ?? "";
  const ordem = ["← Início", ">Ajustes<", ">Recomeçar<"].map((t) => linha.indexOf(t));
  assert.ok(ordem.every((i) => i >= 0), "falta um dos três itens na linha do topo");
  assert.deepEqual([...ordem].sort((a, b) => a - b), ordem, "ordem esperada: Início, Ajustes, Recomeçar");
  assert.doesNotMatch(linha, /seletor-tema|interruptor/, "tema e movimento ficam só dentro de Ajustes");
});

test("a lógica do painel está em ajustes.ts e as duas páginas a iniciam", () => {
  for (const caminho of ["../inicio/pagina.ts", "../medicao/pagina.ts"]) {
    const fonte = readFileSync(new URL(caminho, import.meta.url), "utf8");
    assert.match(fonte, /import \{ iniciarAjustes \} from "\.\.\/design\/ajustes\.ts";/);
    assert.match(fonte, /\niniciarAjustes\(\);/);
  }
});

test("abrir Ajustes não anima: o ajustes.ts não mexe em estilo nem em transição", () => {
  const fonte = readFileSync(new URL("./ajustes.ts", import.meta.url), "utf8");
  assert.doesNotMatch(fonte, /style|transition|animate|classList/);
});
