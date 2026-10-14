/**
 * Contraste WCAG dos pares de cores que o CSS realmente usa, nos 3 temas.
 * Regra do Design System: texto >= 4,5:1 (claro, escuro) e >= 7:1 (alto contraste);
 * borda de controle, foco e marcadores >= 3:1.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

type Rgb = [number, number, number];
const tokens = JSON.parse(readFileSync(new URL("./tokens.json", import.meta.url), "utf8")) as {
  color: { themes: { id: string }[]; tokens: { name: string; value: Record<string, string> }[] };
};

function rgb(hex: string): Rgb {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  assert.ok(m, `cor ${hex} não é #rrggbb`);
  return [0, 2, 4].map((i) => parseInt(m[1]!.slice(i, i + 2), 16)) as Rgb;
}

function luminancia([r, g, b]: Rgb): number {
  const [lr, lg, lb] = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as Rgb;
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

function razao(a: Rgb, b: Rgb): number {
  const [claro, escuro] = [luminancia(a), luminancia(b)].sort((x, y) => y - x) as [number, number];
  return (claro + 0.05) / (escuro + 0.05);
}

/** color-mix(in srgb, frente pct%, fundo): o realce de hover (--realce em estilos.css). */
function misturar(frente: Rgb, fundo: Rgb, pct: number): Rgb {
  return frente.map((v, i) => Math.round((v * pct) / 100 + fundo[i]! * (100 - pct) / 100)) as Rgb;
}

const BRANCO = "#ffffff"; // --sobre-aviso-forte (medicao.css)
const TILE_OSM = "#f2efe9"; // fundo típico do tile do OpenStreetMap

function cor(tema: string, nome: string): Rgb {
  if (nome === BRANCO) return rgb(BRANCO);
  if (nome === TILE_OSM) return rgb(TILE_OSM);
  if (nome === "realce") return misturar(cor(tema, "primaria"), cor(tema, "superficie"), 10);
  const t = tokens.color.tokens.find((x) => x.name === nome);
  assert.ok(t, `token ${nome} não existe`);
  return rgb(t.value[tema]!);
}

// [texto, fundo, onde]
const TEXTO: [string, string, string][] = [
  ["texto", "fundo", "corpo da página"],
  ["texto", "superficie", "seções e campos"],
  ["texto-suave", "fundo", "etiqueta, rodapé"],
  ["texto-suave", "superficie", "ajuda e notas nas seções"],
  ["primaria-escura", "fundo", "título h1"],
  ["primaria-escura", "superficie", "h3 e links nas seções, botão secundário"],
  ["primaria-escura", "realce", "botão secundário em hover"],
  ["texto", "realce", "item de lista em hover"],
  ["sobre-primaria", "primaria", "botão primário e link grande"],
  ["sobre-primaria", "primaria-escura", "aviso de segurança, hover, pular conteúdo"],
  ["sobre-primaria", "perigo", "botão de perigo"],
  [BRANCO, "aviso-forte", "aviso de HTTPS (medicao.css)"],
];

// [frente, fundo, onde]
const NAO_TEXTO: [string, string, string][] = [
  ["borda-controle", "superficie", "borda de campo e select"],
  ["alerta", "fundo", "anel de foco sobre a página"],
  ["alerta", "superficie", "anel de foco dentro de seções"],
  ["primaria", "superficie", "borda do botão secundário e faixa da seção"],
  ["perigo", "superficie", "borda da confirmação de apagar"],
  ["mapa-posicao", TILE_OSM, "marcador você está aqui sobre o tile"],
  ["mapa-acessivel", TILE_OSM, "marcador acessível sobre o tile"],
  ["mapa-atencao", TILE_OSM, "marcador de atenção sobre o tile"],
  ["mapa-rota", TILE_OSM, "rota sobre o tile"],
];

for (const { id: tema } of tokens.color.themes) {
  const minimoTexto = tema === "alto-contraste" ? 7 : 4.5;
  test(`contraste de texto no tema ${tema} (mínimo ${minimoTexto}:1)`, () => {
    const falhas = TEXTO.map(([f, b, onde]) => ({ f, b, onde, r: razao(cor(tema, f), cor(tema, b)) }))
      .filter((x) => x.r < minimoTexto)
      .map((x) => `${x.f} sobre ${x.b} (${x.onde}): ${x.r.toFixed(2)}:1`);
    assert.deepEqual(falhas, []);
  });

  test(`contraste de borda, foco e marcador no tema ${tema} (mínimo 3:1)`, () => {
    const falhas = NAO_TEXTO.map(([f, b, onde]) => ({ f, b, onde, r: razao(cor(tema, f), cor(tema, b)) }))
      .filter((x) => x.r < 3)
      .map((x) => `${x.f} sobre ${x.b} (${x.onde}): ${x.r.toFixed(2)}:1`);
    assert.deepEqual(falhas, []);
  });
}
