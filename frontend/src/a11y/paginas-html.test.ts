/**
 * Acessibilidade estrutural das DUAS páginas (index.html e medicao.html), conferida no HTML e no código
 * (a página depende do DOM e não roda no node:test). Pedido da orientadora (27/10/2026): WCAG AA, leitor de
 * tela (TalkBack/VoiceOver) informado a cada mudança de tela, perfis, botão "Ativar voz" como 1º controle.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { ETAPAS } from "../medicao/fluxo.ts";
import { TELA_ESCOLHER } from "../inicio/telas.ts";
import { tituloDaPagina } from "./orientacao.ts";

const ler = (caminho: string): string => readFileSync(new URL(caminho, import.meta.url), "utf8");
const PAGINAS = [
  { nome: "index.html", html: ler("../../index.html"), regiao: "anuncio-rota", ts: ler("../inicio/pagina.ts") },
  { nome: "medicao.html", html: ler("../../medicao.html"), regiao: "anuncio-etapa", ts: ler("../medicao/pagina.ts") },
];

/** O conteúdo de texto visível de um trecho de HTML (sem tags). */
const semTags = (t: string): string => t.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();

test("index.html: o título inicial segue '<Tela> · Navegação Acessível no Campus'", () => {
  const html = PAGINAS[0]!.html;
  assert.ok(html.includes(`<title>${tituloDaPagina(TELA_ESCOLHER.nome)}</title>`));
});

