import assert from "node:assert/strict";
import { test } from "node:test";
import { itensIguais, type ItemListaBarreira } from "./itens.ts";

const base: ItemListaBarreira = {
  id: 1,
  tipoNome: "Degrau",
  status: "pendente",
  confirmacoes: 1,
  latitude: -23.5,
  longitude: -46.6,
};
const outro: ItemListaBarreira = { ...base, id: 2 };

test("mesmos itens em ordem diferente são iguais", () => {
  assert.equal(itensIguais([base, outro], [outro, base]), true);
});

test("conjuntos de ids diferentes não são iguais", () => {
  assert.equal(itensIguais([base], [outro]), false);
  assert.equal(itensIguais([base], [base, outro]), false);
});

test("mesmo id com qualquer campo diferente não é igual", () => {
  const variacoes: Partial<ItemListaBarreira>[] = [
    { tipoNome: "Rampa" },
    { status: "confirmada" },
    { confirmacoes: 2 },
    { latitude: -23.6 },
    { longitude: -46.7 },
  ];
  for (const variacao of variacoes) {
    assert.equal(itensIguais([base], [{ ...base, ...variacao }]), false, JSON.stringify(variacao));
  }
});

test("listas vazias são iguais", () => {
  assert.equal(itensIguais([], []), true);
});
