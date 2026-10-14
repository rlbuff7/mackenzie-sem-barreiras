/**
 * Regras do movimento conferidas no texto do CSS (não dá para ver animação em teste):
 * tudo opt-in, nada acima de 300 ms, sem loop, sem bounce, nunca no mapa nem em leitura ao vivo.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const RAIZ_SRC = fileURLToPath(new URL("..", import.meta.url));

function ler(caminho: string): string {
  return readFileSync(join(RAIZ_SRC, caminho), "utf8");
}

function semComentarios(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function todosOsCss(pasta = RAIZ_SRC): string[] {
  const achados: string[] = [];
  for (const nome of readdirSync(pasta)) {
    const caminho = join(pasta, nome);
    if (statSync(caminho).isDirectory()) achados.push(...todosOsCss(caminho));
    else if (nome.endsWith(".css")) achados.push(caminho);
  }
  return achados;
}

/** Texto do bloco `{ ... }` que começa na abertura `cabecalho {`, com as chaves balanceadas. */
function bloco(css: string, cabecalho: string): { dentro: string; fora: string } {
  const inicio = css.indexOf(cabecalho);
  assert.ok(inicio >= 0, `bloco ausente: ${cabecalho}`);
  let fundo = 0;
  for (let i = inicio + cabecalho.length - 1; i < css.length; i++) {
    if (css[i] === "{") fundo++;
    if (css[i] === "}" && --fundo === 0) {
      return {
        dentro: css.slice(inicio + cabecalho.length, i),
        fora: css.slice(0, inicio) + css.slice(i + 1),
      };
    }
  }
  throw new Error(`bloco sem fechamento: ${cabecalho}`);
}

const OPT_IN = "@media (prefers-reduced-motion: no-preference) {";
const GUARDA = ':root:not([data-movimento="reduzido"])';
const movimentoCss = semComentarios(ler("design/movimento.css"));
const { dentro: optIn, fora: foraDoOptIn } = bloco(movimentoCss, OPT_IN);

test("estilos.css importa o movimento.css (as duas páginas carregam o estilos.css)", () => {
  assert.match(semComentarios(ler("estilos.css")), /@import "\.\/design\/movimento\.css";/);
});

