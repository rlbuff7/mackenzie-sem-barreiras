import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  CAMINHO_TOKENS_CSS,
  CAMINHO_TOKENS_JSON,
  gerarCss,
  resolverAlias,
} from "./gerar-tokens.mjs";

const tokens = JSON.parse(readFileSync(CAMINHO_TOKENS_JSON, "utf8"));

test("tokens.css versionado é igual ao que o gerador produz (rode `npm run tokens`)", () => {
  const versionado = readFileSync(CAMINHO_TOKENS_CSS, "utf8");
  assert.equal(
    versionado,
    gerarCss(tokens),
    "tokens.json e tokens.css divergem: edite só o tokens.json e rode `npm run tokens`",
  );
});

test("alias {x} vira var(--x) e texto comum passa como está", () => {
  assert.equal(resolverAlias("{primaria}"), "var(--primaria)");
  assert.equal(resolverAlias("0 0 0 2px {mapa-contorno}"), "0 0 0 2px var(--mapa-contorno)");
  assert.equal(resolverAlias("#fff"), "#fff");
});

test("o 1o tema está em :root e os outros em data-tema e nas media queries", () => {
  const css = gerarCss(tokens);
  assert.match(css, /^:root \{\n {2}color-scheme: light;\n {2}--fundo: #ede8dc;/m);
  assert.match(css, /@media \(prefers-color-scheme: dark\) \{\n {2}:root:not\(\[data-tema\]\) \{/);
  assert.match(css, /@media \(prefers-contrast: more\) \{\n {2}:root:not\(\[data-tema\]\) \{/);
  for (const id of ["claro", "escuro", "alto-contraste"]) {
    assert.ok(css.includes(`:root[data-tema="${id}"] {`), `falta o bloco do tema ${id}`);
  }
  // alto contraste depois do escuro: com os dois ativos, vence o alto contraste
  assert.ok(css.indexOf("prefers-contrast: more") > css.indexOf("prefers-color-scheme: dark"));
});

test("color-scheme certo em cada tema", () => {
  const css = gerarCss(tokens);
  const esquema = (seletor) => {
    const i = css.indexOf(seletor);
    assert.ok(i >= 0, `bloco ausente: ${seletor}`);
    return /color-scheme: (\w+);/.exec(css.slice(i))[1];
  };
  assert.equal(esquema(':root[data-tema="claro"]'), "light");
  assert.equal(esquema(':root[data-tema="escuro"]'), "dark");
  assert.equal(esquema(':root[data-tema="alto-contraste"]'), "dark");
});

test("toda variável de cor existe nos 3 temas e as demais famílias saíram", () => {
  const css = gerarCss(tokens);
  for (const t of tokens.color.tokens) {
    // :root, 2 media queries e 3 blocos data-tema: 6 declarações por cor
    const total = css.split(`--${t.name}:`).length - 1;
    assert.equal(total, 6, `--${t.name} apareceu ${total}x, esperado 6`);
  }
  for (const nome of ["espaco-5", "raio-secao", "sombra-marcador", "alvo-toque", "linha-foco"]) {
    assert.ok(css.includes(`--${nome}:`), `falta --${nome}`);
  }
  assert.ok(css.includes("--font-texto:") && css.includes("--font-exibicao:"));
});

test("tema sem valor para um token de cor falha alto", () => {
  const quebrado = structuredClone(tokens);
  delete quebrado.color.tokens[0].value.escuro;
  assert.throws(() => gerarCss(quebrado), /sem valor para o tema "escuro"/);
});
