# Contrato da API — Mackenzie sem Barreiras

> **Escopo antigo (até 08/10/2026): este é o contrato da API de crowdsourcing de barreiras (`/alertas`, `/barreiras`, `/validacao/*`). As rotas do escopo novo `/pontos-interesse` e `/rotas` (protótipo E6) existem e estão documentadas na seção "Escopo novo" no fim deste arquivo; `/orientacoes` ainda não existe (M4; plano no [`CLAUDE.md`](../CLAUDE.md), §7 e §16). A medição de GPS da equipe (`/medicoes`) também está implementada.**

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
- `POST /medicoes` (medição de GPS em tempo real; é dado DA EQUIPE, os celulares dela
  nos pontos de controle, nunca de quem navega; sem nome de pessoa, só o modelo do
  aparelho). Header `X-Codigo-Equipe` obrigatório, igual a `MEDICAO_CODIGO_EQUIPE`
  (comparação em tempo constante; use só caracteres ASCII). Corpo:
  ```json
  {"medicoes": [{"id_cliente": "<uuid>", "tipo": "ponto",
                 "medido_em": "2026-10-14T10:30:00-03:00", "aparelho": "Galaxy A54",
                 "ponto": 3, "condicao": "ceu_aberto",
                 "latitude": -23.5472, "longitude": -46.6525, "precisao_m": 4.5}]}
  ```
  De 1 a 50 medições por lote (o trajeto vai em lotes a cada 10 s). Campos, todos
  estritos (`extra` é recusado; número só como número JSON, `"5"` e `true` não;
  `NaN`/`Infinity` não):
  - `id_cliente` UUID (gerado no celular), `tipo` (`ponto`|`trajeto`|`bussola`|
    `vibracao`), `medido_em` texto ISO 8601 COM fuso (`...-03:00` ou `...Z`),
    `aparelho` 1 a 80 caracteres (espaços nas pontas removidos), todos obrigatórios.
  - `ponto` inteiro 1 a 12, obrigatório quando `tipo = "ponto"`; `condicao`
    `ceu_aberto`|`entre_predios`|`entrada_predio`|`coberto`.
  - `latitude` [-90, 90] e `longitude` [-180, 180]: obrigatórias em `ponto` e
    `trajeto`; nos outros tipos, ou as duas ou nenhuma. `precisao_m` >= 0
    (metros): obrigatória nos tipos com posição E sempre que há latitude e
    longitude, em qualquer tipo.
  - `altitude_m`, `altitude_precisao_m`, `velocidade_ms`, `rumo_gps_graus`: números
    livres, como o navegador informa. `bussola_graus` 0 <= x < 360;
    `bussola_fonte` `webkitCompassHeading`|`alpha_absoluto`|`alpha_relativo`;
    `bussola_oscilacao_graus` >= 0; `vibracao_suportada` booleano;
    `observacao` <= 500 caracteres e `user_agent` <= 300 (vazios viram null).
  - 200 `{"gravadas": 3, "repetidas": 1}`: o lote inteiro vai numa transação. Um
    `id_cliente` que já existe conta como repetido e não dá erro
    (`ON CONFLICT (id_cliente) DO NOTHING`); reenviar o mesmo lote inteiro dá
    `{"gravadas": 0, "repetidas": N}`. A posição entra em SRID 4326 (grau).
  - 422 `{"mensagem": "Medição inválida.", "erros": [{"campo":
    "medicoes.0.precisao_m", "erro": "..."}]}`: `campo` leva o índice do item no lote;
    erros do corpo inteiro saem com `campo: "corpo"` (`"JSON malformado."`) ou
    `"medicoes"` (lote vazio ou com mais de 50). Se um item é inválido, NENHUM do
    lote é gravado.
  - 401 `{"detail": "Código da equipe ausente ou inválido (header X-Codigo-Equipe)."}`.
  - 503 `{"detail": "Medição desligada neste servidor."}`: `MEDICAO_CODIGO_EQUIPE`
    vazio no servidor (padrão). Diferente do `TOKEN_ADMIN`, vazio NÃO abre a rota.
    A checagem do código vem antes da leitura do corpo (503 e 401 não leem nada).
  - 413 `{"mensagem": "Corpo grande demais: o limite é 16 KiB."}`: o mesmo
    `LIMITE_CORPO_BYTES` do `POST /alertas`. Um lote de 50 medições completas
    (com `user_agent`) pode passar de 16 KiB: mande lotes menores.
  - 429 (só pelo nginx do frontend): `POST /api/medicoes` tem limite próprio, 60
    requisições por minuto de média, rajada de 30 (`frontend/nginx.conf`).
