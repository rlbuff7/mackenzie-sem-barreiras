/**
 * Itens da lista acessível de barreiras e a comparação entre duas listas.
 *
 * Fica fora de mapa.ts (que depende do Leaflet e do DOM) para ser uma função
 * pura, verificável isoladamente.
 */

/** Uma barreira da bbox atual, com só o necessário para a lista e o marcador. */
export interface ItemListaBarreira {
  id: number;
  tipoNome: string;
  status: "pendente" | "confirmada";
  confirmacoes: number;
  latitude: number;
  longitude: number;
}

/**
 * Compara duas listas de barreiras pelo que aparece na lista acessível e no
 * marcador (id, tipo, status, confirmações, posição), como conjuntos — sem
 * depender da ordem, já que o backend não garante a mesma ordem entre duas
 * consultas idênticas. Usado para não notificar `aoAtualizarBarreiras` (e não
 * refazer os marcadores) quando a recarga da bbox devolve exatamente o mesmo
 * conteúdo de antes.
 */
export function itensIguais(a: ItemListaBarreira[], b: ItemListaBarreira[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const porId = new Map(b.map((item) => [item.id, item]));
  return a.every((item) => {
    const outro = porId.get(item.id);
    return (
      outro !== undefined &&
      outro.tipoNome === item.tipoNome &&
      outro.status === item.status &&
      outro.confirmacoes === item.confirmacoes &&
      outro.latitude === item.latitude &&
      outro.longitude === item.longitude
    );
  });
}
