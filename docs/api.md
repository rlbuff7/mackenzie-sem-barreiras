# Contrato da API — Mackenzie sem Barreiras

Fonte única para backend e frontend (resumo em [`CLAUDE.md` §7](../CLAUDE.md)).

Base local: `http://localhost:8000`. JSON UTF-8. CORS liberado para as origens de
`CORS_ORIGENS` (vírgula), padrão `http://localhost:5173` (só o servidor de dev do
Vite; o frontend em container fala com a API pela mesma origem, via proxy do nginx
em `/api/` — R19, `frontend/nginx.conf` — e não precisa de CORS).

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
  Tipos estritos: `latitude`/`longitude` só aceitam número JSON (inteiro vale;
  `true` e `"-23.5"` não) e `severidade` só inteiro (`true`, `"2"`, `2.5` e `2.0` não).
  Erros: `"Deve ser um número."` e `"Deve ser um número inteiro."`.
  - 201 `{"id": 12, "status": "bruto", "motivo_descarte": null,
    "mensagem": "Alerta recebido. Ele será validado quando outras pessoas confirmarem."}`
  - 201 `{"id": 13, "status": "descartado", "motivo_descarte": "fora_da_area",
    "mensagem": "O ponto está fora da área de estudo do projeto."}`
  - 422 `{"mensagem": "Alerta inválido.", "erros": [{"campo": "latitude", "erro": "..."}]}`.
    O payload vai para `alertas_rejeitados`. Erros do corpo inteiro saem com
    `campo: "corpo"`:
    - `"JSON malformado."`: sintaxe inválida, UTF-8 inválido, `NaN`/`Infinity`/
      `-Infinity`, número que estoura o float (`1e999`) ou aninhamento profundo demais.
      O corpo cru é guardado como texto (`{"corpo_invalido": "..."}`, até 2000
      caracteres, U+0000 trocado por U+FFFD).
    - `"O corpo tem um caractere que não pode ser gravado (U+0000 ou um substituto
      UTF-16 isolado)."`: JSON válido, mas com `\u0000` ou um `\ud800` isolado em
      alguma chave ou valor. O corpo inteiro é rejeitado (o caractere não é removido).
    - `"Deve ser um objeto JSON (chave-valor)."`: JSON válido que não é objeto
      (`42`, `"texto"`, `[]`, `null`).

    Nenhum corpo dá 500 no estágio 1 (`app/validacao/entrada.py::interpretar_corpo`).
  - 413 `{"mensagem": "Corpo grande demais: o limite é 16 KiB."}`: corpo acima de
    `LIMITE_CORPO_BYTES` (padrão 16384). É abuso, não relato: nada é gravado, nem em
    `alertas_rejeitados`. A API confere o `Content-Length` antes de ler e corta a
    leitura ao passar do limite. Pelo frontend, o nginx já barra antes
    (`client_max_body_size 16k`, corpo HTML do nginx; mantenha os dois limites iguais).
  - 429 (só pelo nginx do frontend, nunca pela API): mais de 30 envios por minuto de
    média, com rajada de 20 (`limit_req` em `frontend/nginx.conf`, só `POST
    /api/alertas`, corpo HTML). Atrás de um túnel o limite é coletivo. O frontend mostra
    "Muitos envios em sequência; aguarde um minuto."
- `GET /barreiras?bbox=minLon,minLat,maxLon,maxLat[&status=pendente|confirmada][&origem=real|simulacao]`
  `bbox` obrigatório (422 se ausente/malformado/min ≥ max/fora das faixas, com
  `campo: "bbox"`; formato abaixo). `origem`
  padrão `real`. Até `LIMITE_BARREIRAS_POR_CONSULTA` (config, padrão 1000) itens.
  → 200 GeoJSON `FeatureCollection` com o membro extra `rotulo` no topo (o mesmo texto
  das estatísticas para a origem: `"Dados reais de campo"` ou
  `"SIMULAÇÃO — dados sintéticos"`; RFC 7946 §6.1 permite membros extras); cada
  Feature: geometry Point e
  `properties: {"id", "tipo", "tipo_nome", "confirmacoes", "status", "atualizado_em"}`.
  `atualizado_em` é o instante da **última execução do pipeline** daquela origem (o
  mesmo `executado_em` das estatísticas), não a data do primeiro relato nem da última
  confirmação: cada execução apaga e recria as barreiras da origem (D6), então os `id`
  e as datas das barreiras mudam a cada execução. Não guarde o `id` de uma barreira
  entre execuções.