- `GET /medicoes/resumo` (header `X-Token-Admin`, como `POST /validacao/executar`;
  `TOKEN_ADMIN` vazio deixa aberta, só em desenvolvimento; 401 com o mesmo texto) →
  200
  ```json
  {"total": 7,
   "por_aparelho": [{"aparelho": "Galaxy A54", "pontos": 2, "medicoes": 4,
                     "precisao_mediana_m": 6.0}],
   "por_ponto": [{"ponto": 1, "medicoes": 4, "precisao_mediana_m": 6.0,
                  "precisao_p90_m": 16.1}]}
  ```
  Serve para a equipe conferir a ida a campo sem psql. `total` conta todas as
  linhas. `por_aparelho` (ordem alfabética): `pontos` = quantos pontos de controle
  DISTINTOS o aparelho mediu, `medicoes` = linhas dele, de todos os tipos.
  `por_ponto` (ordem do ponto): só linhas com número de ponto, `medicoes` conta todas
  elas. Mediana e p90 (`percentile_cont`, interpolados, em metros, 2 casas) usam só as
  linhas com `precisao_m`; sem nenhuma, `null`.
- `GET /medicoes/analise` (mesma proteção do `/medicoes/resumo`: header
  `X-Token-Admin`, `TOKEN_ADMIN` vazio deixa aberta só em desenvolvimento, 401) → 200
  ```json
  {"aviso": "O erro é a distância entre a posição medida pelo celular e uma referência estimada por imagem de satélite ...",
   "total_medicoes_analisadas": 3,
   "por_ponto_aparelho": [{"ponto_codigo": "P01", "ponto_nome": "Praça de convivência ...",
                           "aparelho": "Galaxy A54", "n": 3, "erro_mediana_m": 10.0,
                           "erro_p90_m": 18.0, "fracao_erro_dentro_precisao": 0.67}],
   "por_condicao": [{"condicao": "ceu_aberto", "n": 2, "erro_mediana_m": 5.0,
                     "erro_p90_m": 9.0}]}
  ```
  Erro de cada medição de `tipo = "ponto"` contra a referência do ponto de controle
  (views `vw_erro_medicoes` e `vw_erro_por_ponto_aparelho`, distância em SRID 31983).
  A referência é uma estimativa por imagem de satélite, então o erro inclui a incerteza
  dela: NÃO é o erro absoluto do GPS (o `aviso` diz isso). Pontos sem referência (11 e
  12) e medições sem posição não entram. Erros em metros com 1 casa;
  `fracao_erro_dentro_precisao` (0 a 1, 2 casas) é a parcela das medições com erro
  menor ou igual à `precisao_m` informada pelo celular. `por_condicao` só conta
  medições que informaram `condicao`. Sem dados: listas vazias e total 0 (200).
- `POST /medicoes/fotos?id_cliente=<uuid>&ponto=<1..12>&aparelho=<texto>&tirada_em=<ISO 8601 com fuso>[&largura_px=<1..2048>&altura_px=<1..2048>&observacao=<até 500>]`
  (foto do ponto de controle, 22/10/2026; dado DA EQUIPE). Header `X-Codigo-Equipe`
  (mesma regra do `POST /medicoes`: código não configurado = 503, ausente ou errado =
  401), header `Content-Type: image/jpeg` e o JPEG como corpo bruto (sem multipart).
  Sem metadados: o app reprocessa a imagem num canvas, que descarta EXIF/GPS.
  - 200 `{"gravada": true}`; o mesmo `id_cliente` de novo: 200 `{"gravada": false}`
    (idempotente, `ON CONFLICT DO NOTHING`).
  - 413 `{"mensagem": ...}`: corpo vazio ou com mais de 1 048 576 bytes (confere o
    `Content-Length` antes de ler; o nginx aceita até 1200k só nesta rota).
  - 415: `Content-Type` diferente de `image/jpeg`, ou corpo que não começa com
    `FF D8 FF`.
  - 422 `{"mensagem": "A foto tem metadados (EXIF); envie pelo app, que remove."}`
    se há um segmento `Exif\0\0` nos primeiros 64 KiB; parâmetro inválido ou
    desconhecido: `{"mensagem": "Foto inválida.", "erros": [{"campo": "ponto",
    "erro": "..."}]}`.
  - 429 (só pelo nginx): mesmo limite de envio das medições.
