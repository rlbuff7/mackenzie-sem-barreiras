/** GeoJSON guarda [longitude, latitude]; o Leaflet quer [latitude, longitude]. A inversão mora só aqui. */
export function paraLatLng(coordenadas: readonly (readonly [number, number])[]): [number, number][] {
  return coordenadas.map(([longitude, latitude]) => [latitude, longitude]);
}

export function pontoParaLatLng(ponto: { latitude: number; longitude: number }): [number, number] {
  return [ponto.latitude, ponto.longitude];
}