- `POST /validacao/executar?origem=real|simulacao` (padrão `real`; D7) →
  200 `{"origem", "rotulo", "alertas_processados", "agrupados", "ruido_isolado",
  "barreiras_pendentes", "barreiras_confirmadas", "parametros": {"eps_metros",
  "min_pontos", "min_confirmacoes"}, "executado_em"}` (`rotulo` igual ao das
  estatísticas; `parametros` são os da configuração, que esta execução usou;
  `executado_em` em UTC, ISO-8601); 401 com token errado/ausente
  (`{"detail": "Token de administrador ausente ou inválido (header X-Token-Admin)."}`).
  Cada execução grava seus parâmetros e `executado_em` em `execucoes_pipeline`
  (uma linha por origem, migration 003).
- `GET /validacao/estatisticas?origem=real|simulacao` (padrão `real`) → 200
  ```json
  {"origem": "simulacao", "rotulo": "SIMULAÇÃO — dados sintéticos",
   "alertas": {"recebidos": 0, "rejeitados_schema": 0, "descartados": {"fora_da_area": 0},
               "aguardando_pipeline": 0, "ruido_isolado": 0, "agrupados": 0},
   "barreiras": {"total": 0, "pendentes": 0, "confirmadas": 0},
   "parametros": {"eps_metros": 8, "min_pontos": 2, "min_confirmacoes": 3},
   "executado_em": "ISO-8601",
   "gerado_em": "ISO-8601"}
  ```
  `parametros` e `executado_em` são os da ÚLTIMA EXECUÇÃO do pipeline para aquela origem
  (tabela `execucoes_pipeline`), NÃO a configuração atual — assim a figura do funil nunca
  leva parâmetros que não produziram os números. Origem nunca processada: ambos `null`.
  Todas as contagens vêm de um único snapshot (uma só consulta). `executado_em` e
  `gerado_em` em UTC.
  `rotulo` para `real`: `"Dados reais de campo"`. `recebidos` = rejeitados + linhas de
  `alertas` daquela origem. Unidades explícitas: o bloco `alertas` conta alertas, o bloco
  `barreiras` conta barreiras.
- Nas duas rotas de validação, `parametros.eps_metros` sai como número de ponto
  flutuante (ex.: `8.0`), como na configuração.
- **422 de parâmetro inválido** (query: `bbox` ausente ou malformado, `status`/`origem`
  fora das opções), em todas as rotas: `{"mensagem": "Requisição inválida.", "erros":
  [{"campo": "origem", "erro": "Deve ser um destes valores: 'real' ou 'simulacao'."}]}`.
  `campo` é o nome do parâmetro; as mensagens são as mesmas do `POST /alertas`
  (`app/validacao/mensagens.py`). O 422 do `POST /alertas` continua o de cima
  (`"Alerta inválido."`).

- **Documentação interativa:** `/docs`, `/redoc` e `/openapi.json` existem quando
  `EXPOR_DOCS=true` (padrão, dev) e respondem 404 com `EXPOR_DOCS=false` (coleta
  pública, `.env.example`).

## Estado de implementação

- **M2 (implementado):** `GET /saude`, `GET /tipos-barreira`, `GET /area-estudo`,
  `POST /alertas`, `GET /barreiras`.
- **M3 (implementado):** `POST /validacao/executar`, `GET /validacao/estatisticas`
  (`app/routers/validacao.py`; lógica em `app/validacao/pipeline.py` e
  `app/validacao/estatisticas.py`).