test("fora do opt-in não há transição, animação, @starting-style nem @view-transition (só 'none')", () => {
  const resto = foraDoOptIn.replace(/(transition|animation)\s*:\s*none\s*(!important)?\s*;/g, "");
  assert.doesNotMatch(resto, /transition|animation|@starting-style|@view-transition|@keyframes|translate|scale\(/);
});

test("todo seletor do opt-in leva a guarda de data-movimento (ou é o desligamento explícito)", () => {
  const semAtRules = optIn
    .replace(/@view-transition\s*\{[^}]*\}/g, "")
    .replace(/@starting-style\s*\{/g, "")
    .replace(/\{[^{}]*\}/g, "{}");
  const seletores = semAtRules
    .split("{}")
    .map((s) => s.replace(/[{}]/g, "").trim())
    .filter(Boolean)
    .flatMap((s) => s.split(","))
    .map((s) => s.trim())
    .filter(Boolean);
  assert.ok(seletores.length > 5, "esperava vários seletores no opt-in");
  for (const s of seletores) {
    assert.ok(
      s.startsWith(GUARDA) || s.startsWith(':root[data-movimento="reduzido"]') || s.startsWith("::view-transition"),
      `seletor sem a guarda de movimento reduzido: ${s}`,
    );
  }
});

test("a troca de página é só crossfade: navigation auto, sem @keyframes, sem deslocamento", () => {
  assert.match(optIn, /@view-transition\s*\{\s*navigation:\s*auto;\s*\}/);
  assert.doesNotMatch(movimentoCss, /@keyframes/);
  const pseudo = optIn.slice(optIn.indexOf("::view-transition"), optIn.indexOf(":root:not("));
  assert.doesNotMatch(pseudo.replace(/:root\[data-movimento="reduzido"\][^{]*\{[^}]*\}/g, ""), /transform|translate/);
});

test("com 'Reduzir animações' ligado, a troca de página também fica instantânea", () => {
  assert.match(optIn, /:root\[data-movimento="reduzido"\]::view-transition-(old|new|group)\([^)]*\)[^{]*\{[^}]*animation:\s*none/);
});

test("nenhum CSS do projeto usa transition: all, loop (infinite) ou @keyframes", () => {
  for (const arquivo of todosOsCss()) {
    const css = semComentarios(readFileSync(arquivo, "utf8"));
    if (arquivo.includes("node_modules")) continue;
    assert.doesNotMatch(css, /transition\s*:\s*all\b/, `${arquivo}: transition: all`);
    assert.doesNotMatch(css, /transition-property\s*:\s*all\b/, `${arquivo}: transition-property: all`);
    assert.doesNotMatch(css, /infinite/, `${arquivo}: animação em loop`);
    assert.doesNotMatch(css, /@keyframes/, `${arquivo}: @keyframes`);
  }
});

test("durações: só tokens mov-*, e nenhum token passa de 300 ms", () => {
  assert.doesNotMatch(optIn, /\d(ms|s)\b/, "duração solta no movimento.css: use var(--mov-*)");
  const tokens = JSON.parse(ler("design/tokens.json")) as {
    movimento: { tokens: { name: string; value: string }[] };
  };
  const duracoes = tokens.movimento.tokens.filter((t) => /^\d+ms$/.test(t.value));
  assert.ok(duracoes.length >= 4, "esperava toque, painel, painel-saida e pagina");
  for (const t of duracoes) {
    assert.ok(parseInt(t.value, 10) <= 300, `${t.name} passa de 300 ms`);
  }
  const por = (nome: string) => parseInt(tokens.movimento.tokens.find((t) => t.name === nome)?.value ?? "0", 10);
  assert.equal(por("mov-toque"), 100);
  assert.equal(por("mov-painel"), 200);
  assert.ok(por("mov-painel-saida") < por("mov-painel"), "a saída tem de ser mais rápida que a entrada");
  assert.equal(por("mov-pagina"), 250);
});

test("a curva é de saída forte e sem bounce (y entre 0 e 1) e ninguém usa ease-in", () => {
  const tokens = JSON.parse(ler("design/tokens.json")) as {
    movimento: { tokens: { name: string; value: string }[] };
  };
  const curva = tokens.movimento.tokens.find((t) => t.name === "mov-curva")?.value ?? "";
  const m = /^cubic-bezier\(\s*([\d.]+),\s*([\d.-]+),\s*([\d.]+),\s*([\d.-]+)\s*\)$/.exec(curva);
  assert.ok(m, `mov-curva inesperada: ${curva}`);
  const [, , y1, , y2] = m.map(Number) as [number, number, number, number, number];
  assert.ok(y1 >= 0 && y1 <= 1 && y2 >= 0 && y2 <= 1, "y fora de 0..1 faz bounce");
  for (const arquivo of todosOsCss()) {
    assert.doesNotMatch(semComentarios(readFileSync(arquivo, "utf8")), /ease-in\b/, `${arquivo}: ease-in`);
  }
});

test("só opacity, transform e cores animam, e o foco nunca entra na lista", () => {
  const listas = [...optIn.matchAll(/transition\s*:\s*([^;]+);/g)].map((m) => m[1]!);
  assert.ok(listas.length > 0);
  for (const lista of listas) {
    for (const item of lista.split(",")) {
      const propriedade = item.trim().split(/\s+/)[0]!;
      assert.ok(
        ["opacity", "transform", "background-color", "border-color", "color"].includes(propriedade),
        `propriedade não permitida na transição: ${propriedade}`,
      );
    }
  }
  assert.doesNotMatch(optIn, /outline/);
  assert.doesNotMatch(optIn, /\b(width|height|margin|padding|top|left|right|bottom)\s*:/, "layout nunca anima");
});

test("o movimento nunca toca mapa, posição, rumo, rota, avisos nem leituras ao vivo (o BOTÃO da contagem pode, o número e a barra não)", () => {
  const proibidos = /leaflet|mapa|marcador|posicao|rumo|rota|precisao|contagem-valor|barra-contagem|painel-contagem|aviso|status|leitura|envio|bussola|segmento/i;
  const seletores = optIn
    .replace(/\{[^{}]*\}/g, "{}")
    .split("{}")
    .map((s) => s.replace(/@starting-style\s*\{/, "").trim());
  for (const s of seletores) {
    assert.doesNotMatch(s, proibidos, `seletor de movimento em área proibida: ${s}`);
  }
});

test("o mapa do Leaflet nunca anima: rede de segurança sempre ligada, fora do opt-in", () => {
  assert.match(
    foraDoOptIn,
    /\.leaflet-container,\s*\.leaflet-container \*\s*\{[^}]*transition:\s*none\s*!important;[^}]*animation:\s*none\s*!important/,
  );
});

test("estilos.css não tem mais o 'matar tudo' (* { transition: none }) do movimento reduzido", () => {
  assert.doesNotMatch(semComentarios(ler("estilos.css")), /\*\s*\{[^}]*transition:\s*none/);
});

test("todo :hover está dentro de @media (hover: hover) and (pointer: fine)", () => {
  const PORTA = "@media (hover: hover) and (pointer: fine) {";
  for (const arquivo of ["estilos.css", "inicio/inicio.css", "medicao/medicao.css"]) {
    let css = semComentarios(ler(arquivo));
    while (css.includes(PORTA)) css = bloco(css, PORTA).fora;
    assert.doesNotMatch(css, /:hover/, `${arquivo}: :hover fora da media (hover: hover) and (pointer: fine)`);
  }
});

test("o anel de foco continua em alerta, sem transição", () => {
  const estilos = semComentarios(ler("estilos.css"));
  assert.match(estilos, /:focus-visible\s*\{[^}]*outline:\s*var\(--linha-foco\) solid var\(--alerta\)/);
});