test("medicao.html: o título estático fica como o E2E confere; a página troca o título a cada etapa ao carregar", () => {
  const { html, ts } = PAGINAS[1]!;
  assert.ok(html.includes("<title>Medição de GPS — Mackenzie</title>"), "backend/scripts/ponta_a_ponta.py confere este texto");
  assert.match(ts, /orientacao\.mudarDeTela\(telaAtualDaEtapa\(/, "irParaEtapa põe o título e anuncia");
  assert.match(ts, /irParaEtapa\(etapaInicial\(/, "a etapa inicial também põe o título");
  assert.equal(tituloDaPagina(`Etapa 2 de 3: Medir o ponto`), "Etapa 2 de 3: Medir o ponto · Navegação Acessível no Campus");
  assert.equal(ETAPAS.length, 3);
});

for (const { nome, html, regiao, ts } of PAGINAS) {
  test(`${nome}: html lang pt-BR, viewport sem bloquear o zoom`, () => {
    assert.match(html, /<html lang="pt-BR">/);
    const viewport = /<meta\s+name="viewport"\s+content="([^"]*)"/.exec(html)?.[1] ?? "";
    assert.ok(viewport.includes("width=device-width"));
    assert.ok(!/user-scalable\s*=\s*(no|0)/.test(viewport), "não pode travar o zoom (WCAG 1.4.4)");
    assert.ok(!/maximum-scale\s*=\s*1(\.0)?\b/.test(viewport), "maximum-scale=1 trava o zoom");
  });

  test(`${nome}: o primeiro item é o link 'Pular para o conteúdo' e o destino existe`, () => {
    const corpo = html.slice(html.indexOf("<body"));
    const primeiroLink = /<a\b[^>]*>[\s\S]*?<\/a>/.exec(corpo)![0];
    assert.match(primeiroLink, /class="pular-conteudo"/);
    assert.match(primeiroLink, /href="#conteudo-principal"/);
    assert.equal(semTags(primeiroLink), "Pular para o conteúdo");
    assert.match(html, /<main id="conteudo-principal"[^>]*tabindex="-1"/);
  });

  test(`${nome}: landmarks coerentes: um header, um nav, um main e um footer`, () => {
    const contar = (tag: string): number => html.match(new RegExp(`<${tag}[\\s>]`, "g"))?.length ?? 0;
    assert.equal(contar("main"), 1, "main");
    assert.equal(contar("nav"), 1, "nav");
    assert.ok(contar("header") >= 1, "header");
    assert.ok(contar("footer") >= 1, "footer");
    assert.match(html, /<nav aria-label="[^"]+"/, "o nav precisa de nome");
    // o main vem depois do header (ordem de leitura lógica)
    assert.ok(html.indexOf("<header") < html.indexOf("<main"));
  });

  test(`${nome}: 'Ativar voz' é o primeiro botão da página, com aria-pressed e nota ligada por aria-describedby`, () => {
    const botoes = [...html.matchAll(/<button\b[^>]*>/g)].map((m) => m[0]);
    assert.match(botoes[0]!, /id="botao-voz-tela"/, "o primeiro <button> é o da voz");
    assert.match(botoes[0]!, /type="button"/);
    assert.match(botoes[0]!, /aria-pressed="false"/);
    assert.match(botoes[0]!, /aria-describedby="nota-voz-tela"/);
    assert.match(html, /<button[^>]*id="botao-voz-tela"[^>]*>Ativar voz<\/button>/);
    assert.match(html, /<p id="nota-voz-tela"/);
    // vem antes de qualquer campo e de qualquer outro controle
    const posVoz = html.indexOf('id="botao-voz-tela"');
    for (const outro of ['id="botao-ajustes"', "<select", "<input", "<form"]) {
      const pos = html.indexOf(outro);
      assert.ok(pos === -1 || posVoz < pos, `Ativar voz deve vir antes de ${outro}`);
    }
    assert.match(html, /<header/);
    assert.ok(html.indexOf("<header") < posVoz, "o botão fica dentro do header");
  });

  test(`${nome}: uma região aria-live polite para a mudança de tela, vazia e escondida só da vista`, () => {
    const tag = new RegExp(`<p[^>]*id="${regiao}"[^>]*>`).exec(html)?.[0] ?? "";
    assert.ok(tag, `falta #${regiao}`);
    assert.match(tag, /role="status"/);
    assert.match(tag, /aria-live="polite"/);
    assert.match(tag, /oculto-visualmente/);
    assert.equal(html.match(new RegExp(`id="${regiao}"`, "g"))?.length, 1);
    assert.match(ts, new RegExp(`regiao: "${regiao}"`), "a orientação escreve nesta região");
    assert.match(ts, /botao: "botao-voz-tela", nota: "nota-voz-tela"/);
  });

  test(`${nome}: todo botão tem nome acessível (texto ou aria-label)`, () => {
    const botoes = [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)];
    assert.ok(botoes.length >= 5);
    const sem = botoes.filter((b) => semTags(b[2]!) === "" && !/aria-label(ledby)?="[^"]+"/.test(b[1]!)).map((b) => b[1]);
    assert.deepEqual(sem, []);
    for (const b of botoes) assert.match(b[1]!, /type="(button|submit)"/, `botão sem type: ${b[1]}`);
  });

  test(`${nome}: todo campo (input, select, textarea) tem rótulo: <label for>, label que envolve ou aria-label`, () => {
    const campos = [...html.matchAll(/<(input|select|textarea)\b([^>]*)>/g)];
    assert.ok(campos.length >= 3);
    const semRotulo: string[] = [];
    for (const [, , attrs] of campos) {
      if (/type="hidden"/.test(attrs!)) continue;
      const id = /\bid="([^"]+)"/.exec(attrs!)?.[1];
      const comFor = id ? new RegExp(`<label[^>]*for="${id}"`).test(html) : false;
      const comAria = /aria-label(ledby)?="[^"]+"/.test(attrs!);
      const envolvido = id ? new RegExp(`<label[^>]*>(?:(?!</label>)[\\s\\S])*id="${id}"`).test(html) : /<label[^>]*>[^<]*<input/.test(html);
      if (!comFor && !comAria && !envolvido) semRotulo.push(attrs!.trim());
    }
    assert.deepEqual(semRotulo, []);
  });

  test(`${nome}: o mapa é uma região com nome descritivo; sem imagem sem alt; sem tabindex positivo`, () => {
    const mapa = /<div\s+id="mapa-(?:campus|medicao)"[\s\S]*?>/.exec(html)?.[0] ?? "";
    assert.match(mapa, /role="region"/);
    const rotulo = /aria-label="([^"]+)"/.exec(mapa)?.[1] ?? "";
    assert.ok(rotulo.length >= 40, "o nome do mapa descreve o que ele mostra");
    assert.ok(/referência visual/.test(rotulo) || /referência visual/.test(html));
    for (const img of html.match(/<img\b[^>]*>/g) ?? []) assert.match(img, /\balt=/, img);
    assert.ok(!/tabindex="[1-9]/.test(html), "tabindex positivo bagunça a ordem de foco");
  });

  test(`${nome}: o código do mapa não captura o foco (keyboard:false), põe zoom e atribuição em português`, () => {
    assert.match(ts, /\.\.\.OPCOES_DE_FOCO_DO_MAPA/);
    assert.match(ts, /\.\.\.OPCOES_DO_ZOOM/);
    assert.match(ts, /setPrefix\(PREFIXO_DA_ATRIBUICAO\)/);
  });

  test(`${nome}: nenhum texto de interface fala em 'clique' (toque/ação), e links têm texto`, () => {
    assert.ok(!/clique/i.test(semTags(html)));
    const links = [...html.matchAll(/<a\b[^>]*>([\s\S]*?)<\/a>/g)];
    for (const l of links) assert.notEqual(semTags(l[1]!), "", "link sem texto");
  });
}

