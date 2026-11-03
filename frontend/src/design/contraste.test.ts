/**
 * Contraste WCAG 2.2 AA dos pares de cores que o CSS e o código realmente usam, nos 3 temas.
 * Pedido da orientadora (27/10/2026): texto comum >= 4,5:1 (>= 3:1 só para texto grande, que aqui
 * não se usa: todo texto é cobrado em 4,5:1); borda de controle, foco, marcadores e linhas do mapa
 * >= 3:1. O tema alto contraste é mais exigente de propósito: texto >= 7:1.
 * Há ainda um teste que lê os CSS: cor de texto ou literal que não esteja nas listas abaixo derruba o teste.
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

/** color-mix(in srgb, frente pct%, fundo): o realce de hover e o de pressionado (--realce e --realce-ativo em estilos.css). */
function misturar(frente: Rgb, fundo: Rgb, pct: number): Rgb {
  return frente.map((v, i) => Math.round((v * pct) / 100 + fundo[i]! * (100 - pct) / 100)) as Rgb;
}

const BRANCO = "#ffffff"; // --sobre-aviso-forte (medicao.css)
const TILE_OSM = "#f2efe9"; // fundo típico do tile do OpenStreetMap (nos 3 temas: o mapa não escurece)
const LEAFLET_FUNDO_ATRIBUICAO = "#fcfcfb"; // branco a 80% sobre o tile (atribuição do Leaflet)
const LEAFLET_LINK = "#0078a8"; // cor do link da atribuição do Leaflet (padrão da biblioteca)
const LEAFLET_TEXTO = "#222222"; // texto do rótulo (tooltip) do Leaflet
const AZUL_CAMINHO_V0 = "#1f6fc2"; // azul da v0 (marcadores.css)
const AZUL_BOLINHA_SIMULACAO = "#1a5fb4"; // bolinha da simulação (rota-tela.ts)

/** "token@0.55" = o token com 55% de opacidade sobre o tile do mapa. */
function cor(tema: string, nome: string): Rgb {
  if (nome.includes("@")) {
    const [frente, opacidade] = nome.split("@") as [string, string];
    return misturar(cor(tema, frente), rgb(TILE_OSM), Number(opacidade) * 100);
  }
  if (nome.startsWith("#")) return rgb(nome);
  if (nome === "realce") return misturar(cor(tema, "primaria"), cor(tema, "superficie"), 10);
  if (nome === "realce-ativo") return misturar(cor(tema, "primaria"), cor(tema, "superficie"), 20);
  const t = tokens.color.tokens.find((x) => x.name === nome);
  assert.ok(t, `token ${nome} não existe`);
  return rgb(t.value[tema]!);
}

// [texto, fundo, onde]
export const TEXTO: [string, string, string][] = [
  ["texto", "fundo", "corpo da página"],
  ["texto", "superficie", "seções, campos, cartão de resultado, popup"],
  ["texto", "realce", "opção de perfil marcada e item em hover"],
  ["texto-suave", "fundo", "etiqueta, rodapé, notas fora de seção"],
  ["texto-suave", "superficie", "ajuda, notas e contador nas seções"],
  ["texto", "realce", "confirmação 'Destino escolhido' (borda primária, fundo do realce)"],
  ["primaria-escura", "fundo", "título h1, links e '← Início'"],
  ["primaria-escura", "superficie", "h2 e links nas seções, botão secundário, chip, botão Ativar voz"],
  ["primaria-escura", "realce", "botão secundário em hover"],
  ["primaria-escura", "realce-ativo", "botão secundário pressionado (:active)"],
  ["sobre-primaria", "perigo-escuro", "botão de perigo pressionado (:active) e em hover"],
  ["sobre-primaria", "primaria", "botão primário, link grande, Desativar voz (ligada), ícone enviado"],
  ["sobre-primaria", "primaria-escura", "aviso de segurança, hover, pular conteúdo"],
  ["sobre-primaria", "perigo", "botão de perigo, ícone recusado"],
  [BRANCO, "aviso-forte", "aviso de HTTPS (medicao.css)"],
  ["primaria", "superficie", "✓ enviado e ● boa (azul da marca, sem verde)"],
  ["primaria", "fundo", "texto de estado da foto enviada, fora de seção"],
  ["pendente", "superficie", "estado na fila, precisão média, ícone ◆"],
  ["pendente", "fundo", "foto na fila, fora de seção"],
  ["perigo", "superficie", "estado recusado, precisão ruim, mensagem de erro (✕)"],
  ["perigo", "fundo", "foto recusada, fora de seção"],
  ["mapa-contorno", "mapa-posicao", "letra do prédio no mapa (branco sobre azul-escuro)"],
  ["mapa-posicao", BRANCO, "símbolos + e − dos botões de zoom do mapa"],
  [LEAFLET_LINK, LEAFLET_FUNDO_ATRIBUICAO, "link da atribuição do mapa"],
  [LEAFLET_TEXTO, BRANCO, "rótulo (tooltip) de partida e chegada no mapa"],
];

