/**
 * Estrutura da tela de rota em index.html e do que o E2E confere em GET / (título, aviso de
 * segurança, nenhum "Relatar barreira"). Lido no texto: a página depende do DOM e não roda no node:test.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { PERFIS } from "./tipos.ts";

const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");
const tela = readFileSync(new URL("../inicio/rota-tela.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../inicio/inicio.css", import.meta.url), "utf8");

test("o que o E2E confere em GET / continua na página", () => {
  assert.ok(html.includes("Navegação Acessível no Campus"));
  assert.ok(html.includes("Aviso de segurança"));
  assert.ok(html.includes("Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade"));
  assert.ok(!html.includes("Relatar barreira"));
});

test("o botão desabilitado 'em novembro' saiu", () => {
  assert.ok(!html.includes("em novembro"));
});

test("De e Para são <select> nativos com <label> ligado pelo for", () => {
  for (const [id, texto] of [["rota-de", "De"], ["rota-para", "Para"]] as const) {
    assert.match(html, new RegExp(`<label for="${id}">${texto}</label>`));
    assert.match(html, new RegExp(`<select id="${id}"`));
  }
});

test("perfil: quatro rádios nativos em fieldset com legend; Cegueira é o primeiro e o padrão", () => {
  assert.match(html, /<fieldset[^>]*>\s*<legend>Perfil<\/legend>/);
  const valores = [...html.matchAll(/name="perfil" value="([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual(valores, ["cegueira", "baixa_visao", "cadeirante", "sem_restricao"]);
  assert.deepEqual(valores, [...PERFIS]);
  assert.match(html, /value="cegueira" checked/);
  assert.equal(html.match(/name="perfil"[^>]* checked/g)?.length, 1, "só um perfil marcado");
  const rotulos = [...html.matchAll(/name="perfil" value="[a-z_]+"(?: checked)? \/> ([^<]+)<\/label>/g)].map((m) => m[1]);
  assert.deepEqual(rotulos, ["Cegueira", "Baixa visão", "Cadeirante (evita escadas)", "Sem restrição"]);
  assert.ok(!html.includes("deficiencia_visual"), "o nome antigo não é mais enviado pela tela");
});

test("Traçar rota é o botão de envio do formulário, com 64 px no CSS", () => {
  assert.match(html, /<button type="submit" id="botao-tracar"[^>]*>Traçar rota<\/button>/);
  assert.match(css, /\.rota__botao\s*\{[^}]*min-height:\s*64px/);
});

test("resultado: título focável, lista ordenada <ol>, rótulo, distância e botão de voz", () => {
  assert.match(html, /<h2 id="titulo-resultado"[^>]*tabindex="-1"/);
  assert.match(html, /<ol id="instrucoes-rota"/);
  assert.ok(html.includes('id="rotulo-rota"') && html.includes('id="distancia-rota"'));
  assert.match(html, /<button type="button" id="botao-voz"[^>]*>Ouvir com a voz do app<\/button>/);
});

test("um único anúncio: só uma região aria-live, e o resultado não é live", () => {
  const vivos = html.match(/aria-live=|role="status"|role="alert"/g) ?? [];
  // #mapa-indisponivel (role=status, já existia) + #anuncio-rota (role=status + aria-live)
  assert.ok(html.includes('id="anuncio-rota" class="oculto-visualmente" role="status" aria-live="polite"'));
  const resultado = /<div id="resultado-rota"[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(!/aria-live|role="/.test(resultado), "o resultado não pode ser live (o foco no título já lê)");
  assert.ok(vivos.length >= 2);
});

test("tela: não lê a posição do aparelho, não fala sozinha e move o mapa sem animação", () => {
  assert.ok(!/geolocation|watchPosition/.test(tela));
  assert.ok(!/\.speak\(/.test(tela), "speak só dentro de voz.ts");
  assert.ok(!/deveFalarSozinho/.test(tela), "nenhum perfil fala sozinho: quem lê é o leitor de tela");
  const chamadas = [...tela.matchAll(/\.(setView|flyTo|panTo|fitBounds|invalidateSize)\(([^;]*)\);/g)];
  assert.ok(chamadas.length >= 2);
  for (const [linha] of chamadas) assert.match(linha, /animate:\s*false/);
});

test("a rota é desenhada com as cores do DS (mapa-rota, contorno branco) e sem animação no CSS", () => {
  assert.match(css, /\.mapa-rota-linha[^}]*var\(--mapa-rota\)/);
  assert.match(css, /\.mapa-rota-contorno[^}]*var\(--mapa-contorno\)/);
  const trecho = css.slice(css.indexOf(".rota {"));
  assert.ok(!/transition|animation|@keyframes/.test(trecho));
});

test("os erros do contrato viram palavra: 'Não encontrei um caminho seguro' é a frase do 404", async () => {
  const { MENSAGEM_SEM_ROTA } = await import("./interpretar.ts");
  assert.equal(MENSAGEM_SEM_ROTA, "Não encontrei um caminho seguro entre esses pontos.");
});

test("leitor de tela: foco no título, avisos antes da <ol> de instruções e 'Você está em' curto na região live", () => {
  const i = (s: string): number => html.indexOf(s);
  assert.ok(i('id="titulo-resultado"') < i('id="avisos-rota"') && i('id="avisos-rota"') < i('id="instrucoes-rota"'));
  assert.match(tela, /titulo\.focus\(\)/);
  assert.match(tela, /orientacao\.mudarDeTela\(telaDaRota\(rota\)\)/);
});

test("Ajustes: voz do app (select, velocidade, testar) com rótulo visível, dentro do painel, e tela usa as chaves novas", () => {
  const painel = /<div[^>]*id="painel-ajustes"[\s\S]*?<p id="nota-voz"[^>]*>/.exec(html)?.[0] ?? "";
  for (const id of ["seletor-voz", "seletor-velocidade", "botao-testar-voz"]) assert.ok(painel.includes(`id="${id}"`), id);
  assert.match(html, /<label for="seletor-voz">Voz do app<\/label>/);
  assert.match(html, /<label for="seletor-velocidade">/);
  assert.match(html, /Automática \(melhor disponível\)/);
  assert.match(tela, /voiceschanged|onvoiceschanged/);
});
