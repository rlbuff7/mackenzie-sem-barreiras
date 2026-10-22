/*
 * Armazém das fotos na fila em IndexedDB (a tela usa; o node:test usa um fake). Cada foto guarda o
 * Blob JPEG (já reduzido, sem EXIF) e os parâmetros do envio. Sem IndexedDB devolve null: a fila
 * então envia direto.
 */
import type { ArmazemFotos, ItemFoto } from "./fila-fotos.ts";

const NOME_BANCO = "msb-fotos";
const LOJA = "fila";

function abrir(): Promise<IDBDatabase> {
  return new Promise((ok, erro) => {
    const req = indexedDB.open(NOME_BANCO, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(LOJA, { keyPath: "id_cliente" });
    };
    req.onsuccess = () => ok(req.result);
    req.onerror = () => erro(req.error);
    req.onblocked = () => erro(new Error("banco bloqueado"));
  });
}

function pedido<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((ok, erro) => {
    req.onsuccess = () => ok(req.result);
    req.onerror = () => erro(req.error);
  });
}

export function criarArmazemFotos(): ArmazemFotos | null {
  try {
    if (typeof indexedDB === "undefined" || !indexedDB) return null;
  } catch {
    return null;
  }
  let banco: Promise<IDBDatabase> | null = null;
  const db = (): Promise<IDBDatabase> => (banco ??= abrir());
  const loja = async (modo: IDBTransactionMode): Promise<IDBObjectStore> =>
    (await db()).transaction(LOJA, modo).objectStore(LOJA);
  return {
    listar: async () => (await pedido((await loja("readonly")).getAll())) as ItemFoto[],
    gravar: async (item) => void (await pedido((await loja("readwrite")).put(item))),
    remover: async (id) => void (await pedido((await loja("readwrite")).delete(id))),
  };
}
