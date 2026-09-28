# Contrato da API — Mackenzie sem Barreiras

Fonte única para backend e frontend (resumo em [`CLAUDE.md` §7](../CLAUDE.md)).

Base local: `http://localhost:8000`. JSON UTF-8. CORS liberado para as origens de
`CORS_ORIGENS` (vírgula), padrão `http://localhost:5173,http://localhost:8080`.

- `GET /saude` → 200 `{"status": "ok", "banco": "ok"}` (503 se o banco não responde).
- `GET /tipos-barreira` → 200 `[{"codigo": "degrau", "nome": "Degrau", "descricao": "..."}]`
  (só `ativo = true`, ordenado por `nome`).
- `GET /area-estudo` → 200 GeoJSON `FeatureCollection` com as áreas; cada Feature tem
  `properties: {"nome": ..., "descricao": ...}` e `geometry` Polygon.
- `POST /alertas` corpo:
  ```json
  {"latitude": -23.5472, "longitude": -46.6525, "tipo": "degrau",
   "severidade": 2, "descricao": "texto opcional", "sessao_id": "<uuid>"}
  ```
  `latitude` ∈ [-90, 90]; `longitude` ∈ [-180, 180]; `tipo` código ativo; `severidade`
  1–3 ou ausente/null; `descricao` opcional, ≤ 500 caracteres (espaços nas pontas
  removidos; vazia vira null); `sessao_id` UUID; campos extras são rejeitados.
  - 201 `{"id": 12, "status": "bruto", "motivo_descarte": null,
    "mensagem": "Alerta recebido. Ele será validado quando outras pessoas confirmarem."}`
  - 201 `{"id": 13, "status": "descartado", "motivo_descarte": "fora_da_area",
    "mensagem": "O ponto está fora da área de estudo do projeto."}`
  - 422 `{"mensagem": "Alerta inválido.", "erros": [{"campo": "latitude", "erro": "..."}]}`
    (inclui JSON malformado: `campo: "corpo"`). O payload vai para `alertas_rejeitados`.
- `GET /barreiras?bbox=minLon,minLat,maxLon,maxLat[&status=pendente|confirmada][&origem=real|simulacao]`
  `bbox` obrigatório (422 se ausente/malformado/min ≥ max/fora das faixas). `origem`
  padrão `real`. Até `LIMITE_BARREIRAS_POR_CONSULTA` (config, padrão 1000) itens.
  → 200 GeoJSON `FeatureCollection`; cada Feature: geometry Point e
  `properties: {"id", "tipo", "tipo_nome", "confirmacoes", "status", "atualizado_em"}`.
- `POST /validacao/executar?origem=real|simulacao` (padrão `real`; D7) →
  200 `{"origem", "alertas_processados", "agrupados", "ruido_isolado",
  "barreiras_pendentes", "barreiras_confirmadas", "parametros": {"eps_metros",
  "min_pontos", "min_confirmacoes"}}`; 401 com token errado/ausente.
- `GET /validacao/estatisticas?origem=real|simulacao` (padrão `real`) → 200
  ```json
  {"origem": "simulacao", "rotulo": "SIMULAÇÃO — dados sintéticos",
   "alertas": {"recebidos": 0, "rejeitados_schema": 0, "descartados": {"fora_da_area": 0},
               "aguardando_pipeline": 0, "ruido_isolado": 0, "agrupados": 0},
   "barreiras": {"total": 0, "pendentes": 0, "confirmadas": 0},
   "parametros": {"eps_metros": 8, "min_pontos": 2, "min_confirmacoes": 3},
   "gerado_em": "ISO-8601"}
  ```
  `rotulo` para `real`: `"Dados reais de campo"`. `recebidos` = rejeitados + linhas de
  `alertas` daquela origem. Unidades explícitas: o bloco `alertas` conta alertas, o bloco
  `barreiras` conta barreiras.

## Estado de implementação

- **M2 (implementado):** `GET /saude`, `GET /tipos-barreira`, `GET /area-estudo`,
  `POST /alertas`, `GET /barreiras`.
- **M3 (planejado):** `POST /validacao/executar`, `GET /validacao/estatisticas`.