- `GET /medicoes/fotos/resumo` (header `X-Token-Admin`, como `/medicoes/resumo`) → 200
  `[{"ponto_codigo": "P03", "ponto": 3, "aparelho": "Galaxy A54", "fotos": 2,
  "ultima_em": "2026-10-22T13:31:00+00:00"}]`, sem os bytes, ordenado por ponto e
  aparelho (pontos 11 e 12 saem como `P11` e `P12`).
- `GET /medicoes/fotos/{id}` (header `X-Token-Admin`) → o JPEG (`image/jpeg`,
  `Cache-Control: no-store`); 404 se o id não existe. Tabela `fotos_pontos`
  (migration 008); código em `app/routers/fotos.py` e `app/schemas/foto.py`.
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
- **Medição de GPS (14/10/2026, implementado):** `POST /medicoes`, `GET /medicoes/resumo`
  (`app/routers/medicoes.py`, `app/schemas/medicao.py`; tabela `medicoes_gps`,
  migration 005). Variável nova: `MEDICAO_CODIGO_EQUIPE` (vazio = desligada).

## Escopo novo: `/pontos-interesse` e `/rotas` (protótipo E6)

Demonstração do protótipo sobre um trecho piloto. **Não é orientação em tempo real** e o
grafo atual é **PROVISÓRIO**: caminhos importados do OpenStreetMap (© contribuidores do
OpenStreetMap, licença ODbL), ainda não conferidos a pé, até o mapeamento do campus chegar
(M2). Toda resposta de rota traz o rótulo de proveniência e o aviso de segurança.

Parâmetros de custo (provisórios, calibração com a orientadora): `PENALIDADE_ESCADA`,
`PENALIDADE_TRAVESSIA`, `PENALIDADE_TRECHO_NAO_VERIFICADO`,
`LIMITE_PONTOS_INTERESSE_POR_CONSULTA` (ver `.env.example`).

### `GET /pontos-interesse?bbox=minLon,minLat,maxLon,maxLat[&tipo=entrada,portao]`

`bbox` **obrigatório** (mesmo formato e mesmo 422, `campo: "bbox"`, de `GET /barreiras`).
`tipo` opcional: lista separada por vírgula de `predio`, `entrada`, `escada`, `rampa`,
`quadra`, `portao` (valor inválido: 422 com `campo: "tipo"`). Até
`LIMITE_PONTOS_INTERESSE_POR_CONSULTA` itens, ordenados por `nome`.

200: GeoJSON `FeatureCollection` com membros extras `rotulo` (texto de proveniência, vazio
se não há pontos) e `atribuicao` (presente quando há dado do OpenStreetMap). Cada Feature:
`geometry` Point `[longitude, latitude]` e
`properties: {"id", "tipo", "nome", "descricao", "acessivel", "fonte_verificacao", "tem_no"}`.
`tem_no = true` quer dizer que o ponto está ligado ao grafo e pode ser origem ou destino.
`acessivel`: `true`, `false` ou `null` (não verificado).

```bash
curl 'http://localhost:8000/pontos-interesse?bbox=-46.6622,-23.5575,-46.6422,-23.5375&tipo=entrada'
```

### `POST /rotas`

Rota pública (sem token); não grava nada, não recebe a posição de ninguém e o corpo não vai
para log. A origem é um ponto escolhido na lista (`origem_id`), nunca a posição do aparelho.

```json
{"origem_id": 3, "destino_id": 7, "perfil": "sem_restricao"}
```

- `origem_id`: ponto com nó (entrada ou portão). `destino_id`: **entrada** com nó.
  Estrito: campo extra, texto no lugar de número ou `origem_id == destino_id` dão 422.
- `perfil`: `"sem_restricao"` (padrão), `"cadeirante"` ou `"deficiencia_visual"` (incluído
  provisoriamente na v0 em 27/10/2026, a validar com a orientadora). Outro valor: 422.
- **Perfil `deficiencia_visual`:** escada e trecho inacessível a cadeirante NÃO são proibidos,
  mas o custo do trecho (escada, travessia ou não conferido a pé) é multiplicado por
  `PENALIDADE_PERFIL_VISUAL` (padrão 2.0, provisório). `avisos` sempre inclui
  `"Ainda sem dados de piso tátil: a rota usa caminhos do mapa aberto."`, e a instrução do
  trecho anterior a uma escada termina com `"Em cerca de N metros, escada."`.