// [frente, fundo, onde]
export const NAO_TEXTO: [string, string, string][] = [
  ["borda-controle", "superficie", "borda de campo, select, opção de perfil e barra de contagem"],
  ["borda-controle", "fundo", "contorno do segmento pendente (vazado) da barra de progresso"],
  ["alerta", "fundo", "anel de foco sobre a página"],
  ["alerta", "superficie", "anel de foco dentro de seções"],
  ["primaria", "superficie", "borda do botão secundário, do cartão e faixa da seção"],
  ["primaria", "fundo", "segmento feito da barra de progresso"],
  ["primaria", "realce", "borda da opção de perfil marcada"],
  ["primaria-escura", "fundo", "segmento atual da barra de progresso"],
  ["perigo", "superficie", "borda do cartão recusado e da mensagem de erro"],
  ["perigo", "fundo", "borda da confirmação de apagar"],
  ["pendente", "superficie", "borda tracejada do cartão na fila e do rótulo ORIGEM DOS DADOS"],
  ["mapa-posicao", TILE_OSM, "marcador você está aqui, limite do campus, ponto de controle e anel de foco no mapa"],
  ["mapa-posicao", BRANCO, "anel de foco dentro dos botões de zoom do mapa e da bola"],
  ["mapa-contorno", "mapa-posicao", "borda branca da bola de posição"],
  ["mapa-acessivel", TILE_OSM, "marcador acessível sobre o tile"],
  ["mapa-atencao", TILE_OSM, "marcador de atenção e contorno da área sem mapeamento"],
  ["mapa-rota", TILE_OSM, "rota sobre o tile"],
  ["mapa-rota@0.9", TILE_OSM, "linha da escada (v0) sobre o tile"],
  ["mapa-posicao", TILE_OSM, "anel do destino escolhido e foco do marcador de entrada, sobre o tile"],
  ["mapa-posicao", "mapa-contorno", "anel azul-escuro sobre o fundo branco do marcador escolhido"],
  ["mapa-acessivel", "mapa-contorno", "pino verde sobre o fundo branco do marcador escolhido"],
  ["mapa-rota", "mapa-posicao", "rota nunca se confunde com a bola de posição"],
  ["mapa-posicao@0.55", TILE_OSM, "trajeto da equipe sobre o tile"],
  ["mapa-posicao@0.95", TILE_OSM, "trajeto ao vivo sobre o tile"],
  [AZUL_CAMINHO_V0, TILE_OSM, "caminho da v0 (calçada) sobre o tile, sem transparência"],
  [AZUL_BOLINHA_SIMULACAO, TILE_OSM, "bolinha da simulação sobre o tile"],
  [BRANCO, AZUL_BOLINHA_SIMULACAO, "borda branca da bolinha da simulação"],
];

for (const { id: tema } of tokens.color.themes) {
  const minimoTexto = tema === "alto-contraste" ? 7 : 4.5;
  // No mapa e no Leaflet as cores não mudam com o tema (tile claro): vale 4,5:1 mesmo no alto contraste.
  const fixo = (f: string, b: string): boolean => f.startsWith("#") || b.startsWith("#") || f.startsWith("mapa-") || b.startsWith("mapa-");
  test(`contraste de texto no tema ${tema} (mínimo ${minimoTexto}:1; 4,5:1 no mapa)`, () => {
    const falhas = TEXTO.map(([f, b, onde]) => ({ f, b, onde, r: razao(cor(tema, f), cor(tema, b)), min: fixo(f, b) ? 4.5 : minimoTexto }))
      .filter((x) => x.r < x.min)
      .map((x) => `${x.f} sobre ${x.b} (${x.onde}): ${x.r.toFixed(2)}:1, mínimo ${x.min}:1`);
    assert.deepEqual(falhas, []);
  });

  test(`contraste de borda, foco, marcador e linha do mapa no tema ${tema} (mínimo 3:1)`, () => {
    const falhas = NAO_TEXTO.map(([f, b, onde]) => ({ f, b, onde, r: razao(cor(tema, f), cor(tema, b)) }))
      .filter((x) => x.r < 3)
      .map((x) => `${x.f} sobre ${x.b} (${x.onde}): ${x.r.toFixed(2)}:1`);
    assert.deepEqual(falhas, []);
  });
}

// ---------- o que os CSS usam tem de estar nas listas acima ----------

const ARQUIVOS_CSS = ["../estilos.css", "../inicio/inicio.css", "../medicao/medicao.css", "../mapa/marcadores.css", "./movimento.css"];
const css = ARQUIVOS_CSS.map((a) => readFileSync(new URL(a, import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "")).join("\n");

/** Estilos do escopo antigo (formulário de relato), sem uso nas páginas atuais: fora da auditoria. */
const SELETORES_ANTIGOS = /(item-barreira|lista-barreiras|formulario-secao|severidade-opcao|ponto-selecionado|marcador--|icone-barreira|cabecalho|\.contador|status-envio|rodape)/;

test("toda cor de texto dos CSS (color: var(--token)) está em um par da lista TEXTO", () => {
  const usados = new Set<string>();
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (SELETORES_ANTIGOS.test(m[1]!)) continue;
    for (const c of m[2]!.matchAll(/(?<![-\w])color:\s*var\(--([a-z-]+)\)/g)) usados.add(c[1]!);
  }
  const cobertos = new Set(TEXTO.map(([f]) => f));
  const faltam = [...usados].filter((t) => !(t === "sobre-aviso-forte" ? cobertos.has(BRANCO) : cobertos.has(t)));
  assert.deepEqual(faltam, [], "texto com cor sem par de contraste testado");
});

test("os CSS não têm cor literal fora das que estão na auditoria", () => {
  const permitidas = new Set([AZUL_CAMINHO_V0, "#ffffff", "#fff"]);
  const soltas = [...css.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => m[0].toLowerCase()).filter((c) => !permitidas.has(c));
  assert.deepEqual(soltas, []);
});

test("a cor do caminho da v0 no CSS é a testada, sem transparência", () => {
  assert.match(css, new RegExp(`\\.mapa-caminho-calcada\\s*\\{[^}]*stroke:\\s*${AZUL_CAMINHO_V0}`));
  assert.doesNotMatch(/\.mapa-caminho-calcada\s*\{[^}]*stroke-opacity/.exec(css)?.[0] ?? "", /stroke-opacity/);
});
