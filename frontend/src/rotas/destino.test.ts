import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  ESPERA_ANUNCIO_BUSCA_MS, confirmacaoDeDestino, criarDebounce, escolherDestino, filtrarPontos,
  normalizarTexto, rotuloDoMarcador, textoContagem,
} from "./destino.ts";
import type { PontoInteresse } from "./tipos.ts";

const ponto = (id: number, nome: string, tipo = "entrada"): PontoInteresse => ({
  id, tipo, nome, descricao: null, acessivel: null, fonte_verificacao: "imagem", tem_no: true, latitude: -23.54, longitude: -46.65,
});
const PONTOS = [ponto(1, "Entrada do Prédio 29"), ponto(2, "Entrada do Prédio 9"), ponto(3, "Portão da rua Piauí", "portao"), ponto(4, "Entrada do Prédio 29 (lateral)")];

test("normalizarTexto tira acento, caixa e espaços sobrando", () => {
  assert.equal(normalizarTexto("  Prédio   29 "), "predio 29");
  assert.equal(normalizarTexto("PIAUÍ"), "piaui");
  assert.equal(normalizarTexto("Portão"), "portao");
});

test("'predio 29' acha 'Prédio 29' (sem acento e sem diferença de maiúsculas)", () => {
  assert.deepEqual(filtrarPontos(PONTOS, "predio 29").map((p) => p.id), [1, 4]);
  assert.deepEqual(filtrarPontos(PONTOS, "PRÉDIO 29").map((p) => p.id), [1, 4]);
});

test("consulta vazia ou só espaços devolve todos; sem acerto devolve vazio", () => {
  assert.equal(filtrarPontos(PONTOS, "").length, 4);
  assert.equal(filtrarPontos(PONTOS, "   ").length, 4);
  assert.deepEqual(filtrarPontos(PONTOS, "biblioteca"), []);
});

test("as palavras podem vir em qualquer ordem, e 'piaui' acha o portão com acento", () => {
  assert.deepEqual(filtrarPontos(PONTOS, "29 predio").map((p) => p.id), [1, 4]);
  assert.deepEqual(filtrarPontos(PONTOS, "piaui").map((p) => p.id), [3]);
});

test("a contagem fala no singular e no plural, e diz quando não achou nada", () => {
  assert.equal(textoContagem(3), "3 lugares encontrados");
  assert.equal(textoContagem(1), "1 lugar encontrado");
  assert.equal(textoContagem(0), "Nenhum lugar encontrado");
});

test("escolherDestino: frase de confirmação e oferta de origem só com 'De' vazio", () => {
  const a = escolherDestino(PONTOS, 1, null);
  assert.equal(a?.confirmacao, "Destino escolhido: Entrada do Prédio 29");
  assert.equal(a?.oferecerOrigem, true);
  assert.equal(escolherDestino(PONTOS, 1, 3)?.oferecerOrigem, false);
  assert.equal(confirmacaoDeDestino("X"), "Destino escolhido: X");
});

test("escolherDestino ignora id que não está na lista de destinos", () => {
  assert.equal(escolherDestino(PONTOS, 99, null), null);
});

test("o rótulo do marcador tem o nome e diz o que o toque faz", () => {
  assert.equal(rotuloDoMarcador("Entrada do Prédio 29"), "Entrada do Prédio 29. Tocar para escolher como destino");
});

test("debounce: várias chamadas seguidas viram uma ação só, depois da espera", () => {
  const fila: { fn: () => void; ms: number; id: number }[] = [];
  let n = 0;
  const d = criarDebounce(() => { n++; }, ESPERA_ANUNCIO_BUSCA_MS, {
    agendar: (fn, ms) => { const id = fila.length + 1; fila.push({ fn, ms, id }); return id; },
    cancelar: (id) => { const i = fila.findIndex((f) => f.id === id); if (i >= 0) fila.splice(i, 1); },
  });
  d.chamar(); d.chamar(); d.chamar();
  assert.equal(fila.length, 1);
  assert.equal(fila[0]!.ms, 500);
  fila.shift()!.fn();
  assert.equal(n, 1);
  d.chamar(); d.cancelar();
  assert.equal(fila.length, 0);
});

// ---------- HTML e CSS (a tela depende do DOM e não roda no node:test) ----------
const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");
const tela = readFileSync(new URL("../inicio/rota-tela.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../inicio/inicio.css", import.meta.url), "utf8");
const cssMapa = readFileSync(new URL("../mapa/marcadores.css", import.meta.url), "utf8");

test("busca: <input type=search> com <label> ligado, acima das listas De e Para, ligado à contagem", () => {
  assert.match(html, /<label for="rota-busca">Buscar lugar<\/label>/);
  assert.match(html, /<input[^>]*id="rota-busca"[^>]*type="search"|<input[^>]*type="search"[^>]*id="rota-busca"/);
  assert.ok(html.indexOf('id="rota-busca"') < html.indexOf('id="rota-de"'), "busca antes de De");
  assert.match(html, /id="rota-busca"[^>]*aria-describedby="ajuda-busca"/);
  assert.match(html, /id="ajuda-busca"/);
  assert.doesNotMatch(html, /role="combobox"/, "lista filtrada simples, não combobox ARIA");
});

test("a contagem usa a região aria-live que já existe (sem região nova)", () => {
  assert.equal(html.match(/aria-live="polite"/g)?.length, 1, "só a região #anuncio-rota é aria-live");
  assert.match(tela, /ESPERA_ANUNCIO_BUSCA_MS/);
  assert.match(tela, /textoContagem/);
});

test("confirmação visível do destino e botão 'Usar como origem' (escondidos até o toque)", () => {
  assert.match(html, /<p id="destino-escolhido"[^>]*hidden/);
  assert.match(html, /<button type="button" id="usar-como-origem"[^>]*hidden[^>]*>Usar como origem<\/button>/);
  assert.match(css, /\.rota__botao--voz|\.rota__escolha/);
});

test("marcadores de entrada: alvo de 44 px, papel de botão, nome acessível e Enter/Espaço", () => {
  assert.match(tela, /TAMANHO_ALVO_MARCADOR_PX/);
  assert.match(tela, /setAttribute\("role", "button"\)/);
  assert.match(tela, /setAttribute\("aria-label", rotuloDoMarcador/);
  assert.match(tela, /"Enter"/);
  assert.match(tela, /keyboard: false/);
  const m = /export const TAMANHO_ALVO_MARCADOR_PX = (\d+)/.exec(readFileSync(new URL("../mapa/marcadores.ts", import.meta.url), "utf8"));
  assert.ok(m && Number(m[1]) >= 44);
  assert.match(cssMapa, /\.mapa-alvo\s*\{[^}]*(width|min-width):\s*44px/);
});

test("o mapa não anima ao escolher o destino", () => {
  assert.doesNotMatch(tela, /flyTo|panTo\([^)]*\)(?!.*animate)/);
});
