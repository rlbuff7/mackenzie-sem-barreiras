/**
 * Estrutura da tela "Orientação ao vivo" em index.html (lida no texto: a página depende do DOM) e as
 * garantias de privacidade e de silêncio, conferidas no código-fonte dos módulos da orientação.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../inicio/inicio.css", import.meta.url), "utf8");
const rotaTela = readFileSync(new URL("../inicio/rota-tela.ts", import.meta.url), "utf8");

/** Código sem comentários (os comentários citam as proibições de propósito). */
function semComentarios(texto: string): string {
  return texto.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const dirOrientacao = new URL("./", import.meta.url);
const MODULOS = [
  ...readdirSync(dirOrientacao).filter((n) => n.endsWith(".ts") && !n.endsWith(".test.ts")).map((n) => `../orientacao/${n}`),
  "../inicio/orientacao-tela.ts",
];
const codigo = new Map(MODULOS.map((m) => [m, semComentarios(readFileSync(new URL(m, import.meta.url), "utf8"))]));

// ---------- HTML ----------

test("botão 'Iniciar orientação ao vivo' fica na área da rota traçada, fora do bloco da simulação", () => {
  assert.match(html, /<button type="button" id="botao-orientacao-iniciar" class="rota__botao">Iniciar orientação ao vivo<\/button>/);
  const resultado = html.slice(html.indexOf('id="resultado-rota"'), html.indexOf("</main>"));
  assert.ok(resultado.includes('id="botao-orientacao-iniciar"'), "dentro do resultado (só aparece depois da rota)");
  const bloco = resultado.slice(resultado.indexOf('id="bloco-orientacao"'), resultado.indexOf('class="rota__simulacao"'));
  assert.ok(bloco.includes("botao-orientacao-iniciar"), "bloco próprio, antes da simulação");
  assert.ok(!bloco.includes("simular"));
});

test("a nota do botão diz que a posição não é guardada (e que vai ao servidor só para calcular)", () => {
  assert.match(html, /id="nota-orientacao-iniciar"[^>]*>[^<]*não é guardada/);
});

test("tela de orientação: seção rotulada, h2 focável, Parar sempre dentro dela", () => {
  assert.match(html, /<section id="tela-orientacao" class="ao-vivo" aria-labelledby="titulo-orientacao" hidden>/);
  assert.match(html, /<h2 id="titulo-orientacao"[^>]*tabindex="-1">Orientação ao vivo<\/h2>/);
  const tela = html.slice(html.indexOf('id="tela-orientacao"'), html.indexOf('id="anuncio-rota"'));
  assert.ok(tela.includes('id="botao-orientacao-parar"'));
  assert.match(tela, /<button type="button" id="botao-orientacao-parar" class="rota__botao[^"]*">Parar orientação<\/button>/);
});

test("avisos permanentes na tela de orientação, com os dois textos combinados", () => {
  const tela = html.slice(html.indexOf('id="tela-orientacao"'), html.indexOf('id="anuncio-rota"'));
  assert.ok(tela.includes("Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade."));
  assert.ok(tela.includes("Direções provisórias, calculadas pelo mapa aberto."));
  assert.match(tela, /class="ao-vivo__avisos" role="note"/);
});

test("estado: palavra + símbolo (aria-hidden); distância; última mensagem; status", () => {
  for (const id of ["estado-orientacao", "simbolo-orientacao", "rotulo-estado-orientacao", "distancia-orientacao", "mensagem-orientacao", "status-orientacao"]) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.match(html, /id="simbolo-orientacao"[^>]*aria-hidden="true"/);
  assert.match(html, /id="distancia-orientacao"[^>]*hidden/);
  assert.match(html, /id="status-orientacao"[^>]*hidden/);
});

test("aria-live: região assertive dedicada (alerta) e a polite que já existia; a mensagem visível não é live", () => {
  assert.match(html, /<p id="alerta-orientacao" class="oculto-visualmente" role="alert" aria-live="assertive" aria-atomic="true"><\/p>/);
  assert.match(html, /<p id="anuncio-rota" class="oculto-visualmente" role="status" aria-live="polite" aria-atomic="true">/);
  assert.equal(html.match(/aria-live="assertive"/g)?.length, 1, "só uma região assertive");
  for (const id of ["mensagem-orientacao", "estado-orientacao", "distancia-orientacao"]) {
    const abertura = html.match(new RegExp(`<[a-z]+ [^>]*id="${id}"[^>]*>`))![0];
    assert.ok(!abertura.includes("aria-live"), `${id} não é região viva (senão o leitor repete tudo a cada ciclo)`);
  }
});

test("alvos de toque: os botões da orientação usam .rota__botao (min-height 64 px)", () => {
  assert.match(css, /\.rota__botao\s*\{[^}]*min-height:\s*64px/);
  assert.ok(!/\.ao-vivo__parar\s*\{[^}]*min-height:\s*(?:[1-3]\d|4[0-3])px/.test(css));
});

test("estados com forma própria no CSS (✓ ✕ ◆ ★ vêm do texto; aqui borda diferente por estado, sem animação)", () => {
  for (const c of ["--na-rota", "--fora", "--sem-gps", "--chegou"]) assert.ok(css.includes(`.ao-vivo__estado${c}`), c);
  const bloco = css.slice(css.indexOf(".ao-vivo__estado {"), css.indexOf(".ao-vivo__distancia"));
  assert.ok(!/transition|animation/.test(bloco));
  assert.match(css, /\.ao-vivo__estado--sem-gps\s*\{[^}]*border-style:\s*dashed/);
});

test("o resultado, a lista e a tela se alternam por hidden com CSS que vale (display:flex não vence [hidden])", () => {
  assert.match(css, /\.rota__form\[hidden\][\s\S]*?\.ao-vivo\[hidden\][\s\S]*?\{\s*display:\s*none/);
});

test("a simulação some o botão de orientação ao vivo, e a orientação para a simulação", () => {
  assert.match(rotaTela, /blocoOrientacao\.hidden = true/);
  assert.match(rotaTela, /aoComecar:\s*\(\)\s*=>\s*\{[^}]*pararSimulacao\(\)/);
});

// ---------- privacidade (RNF04) ----------

const PROIBIDOS_DE_ARMAZENAMENTO = [/localStorage/, /sessionStorage/, /indexedDB/i, /document\.cookie/, /caches\./, /openDatabase/, /navigator\.storage/, /ArmazemFotos|armazem-fotos/, /FilaEnvio|fila-fotos/];
const PROIBIDOS_DE_SAIDA = [/console\./, /sendBeacon/, /XMLHttpRequest/, /WebSocket/, /new Image\(/, /EventSource/, /Blob\(/, /createObjectURL/, /download\s*=/, /\.postMessage\(/, /window\.open/, /location\.(href|assign|replace)/];

test("nenhum módulo da orientação grava a posição: sem localStorage, sessionStorage, IndexedDB, cookie nem cache", () => {
  assert.ok(MODULOS.length >= 4, `módulos varridos: ${MODULOS.join(", ")}`);
  for (const [modulo, texto] of codigo) {
    for (const re of PROIBIDOS_DE_ARMAZENAMENTO) assert.doesNotMatch(texto, re, `${modulo} usa ${re}`);
  }
});

test("nenhum módulo da orientação imprime nem envia a posição para outro lugar (console, beacon, XHR, WebSocket...)", () => {
  for (const [modulo, texto] of codigo) {
    for (const re of PROIBIDOS_DE_SAIDA) assert.doesNotMatch(texto, re, `${modulo} usa ${re}`);
  }
});

test("o único fetch da orientação é o POST montado por montarRequisicao (URL /api/orientacoes)", () => {
  const todos = [...codigo].flatMap(([m, t]) => [...t.matchAll(/\bfetch\s*\(([^)]*)\)/g)].map((x) => ({ m, arg: x[1]! })));
  assert.equal(todos.length, 1, JSON.stringify(todos));
  assert.equal(todos[0]!.m, "../inicio/orientacao-tela.ts");
  assert.match(todos[0]!.arg, /pedido\.url/);
  assert.match(codigo.get("../orientacao/requisicao.ts")!, /URL_ORIENTACOES\s*=\s*"\/api\/orientacoes"/);
  assert.match(codigo.get("../inicio/orientacao-tela.ts")!, /montarRequisicao\(/);
});

test("a tela não lê Ajustes do navegador por conta própria: voz e velocidade chegam por parâmetro", () => {
  const tela = codigo.get("../inicio/orientacao-tela.ts")!;
  assert.match(tela, /preferencias:\s*\(\)\s*=>\s*PreferenciasDeVoz/);
  assert.doesNotMatch(tela, /lerPreferenciasDeVoz|guardarPreferenciasDeVoz|guardarVozAtiva/);
});

test("ao parar: clearWatch, remove ouvintes, solta o Wake Lock, aborta o pedido e apaga trilha e recentes da memória", () => {
  const tela = codigo.get("../inicio/orientacao-tela.ts")!;
  const encerrar = tela.slice(tela.indexOf("function encerrarRecursos"), tela.indexOf("function aoSairDaPagina"));
  for (const trecho of ["clearWatch(", "clearInterval(", "removeEventListener(eventoBussola", 'removeEventListener("visibilitychange"', 'removeEventListener("pagehide"', ".abort()", ".release()", "trilha.limpar()", "recentes.limpar()", "bussola.limpar()", "fix = null", "marcador?.remove()"]) {
    assert.ok(encerrar.includes(trecho), `encerrarRecursos deve ter ${trecho}`);
  }
  assert.match(tela, /window\.addEventListener\("pagehide", aoSairDaPagina\)/, "sair da página também apaga tudo");
});

test("a posição só aparece no mapa (marcador em memória), animate:false, e dentro do campus", () => {
  const tela = codigo.get("../inicio/orientacao-tela.ts")!;
  assert.match(tela, /setView\(ll, 19, \{ animate: false \}\)/);
  assert.match(tela, /dentroDoCampus\(f\.lat, f\.lon\)/);
});

test("GPS pedido como combinado: watchPosition, alta precisão, sem cache (maximumAge 0); Wake Lock em try/catch; vibração em try/catch", () => {
  const tela = codigo.get("../inicio/orientacao-tela.ts")!;
  assert.match(tela, /watchPosition\([^)]*enableHighAccuracy:\s*true,\s*maximumAge:\s*0/);
  assert.match(tela, /async function pedirTrava[\s\S]*?try \{[\s\S]*?wakeLock\.request\("screen"\)[\s\S]*?\} catch/);
  assert.match(tela, /function vibrar[\s\S]*?try \{[\s\S]*?navigator\.vibrate[\s\S]*?\} catch/);
  assert.match(tela, /requestPermission/);
});

// ---------- silêncio ----------

test("SILÊNCIO: o código da tela não tem nenhuma frase de direção própria (só o que a API devolve)", () => {
  for (const [modulo, texto] of codigo) {
    const literais = [...texto.matchAll(/"([^"\n]*)"|`([^`\n]*)`/g)].map((m) => (m[1] ?? m[2] ?? "").toLowerCase());
    for (const frase of literais) {
      assert.doesNotMatch(frase, /\b(vire|siga em frente|caminho está|à sua (direita|esquerda|frente)|vá para|vire à)\b/, `${modulo}: "${frase}" parece direção inventada no cliente`);
    }
  }
});

test("SILÊNCIO: a fala vem de `textoParaDizer` (mensagem da API); o campo `direcao` não é lido pela tela", () => {
  const tela = codigo.get("../inicio/orientacao-tela.ts")!;
  assert.match(tela, /a\.textoParaDizer/);
  assert.doesNotMatch(tela, /\.direcao\b/);
  assert.doesNotMatch(codigo.get("../orientacao/apresentacao.ts")!, /corpo\.direcao|\.direcao\b/);
});

test("voz ligada: fala e NÃO escreve nas regiões aria-live (só cai na região se a fala falhar); voz desligada: só as regiões", () => {
  const tela = readFileSync(new URL("../inicio/orientacao-tela.ts", import.meta.url), "utf8");
  const dizer = tela.slice(tela.indexOf("function dizer"), tela.indexOf("// ---------- ciclo de envio"));
  assert.match(dizer, /if \(sintese && orientacao\.vozAtiva\(\)\) \{\s*regiaoUrgente\.textContent = "";\s*regiaoPolida\.textContent = "";/);
  assert.match(dizer, /if \(falhou\) naRegiao\(\)/);
  assert.match(dizer, /if \(!falou\) naRegiao\(\)/);
  assert.match(dizer, /\} else \{\s*naRegiao\(\);/);
  assert.equal((dizer.match(/anunciarUrgente\(|anunciarPolido\(/g) ?? []).length, 2, "só dentro de naRegiao");
});
