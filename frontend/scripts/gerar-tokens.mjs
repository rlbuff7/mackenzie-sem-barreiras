#!/usr/bin/env node
/**
 * Gera src/design/tokens.css a partir de src/design/tokens.json (fonte única do
 * Design System "Navegação Acessível no Campus"). Sem dependência nova.
 *
 *   npm run tokens          escreve src/design/tokens.css
 *   npm run tokens -- --stdout   imprime no terminal sem gravar
 *
 * Regras de saída:
 * - cores do 1º tema em `:root`;
 * - `escuro` segue `prefers-color-scheme: dark` e `alto-contraste` segue
 *   `prefers-contrast: more`, só quando a pessoa não escolheu um tema (sem
 *   `data-tema` no <html>); `alto-contraste` vem por último e vence o escuro;
 * - `:root[data-tema="<id>"]` força cada tema, vença o que vencer o sistema;
 * - `color-scheme` de cada tema sai da luminância do token `fundo`;
 * - o resto (espaçamento, raios, sombra, tamanho, espessura, famílias de fonte)
 *   vira variável em `:root`; `{x}` dentro de um valor vira `var(--x)`.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url));
export const CAMINHO_TOKENS_JSON = resolve(AQUI, "../src/design/tokens.json");
export const CAMINHO_TOKENS_CSS = resolve(AQUI, "../src/design/tokens.css");

// Grupos do JSON que não são famílias de variáveis simples.
const GRUPOS_ESPECIAIS = new Set(["name", "version", "meta", "color", "type"]);

/** `{x}` vira `var(--x)`; qualquer outro texto passa como está. */
export function resolverAlias(valor) {
  return String(valor).replace(/\{([a-z0-9-]+)\}/gi, "var(--$1)");
}

/** Luminância relativa (WCAG) de uma cor #rrggbb; null se não for hexadecimal simples. */
function luminancia(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return null;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function esquemaDoTema(tokens, idTema) {
  const fundo = tokens.color.tokens.find((t) => t.name === "fundo");
  const lum = fundo ? luminancia(fundo.value[idTema]) : null;
  return lum !== null && lum < 0.18 ? "dark" : "light";
}

function linhasDoTema(tokens, idTema, recuo) {
  const linhas = [`${recuo}color-scheme: ${esquemaDoTema(tokens, idTema)};`];
  for (const t of tokens.color.tokens) {
    if (!(idTema in t.value)) {
      throw new Error(`Token de cor "${t.name}" sem valor para o tema "${idTema}"`);
    }
    linhas.push(`${recuo}--${t.name}: ${resolverAlias(t.value[idTema])};`);
  }
  return linhas;
}

function linhasSimples(tokens) {
  const linhas = [];
  for (const [grupo, conteudo] of Object.entries(tokens)) {
    if (GRUPOS_ESPECIAIS.has(grupo) || !Array.isArray(conteudo?.tokens)) continue;
    linhas.push(`  /* ${grupo} */`);
    for (const t of conteudo.tokens) linhas.push(`  --${t.name}: ${resolverAlias(t.value)};`);
  }
  const familias = tokens.type?.families ?? {};
  if (Object.keys(familias).length > 0) {
    linhas.push("  /* tipografia: famílias */");
    for (const [nome, valor] of Object.entries(familias)) {
      linhas.push(`  --font-${nome}: ${resolverAlias(valor)};`);
    }
  }
  return linhas;
}

export function gerarCss(tokens) {
  const temas = tokens.color.themes.map((t) => t.id);
  const [primeiro, ...outros] = temas;
  const claro = primeiro;
  const escuro = temas.find((id) => id === "escuro");
  const contraste = temas.find((id) => id === "alto-contraste");

  const saida = [
    "/*",
    " * GERADO por scripts/gerar-tokens.mjs a partir de tokens.json. Não edite este arquivo:",
    " * mude o tokens.json e rode `npm run tokens`. O teste de tokens falha se os dois divergirem.",
    " */",
    "",
    ":root {",
    ...linhasDoTema(tokens, claro, "  "),
    ...linhasSimples(tokens),
    "}",
    "",
  ];

  if (escuro) {
    saida.push(
      "/* Sem escolha da pessoa, o tema segue o sistema. */",
      "@media (prefers-color-scheme: dark) {",
      "  :root:not([data-tema]) {",
      ...linhasDoTema(tokens, escuro, "    "),
      "  }",
      "}",
      "",
    );
  }
  if (contraste) {
    saida.push(
      "@media (prefers-contrast: more) {",
      "  :root:not([data-tema]) {",
      ...linhasDoTema(tokens, contraste, "    "),
      "  }",
      "}",
      "",
    );
  }

  saida.push("/* Escolha explícita da pessoa (atributo data-tema no <html>). */");
  for (const id of [claro, ...outros]) {
    saida.push(`:root[data-tema="${id}"] {`, ...linhasDoTema(tokens, id, "  "), "}", "");
  }

  return saida.join("\n").replace(/\n+$/, "\n");
}

function principal() {
  const tokens = JSON.parse(readFileSync(CAMINHO_TOKENS_JSON, "utf8"));
  const css = gerarCss(tokens);
  if (process.argv.includes("--stdout")) {
    process.stdout.write(css);
    return;
  }
  writeFileSync(CAMINHO_TOKENS_CSS, css);
  console.log(`tokens.css gerado (${css.split("\n").length - 1} linhas).`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) principal();