- **Perfil `cadeirante`: a rota NUNCA tem trecho de escada nem trecho marcado como
  inacessível.** Esses trechos saem do grafo da consulta (não é penalidade). Se não houver
  caminho sem eles, a resposta é 404 `sem_rota`: silêncio é melhor que palpite.
- Custo = comprimento × fator (tipo × verificação), com as penalidades do `.env`. As
  instruções não dizem "esquerda/direita" (rumo é do M4).

200:

```json
{
  "rotulo": "PROVISÓRIO: caminhos do mapa aberto (OpenStreetMap), ainda não conferidos a pé. Só para demonstração.",
  "provisorio": true,
  "atribuicao": "Dados de mapa © contribuidores do OpenStreetMap (ODbL).",
  "perfil": "sem_restricao",
  "origem": {"id": 2, "nome": "Passagem entre os Prédios 6 e 24", "latitude": -23.5469, "longitude": -46.6517},
  "destino": {"id": 3, "nome": "Entrada do Prédio 29", "latitude": -23.5476, "longitude": -46.6517},
  "distancia_m": 182.4,
  "custo": 310.2,
  "acessivel_cadeirante": false,
  "avisos": ["O caminho tem escada (cerca de 20 metros).", "Há trecho ainda não conferido a pé."],
  "aviso_seguranca": "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade.",
  "trechos": [{"ordem": 1, "aresta_id": 18, "tipo": "calcada", "comprimento_m": 13.2,
               "acessivel_cadeirante": null, "fonte_verificacao": "provisorio"}],
  "instrucoes": [{"ordem": 1, "texto": "Siga pelo caminho por cerca de 15 metros."}],
  "geometria": {"type": "LineString", "coordinates": [[-46.65176, -23.54705], [-46.65186, -23.54697]]}
}
```

- `distancia_m`: soma dos `comprimento_m` (1 casa). `custo`: informativo.
- `acessivel_cadeirante`: `true` se todos os trechos são `true`; `false` se algum é `false`
  ou escada; `null` se algum não foi verificado e nenhum é `false`.
- `provisorio = true` se algum trecho tem `fonte_verificacao = "provisorio"`; o `rotulo` muda
  conforme o pior caso (provisório, desenhado sobre mapa, conferido a pé). `atribuicao` só
  aparece com dado do OpenStreetMap.
- `geometria`: trechos concatenados no sentido do caminho, sem repetir o vértice de junção;
  coordenadas `[longitude, latitude]` (Leaflet usa `[latitude, longitude]`).
- `instrucoes`: tipo de trecho + distância aproximada (múltiplos de 5 m) + até 2 referências
  por instrução; escada e travessia são anunciadas antes do trecho; a última é sempre a
  chegada ("Você chegou à entrada do Prédio 31.").

Erros (corpo `{"mensagem": ...}` em português):

| Código | Quando | Corpo |
|---|---|---|
| 422 | JSON malformado, campo ausente, tipo errado, campo extra, `perfil` inválido, `origem_id == destino_id` | `{"mensagem": "Pedido de rota inválido.", "erros": [{"campo": "...", "erro": "..."}]}` |
| 422 | `destino_id` não é entrada; ponto sem nó | `campo: "destino_id"` ("Escolha uma entrada de prédio.") ou `campo` do ponto ("Este ponto ainda não está ligado ao mapa de caminhos.") |
| 404 | `origem_id` ou `destino_id` não existe | `{"mensagem": "Ponto de interesse não encontrado.", "campo": "destino_id"}` |
| 404 | nenhum caminho (inclui cadeirante sem caminho sem escada) | `{"mensagem": "Não há caminho mapeado entre esses dois pontos.", "codigo": "sem_rota"}` |
| 413 | corpo acima de `LIMITE_CORPO_BYTES` | `{"mensagem": "Corpo grande demais: o limite é 16 KiB."}` (pelo nginx, página HTML do nginx) |
| 503 | tabela `arestas` vazia | `{"mensagem": "O mapa de caminhos do campus ainda não foi carregado."}` |

```bash
curl -X POST http://localhost:8000/rotas -H 'content-type: application/json' \
  -d '{"origem_id": 3, "destino_id": 7, "perfil": "cadeirante"}'
```
