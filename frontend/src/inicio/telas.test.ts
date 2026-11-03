import assert from "node:assert/strict";
import { test } from "node:test";
import { anuncioDeLocalizacao, orientacaoDaTela, tituloDaPagina } from "../a11y/orientacao.ts";
import { lerRota } from "../rotas/interpretar.ts";
import { ROTA_200 } from "../rotas/fixtures.ts";
import { TELA_ESCOLHER, TELA_SEM_ROTA, telaDaRota } from "./telas.ts";

const rota = lerRota(ROTA_200)!;

test("títulos das três telas da página inicial, todos '<Tela> · Navegação Acessível no Campus' e todos diferentes", () => {
  const titulos = [TELA_ESCOLHER, telaDaRota(rota), TELA_SEM_ROTA].map((t) => tituloDaPagina(t.nome));
  assert.deepEqual(titulos, [
    "Escolher destino · Navegação Acessível no Campus",
    "Rota traçada · Navegação Acessível no Campus",
    "Rota não traçada · Navegação Acessível no Campus",
  ]);
});

test("a frase de cada tela é 'Você está em: <tela>. <próxima ação>' e curta", () => {
  for (const t of [TELA_ESCOLHER, telaDaRota(rota), TELA_SEM_ROTA]) {
    const frase = orientacaoDaTela(t);
    assert.ok(frase.startsWith(`Você está em: ${t.nome}. `), frase);
    assert.ok(frase.length <= 140, `${frase.length} caracteres`);
  }
  assert.equal(
    orientacaoDaTela(telaDaRota(rota)),
    "Você está em: Rota traçada. Cerca de 182 metros, 1 aviso. As instruções vêm a seguir.",
  );
});

test("anuncioDeLocalizacao não repete pontuação do nome da tela", () => {
  assert.equal(anuncioDeLocalizacao("Rota traçada.", "Siga."), "Você está em: Rota traçada. Siga.");
  assert.equal(anuncioDeLocalizacao("Etapa 2 de 3: Medir o ponto", "Pare."), "Você está em: Etapa 2 de 3: Medir o ponto. Pare.");
});
