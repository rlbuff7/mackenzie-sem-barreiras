/** Respostas gravadas do contrato (docs/planos/e6-prototipo-banner.md, B2 e B3). Dado de SIMULAÇÃO: só para teste e prints. */
export const ROTA_200 = {
  rotulo: "Caminhos do mapa aberto, ainda não conferidos a pé (dado de pesquisa)",
  provisorio: false,
  perfil: "sem_restricao",
  origem: { id: 3, nome: "Portão da rua Piauí", latitude: -23.5478, longitude: -46.6527 },
  destino: { id: 7, nome: "Entrada do Prédio 31", latitude: -23.5474, longitude: -46.6515 },
  distancia_m: 182.4,
  custo: 310.2,
  acessivel_cadeirante: false,
  avisos: ["O caminho tem escada (cerca de 10 metros)."],
  aviso_seguranca: "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade.",
  trechos: [
    { ordem: 1, aresta_id: 5, tipo: "calcada", comprimento_m: 40.2, acessivel_cadeirante: true, fonte_verificacao: "imagem" },
    { ordem: 2, aresta_id: 6, tipo: "escada", comprimento_m: 10, acessivel_cadeirante: false, fonte_verificacao: "imagem" },
  ],
  instrucoes: [
    { ordem: 1, texto: "Siga pela calçada por cerca de 40 metros." },
    { ordem: 2, texto: "Atenção: há uma escada no caminho, cerca de 10 metros." },
    { ordem: 3, texto: "Você chegou à entrada do Prédio 31." },
  ],
  geometria: {
    type: "LineString",
    coordinates: [
      [-46.6527, -23.5478],
      [-46.6525, -23.5477],
      [-46.652, -23.5476],
      [-46.6515, -23.5474],
    ],
  },
};

/** Perfil cadeirante: caminho mais longo, sem escada, só por calçada e rampa. */
export const ROTA_CADEIRANTE_200 = {
  ...ROTA_200,
  perfil: "cadeirante",
  distancia_m: 214.7,
  acessivel_cadeirante: true,
  avisos: [],
  trechos: [
    { ordem: 1, aresta_id: 5, tipo: "calcada", comprimento_m: 40.2, acessivel_cadeirante: true, fonte_verificacao: "imagem" },
    { ordem: 2, aresta_id: 9, tipo: "rampa", comprimento_m: 30, acessivel_cadeirante: true, fonte_verificacao: "imagem" },
  ],
  instrucoes: [
    { ordem: 1, texto: "Siga pela calçada por cerca de 40 metros." },
    { ordem: 2, texto: "Siga pela rampa por cerca de 30 metros." },
    { ordem: 3, texto: "Você chegou à entrada do Prédio 31." },
  ],
};

/** Corpo do 404 do contrato quando não há caminho (cadeirante sem alternativa sem escada). */
export const SEM_ROTA_404 = { mensagem: "Não há caminho mapeado entre esses dois pontos.", codigo: "sem_rota" };

export const PONTOS_200 = {
  type: "FeatureCollection",
  rotulo: "Dados de pesquisa",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-46.6527, -23.5478] },
      properties: { id: 3, tipo: "portao", nome: "Portão da rua Piauí", descricao: null, acessivel: true, fonte_verificacao: "imagem", tem_no: true },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-46.6515, -23.5474] },
      properties: { id: 7, tipo: "entrada", nome: "Entrada do Prédio 31", descricao: "Porta principal", acessivel: true, fonte_verificacao: "imagem", tem_no: true },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-46.651, -23.547] },
      properties: { id: 8, tipo: "entrada", nome: "Entrada sem nó", descricao: null, acessivel: null, fonte_verificacao: "imagem", tem_no: false },
    },
  ],
};
