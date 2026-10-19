/**
 * O mapa Leaflet nunca anima, nas duas páginas: as opções do L.map desligam zoom, fade, marcador,
 * inércia e o "salto" no limite do zoom, e toda chamada que move o mapa passa animate: false.
 * Conferido no texto dos arquivos (as páginas dependem do DOM e não rodam no node:test).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const PAGINAS = ["../inicio/pagina.ts", "../medicao/pagina.ts"];
const OPCOES = ["zoomAnimation", "fadeAnimation", "markerZoomAnimation", "inertia", "bounceAtZoomLimits"];

for (const caminho of PAGINAS) {
  const fonte = readFileSync(new URL(caminho, import.meta.url), "utf8");

  test(`${caminho}: o L.map recebe as opções que desligam a animação`, () => {
    assert.match(fonte, /L\.map\(/);
    const definicao = /const SEM_ANIMACAO = \{([\s\S]*?)\} as const;/.exec(fonte)?.[1] ?? "";
    for (const opcao of OPCOES) {
      assert.match(definicao, new RegExp(`${opcao}:\\s*false`), `${opcao} deve ser false`);
    }
    assert.ok(fonte.includes("...SEM_ANIMACAO"), "o L.map precisa espalhar SEM_ANIMACAO");
  });

  test(`${caminho}: setView, flyTo, panTo, fitBounds e invalidateSize usam animate: false`, () => {
    const chamadas = [...fonte.matchAll(/\.(setView|flyTo|flyToBounds|panTo|panBy|fitBounds|setZoom|zoomIn|zoomOut|invalidateSize)\(([^;]*)\);/g)];
    for (const [linha, nome] of chamadas) {
      assert.match(linha, /animate:\s*false/, `${nome} sem animate: false`);
    }
  });
}

test("a medição usa as chamadas que movem o mapa (o teste acima não passa por não achar nada)", () => {
  const fonte = readFileSync(new URL("../medicao/pagina.ts", import.meta.url), "utf8");
  assert.match(fonte, /\.fitBounds\(/);
  assert.match(fonte, /\.panTo\(/);
  assert.match(fonte, /\.invalidateSize\(/);
});