test("ações do mapa na medição têm equivalente em botão com nome (Centralizar em mim, Ver o campus todo)", () => {
  const html = PAGINAS[1]!.html;
  assert.match(html, /<button[^>]*id="botao-centralizar"[^>]*>Centralizar em mim<\/button>/);
  assert.match(html, /<button[^>]*id="botao-ver-campus"[^>]*>Ver o campus todo<\/button>/);
});

test("zoom e atribuição do mapa: textos em português", async () => {
  const { OPCOES_DO_ZOOM, PREFIXO_DA_ATRIBUICAO, OPCOES_DE_FOCO_DO_MAPA } = await import("../mapa/acessibilidade.ts");
  assert.equal(OPCOES_DO_ZOOM.zoomInTitle, "Aproximar o mapa");
  assert.equal(OPCOES_DO_ZOOM.zoomOutTitle, "Afastar o mapa");
  assert.ok(!/JavaScript library/.test(PREFIXO_DA_ATRIBUICAO));
  assert.equal(OPCOES_DE_FOCO_DO_MAPA.keyboard, false);
});

test("alvos de toque: botões de ação com >= 44 px no CSS e o 'Ativar voz' com 64 px", () => {
  const estilos = ler("../estilos.css");
  assert.match(estilos, /\.botao\s*\{[^}]*min-height:\s*var\(--alvo-toque\)/);
  assert.match(estilos, /\.botao-voz\s*\{[^}]*min-height:\s*64px/);
  const marcadores = ler("../mapa/marcadores.css");
  assert.match(marcadores, /\.leaflet-bar a[\s\S]*?width:\s*44px;[\s\S]*?height:\s*44px/);
  const tokens = JSON.parse(ler("../design/tokens.json")) as { tamanho: { tokens: { name: string; value: string }[] } };
  const alvo = tokens.tamanho.tokens.find((t) => t.name === "alvo-toque");
  assert.ok(alvo && parseInt(alvo.value, 10) >= 44, "token alvo-toque >= 44 px");
});

test("o estado da voz nunca é só cor: o texto do botão muda e o aria-pressed acompanha", () => {
  const estilos = ler("../estilos.css");
  assert.match(estilos, /\.botao-voz\[aria-pressed="true"\]/);
});
