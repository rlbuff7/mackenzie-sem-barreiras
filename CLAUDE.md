# CLAUDE.md — Mackenzie sem Barreiras

Contexto permanente do projeto. Leia antes de qualquer tarefa neste repositório.

---

## 1. O que é este projeto

Plataforma de **mapeamento colaborativo de acessibilidade urbana** no entorno da
Universidade Presbiteriana Mackenzie (São Paulo/SP). Voluntários reportam barreiras
físicas (calçada irregular, degrau, ausência de rampa, obstáculo) através de um mapa
web. O sistema **filtra, agrupa e valida** esses reports antes de persistir em banco
espacial.

É um TCC de graduação (FCI/Mackenzie). TCC I entregou a fundamentação teórica e o
desenho de arquitetura. TCC II é a entrega do software funcionando.

### Contribuição técnica central

O diferencial acadêmico **não é** o mapa nem o formulário. É a **camada de validação**
que transforma dados ruidosos de crowdsourcing em uma base confiável. Todo código em
`backend/app/validacao/` é o núcleo do trabalho e merece tratamento cuidadoso:
funções pequenas, nomes explícitos, testes, docstrings explicando a decisão.

### Base teórica

Volunteered Geographic Information (VGI), conceito de Goodchild (2007): cidadãos
atuando como sensores urbanos. O contraponto conhecido na literatura (Haklay, 2010;
Liu et al., 2018; Miyata et al., 2021, 2025) é que dado voluntário é ruidoso — daí a
necessidade da validação.

---

## 2. Stack

| Camada | Tecnologia | Observação |
|---|---|---|
| Frontend | TypeScript | Leaflet + OpenStreetMap na fase de protótipo; Google Maps API depois |
| Backend | Python 3.11+ / FastAPI | Pydantic v2 para schemas |
| Banco | PostgreSQL 16 + PostGIS 3.4 | rodando via Docker |
| Infra local | Docker Compose | nada instalado direto na máquina |

**Não troque de stack sem autorização explícita.** Se algo parecer melhor resolvido com
outra ferramenta, sugira em texto e espere confirmação — não implemente.

---

## 3. Estrutura de pastas

```
mackenzie-sem-barreiras/
├── docker-compose.yml       # db + api + frontend
├── .env.example
├── CLAUDE.md
├── README.md
├── .github/
│   ├── workflows/
│   │   └── ci-cd.yml        # M5.1: testes em todo push; publica imagens no GHCR em push na main
│   └── actionlint.yaml      # ignora só o aviso de estilo do `if: false` intencional
├── scripts/
│   └── ponta-a-ponta.sh     # M5: pilha ISOLADA (msb-e2e) + teste E2E por HTTP + down -v sempre
├── db/
│   ├── banco.sh             # ./db/banco.sh {migrar|testar|psql|preparar-teste|zerar-real}
│   ├── init/                # roda 1x com volume vazio: só habilita o postgis
│   ├── migrations/          # SQL numerado, aplicado em ordem (schema_migrations)
│   ├── seeds/               # upserts: tipos de barreira, polígono da área de estudo
│   └── tests/               # testes do schema em SQL, terminam em ROLLBACK
├── backend/
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py        # lê .env, nada hardcoded
│   │   ├── db.py            # pool de conexão
│   │   ├── schemas/         # modelos Pydantic
│   │   ├── routers/         # endpoints HTTP
│   │   └── validacao/       # NÚCLEO DO TCC
│   │       ├── entrada.py       # estágios 1 e 2 na entrada (registrar_alerta)
│   │       ├── mensagens.py     # erros do schema em português
│   │       ├── geofence.py      # estágio 2
│   │       ├── clustering.py    # estágio 3
│   │       ├── pipeline.py      # estágio 4 + execução em lote (D6)
│   │       └── estatisticas.py  # contagens do funil
│   ├── scripts/             # SIMULAÇÃO, figuras e o E2E (§9, M5); a sensibilidade nunca grava
│   │   ├── gerar_dados_sinteticos.py  # 5 populações + teste de eficácia
│   │   ├── analisar_sensibilidade.py  # grade eps × min_confirmacoes
│   │   ├── gerar_figura_funil.py      # docs/figuras/funil-<origem>.svg|png
│   │   ├── ponta_a_ponta.py           # M5: contrato inteiro da API por HTTP (httpx)
│   │   └── saida/                     # JSON e CSV gerados (não versionados)
│   ├── tests/
│   └── pyproject.toml / uv.lock
├── frontend/                 # TypeScript + Vite + Leaflet, sem framework
│   ├── Dockerfile             # M5: node:22-alpine (build) → nginx:alpine (serve dist/)
│   ├── nginx.conf              # SPA + cache dos assets + proxy /api/ → api:8000 (R19, sem CORS); log sem IP
│   ├── index.html
│   └── src/
│       ├── main.ts             # ponto de entrada: liga mapa, formulário, sessão
│       ├── api.ts              # cliente HTTP tipado, um a um com docs/api.md
│       ├── sessao.ts           # sessao_id (UUID) em localStorage (D1)
│       ├── mapa.ts             # Leaflet: tiles OSM, área de estudo, barreiras por bbox
│       ├── formulario.ts       # formulário de envio de alerta
│       ├── estilos.css
│       └── fontes/             # Public Sans (woff2 + OFL), servida pelo próprio frontend
└── docs/
    ├── api.md                 # Contrato da API (fonte única, backend + frontend)
    ├── ci-cd.md               # M5.1: o que cada job do GitHub Actions faz e como usá-lo
    ├── decisoes-pendentes.md  # pendências da §11 + decisões técnicas em aberto
    ├── coleta-em-campo.md     # M6: protocolo de coleta em campo
    ├── figuras/               # figuras geradas pelos scripts (funil)
    └── academico/             # pôster e artigo do TCC I (não é código)
```

Documentos acadêmicos (`.pdf`, `.doc`) ficam **sempre** em `docs/academico/`, nunca
na raiz. A raiz guarda só o que as ferramentas exigem lá (`docker-compose.yml`,
`CLAUDE.md`, `.env*`, `README.md`).

---

## 4. Modelo de dados

### Regra fundamental: duas tabelas, não uma

`alertas` guarda **tudo** que chega com forma válida, inclusive o que foi descartado
depois, com o motivo do descarte. `barreiras` guarda apenas o que sobreviveu à
validação.

Isso é intencional e não deve ser "otimizado". Sem a tabela de brutos não é possível
gerar as estatísticas do funil de validação, que é o resultado empírico que o TCC
precisa apresentar.

Exceção: o payload reprovado no **estágio 1** (schema) não cabe em `alertas`, porque
`geom NOT NULL` e a FK de `tipo_id` o impedem. Ele vai para `alertas_rejeitados`, para
que o funil também conte esse estágio. Decidido em 28/09/2026: preserva as constraints
de `alertas` em vez de afrouxá-las.

### Tabelas

**`tipos_barreira`** — taxonomia em tabela de referência, não em `ENUM` do Postgres.
A lista ainda não está fechada com a orientadora; `ENUM` exigiria migration a cada
alteração.

**`area_estudo`** — polígono do entorno do Mackenzie, `GEOMETRY(Polygon, 4326)`.
É contra ele que o geofence roda.

**`alertas`** (resumo; a fonte da verdade é `db/migrations/001_schema_inicial.sql`)
```sql
id              BIGSERIAL PRIMARY KEY
geom            GEOMETRY(Point, 4326) NOT NULL
tipo_id         INT NOT NULL REFERENCES tipos_barreira(id)
severidade      SMALLINT CHECK (severidade BETWEEN 1 AND 3)
descricao       TEXT
sessao_hash     VARCHAR(64) NOT NULL  -- identifica reports da mesma origem
criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
status          VARCHAR(24) NOT NULL DEFAULT 'bruto'
motivo_descarte VARCHAR(48)
barreira_id     BIGINT REFERENCES barreiras(id)
-- CHECK: status = 'descartado'  <=>  motivo_descarte preenchido
-- CHECK: status = 'agrupado'    <=>  barreira_id preenchido
```

`tipo_id` e `sessao_hash` são `NOT NULL` por causa do pipeline: o DBSCAN particiona
por tipo, e `COUNT(DISTINCT sessao_hash)` ignora NULL em silêncio.

Ciclo de vida (`status`):

| status | significado | final? |
|---|---|---|
| `bruto` | passou do schema e do geofence; aguarda o pipeline | não |
| `descartado` | motivo em `motivo_descarte` (ex.: `fora_da_area`) | **sim** |
| `ruido_isolado` | sem vizinhos no DBSCAN | não: é reavaliado quando chegam alertas novos |
| `agrupado` | pertence a um cluster, ligado a `barreira_id` | não |

**`barreiras`** — barreira consolidada, com geometria representativa do cluster
(centroide), tipo, contagem de confirmações e status (`pendente` / `confirmada`).

**`alertas_rejeitados`** — payloads reprovados no estágio 1 (ver exceção acima).
```sql
id           BIGSERIAL PRIMARY KEY
payload      JSONB NOT NULL        -- corpo recebido, como chegou
erros        JSONB NOT NULL        -- erros de validação do schema
recebido_em  TIMESTAMPTZ DEFAULT now()
```

**`execucoes_pipeline`** (migration 003) — uma linha por origem com os parâmetros
(`eps_metros`, `min_pontos`, `min_confirmacoes`, `srid_calculo`) e o `executado_em` da
última execução do pipeline. É de onde as estatísticas leem os parâmetros (§6).

### Índices obrigatórios

```sql
CREATE INDEX idx_alertas_geom   ON alertas   USING GIST (geom);
CREATE INDEX idx_barreiras_geom ON barreiras USING GIST (geom);
```

Nota de nomenclatura para o texto do TCC: o artigo escrito fala em "R-Tree". O PostGIS
implementa indexação espacial via **GiST**. Nos documentos acadêmicos, mencionar R-Tree
como conceito é aceitável, mas o código e a defesa devem dizer GiST.

---

## 5. Armadilha do SRID — leia antes de escrever qualquer query espacial

O banco armazena em **SRID 4326 (WGS84)**, cuja unidade é **grau**, não metro.

Consequências práticas:

- `ST_ClusterDBSCAN(geom, eps, minpoints)` interpreta `eps` na unidade do SRID.
  Passar `eps = 8` significa **8 graus**, algo em torno de 800 km. Erro silencioso:
  não quebra, só agrupa tudo.
- `ST_DWithin` sobre `geometry` em 4326 tem o mesmo problema.

Regra deste projeto:

- **Armazenar** em 4326 (é o que o GPS e o frontend usam).
- **Calcular distância** reprojetando para **SRID 31983** (SIRGAS 2000 / UTM 23S,
  que cobre São Paulo), onde a unidade é metro:
  `ST_Transform(geom, 31983)`.
- Alternativa aceita para distâncias simples: cast para `geography`, que calcula em
  metros — mas `ST_ClusterDBSCAN` não aceita `geography`, então para clustering use
  sempre `ST_Transform`.

Qualquer código novo que meça distância deve deixar a unidade explícita no nome da
variável ou em comentário.

---

## 6. Pipeline de validação

Quatro estágios, espelhando o funil apresentado no pôster do TCC I:

1. **Schema** (`schemas/`) — Pydantic rejeita latitude/longitude fora de faixa, tipo
   inexistente, severidade inválida. Descarte com motivo `schema_invalido`, gravado em
   `alertas_rejeitados` (não em `alertas`).
2. **Geofence** (`validacao/geofence.py`) — `ST_Within` contra `area_estudo`. Ponto
   fora do entorno é descartado com motivo `fora_da_area`.
3. **Agrupamento** (`validacao/clustering.py`) — `ST_ClusterDBSCAN` sobre alertas do
   **mesmo tipo**, em geometria reprojetada. Alertas próximos viram um cluster;
   pontos isolados recebem status `ruido_isolado`. Ruído **não é descarte**: esses
   alertas entram de novo em cada execução do pipeline, porque podem ganhar vizinhos.
4. **Promoção** (`validacao/pipeline.py`) — cluster com pelo menos `MIN_CONFIRMACOES`
   alertas de **sessões distintas** vira barreira `confirmada`. Abaixo disso, entra
   como `pendente`.

O estágio 4 usar sessões distintas é importante: impede que uma pessoa sozinha
reportando cinco vezes no mesmo lugar produza uma "confirmação" falsa.

### Execução em lote: reconstrução completa (D6)

Os estágios 1 e 2 rodam na entrada, alerta por alerta. Os estágios 3 e 4 rodam em
lote, em `executar_pipeline` (`POST /validacao/executar?origem=real|simulacao` ou os
scripts de simulação), sempre sobre **uma origem por vez** e numa única transação.
Antes de qualquer SQL, valida a origem e os parâmetros (`eps_metros > 0`, `min_pontos
>= 1`, `min_confirmacoes >= 1`; `ValueError` se não): um valor inválido nunca chega a
apagar barreiras. `Configuracoes` exige as mesmas faixas ao ler o `.env`.

1. `pg_advisory_xact_lock(CHAVE_LOCK_PIPELINE)`: uma segunda execução simultânea
   espera a primeira terminar. O lock é liberado sozinho no commit/rollback de quem
   chamou; as funções de `validacao/` nunca fazem commit.
2. Reset: `agrupado` e `ruido_isolado` da origem voltam a `bruto`; as barreiras da
   origem são apagadas.
3. `rotular_clusters` (DBSCAN) sobre tudo que não é `descartado`.
4. Uma barreira por cluster (tipo, cluster): centroide calculado em `SRID_CALCULO`
   e gravado em `SRID_ARMAZENAMENTO`, `confirmacoes = COUNT(DISTINCT sessao_hash)`,
   status `confirmada`/`pendente`. Os alertas do cluster viram `agrupado`; o ruído
   vira `ruido_isolado`.
5. Upsert em `execucoes_pipeline` com os parâmetros usados e `executado_em`, na mesma
   transação: o estado do funil e os parâmetros que o produziram nunca se separam.

Recalcular tudo, em vez de atualizar só o que mudou, porque no DBSCAN o rótulo de um
alerta depende de todos os outros. Assim o **ruído é reavaliado** a cada execução, um
alerta novo perto de uma barreira entra no cluster dela (T4), e duas execuções
seguidas dão o mesmo resultado. `descartado` nunca é tocado. Custo aceito: os ids das
barreiras mudam a cada execução.

`executar_pipeline` recebe os parâmetros explicitamente (`eps_metros`, `min_pontos`,
`min_confirmacoes`, `srid_calculo`, `srid_armazenamento`). A rota passa os do `.env`;
a análise de sensibilidade passa outros sem mexer no `.env`.

`ST_ClusterDBSCAN` roda com `OVER (PARTITION BY tipo_id ORDER BY id)`. O `ORDER BY id`
torna o resultado reproduzível (numeração dos clusters e destino de pontos de borda
não dependem da ordem física da tabela). Isso foi verificado no PostGIS 3.4.3 e está
coberto por teste.

### Estatísticas do funil

`GET /validacao/estatisticas?origem=real|simulacao` (`validacao/estatisticas.py`)
devolve contagens reais do banco, separadas por unidade:

- `alertas` (conta **alertas**): `recebidos` (= `rejeitados_schema` + linhas de
  `alertas`), `rejeitados_schema` (estágio 1), `descartados` por motivo
  (`fora_da_area` sempre presente, mesmo com 0), `aguardando_pipeline` (`bruto`),
  `ruido_isolado`, `agrupados`. `recebidos` é a soma de todos os outros.
- `barreiras` (conta **barreiras**): `total`, `pendentes`, `confirmadas`.
- `rotulo`: `"SIMULAÇÃO — dados sintéticos"` ou `"Dados reais de campo"` (§9). A
  resposta de `POST /validacao/executar` traz o mesmo `rotulo`.
- `parametros` e `executado_em`: os da **última execução** daquela origem, lidos de
  `execucoes_pipeline`, **não** a configuração atual. Se o `.env` for recalibrado sem
  rodar o pipeline de novo, ou se um script rodar com outros valores, a figura do funil
  continua mostrando os parâmetros que de fato produziram os números. Origem nunca
  processada: ambos `null`.
- `gerado_em`: instante do cálculo (ISO-8601, UTC).
- Tudo sai de **uma única consulta** (um snapshot): em READ COMMITTED, várias consultas
  poderiam misturar o estado de antes e o de depois de uma execução confirmada no meio.

Formato exato em [`docs/api.md`](docs/api.md).

### Parâmetros — sempre em `.env`, nunca no código

```
DBSCAN_EPS_METROS=8
DBSCAN_MIN_POINTS=2
MIN_CONFIRMACOES=3
SRID_ARMAZENAMENTO=4326
SRID_CALCULO=31983
```

Esses valores são **provisórios**, escolhidos para prototipagem. Serão calibrados com
a orientadora e com dados reais. Por isso não podem estar espalhados pelo código.

---

## 7. Contrato da API

Contrato completo (corpos, respostas, códigos HTTP, mensagens exatas):
[`docs/api.md`](docs/api.md). Resumo:

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/saude` | Sobe a API e confere se o banco responde. |
| `GET` | `/tipos-barreira` | Taxonomia ativa, para o formulário do frontend. |
| `GET` | `/area-estudo` | Polígono(s) da área de estudo, em GeoJSON. |
| `POST` | `/alertas` | Recebe report do voluntário. Valida schema + geofence na entrada (estágios 1 e 2). |
| `GET` | `/barreiras?bbox=minLon,minLat,maxLon,maxLat` | Barreiras validadas dentro do retângulo visível do mapa. |
| `POST` | `/validacao/executar` | Roda o pipeline em lote sobre alertas de uma origem (`real`\|`simulacao`). Protegido por `X-Token-Admin`. |
| `GET` | `/validacao/estatisticas` | Contagens do funil: brutos, descartados por motivo, agrupados, confirmados. |

O parâmetro `bbox` é obrigatório em `/barreiras`. O mapa nunca deve pedir o banco
inteiro — é justamente a consulta por bounding box que justifica o índice espacial.

O endpoint de estatísticas alimenta a figura do funil de validação no documento final.
Ele precisa devolver números reais do banco, nunca valores fixos.

---

## 8. Marcos de desenvolvimento

Trabalhe **um marco por vez**. Não antecipe marcos futuros sem pedido explícito.

- **M0** — `docker compose up` sobe Postgres+PostGIS limpo e acessível.
- **M1** — migrations e seeds aplicadas; tabelas, constraints e índices criados.
- **M2** — `POST /alertas` e `GET /barreiras` funcionando.
- **M3** — gerador de dados sintéticos + pipeline completo + endpoint de estatísticas.
  *Ao final do M3 o núcleo científico do TCC está demonstrável.*
- **M4** — frontend com mapa (Leaflet/OSM) e envio de alerta.
- **M5** — integração ponta a ponta.
- **M5.1** — CI/CD: todo push roda os testes (banco, backend, frontend, ponta a
  ponta); push no `main` publica as imagens Docker no GHCR.
- **M6** — coleta real em campo.

---

## 9. Dados sintéticos

`backend/scripts/gerar_dados_sinteticos.py` gera **cinco** populações de CONTROLE (D8),
cada uma com o destino conhecido de antemão, para que o pipeline possa ser avaliado:

| População | O que é | Destino esperado | Estágio que prova |
|---|---|---|---|
| **Aglomerados verdadeiros** (`aglomerado`) | N relatos do mesmo tipo, com dispersão de poucos metros, cada um de uma sessão diferente | 1 barreira `confirmada` por grupo | 3 e 4 |
| **Sessão repetida** (`sessao_repetida`) | UMA sessão relatando N vezes no mesmo lugar | 1 barreira `pendente` por grupo | 4 (sessões distintas) |
| **Ruído isolado** (`ruido`) | relatos únicos, espalhados, sem vizinho do mesmo tipo | `ruido_isolado` | 3 |
| **Fora da área** (`fora_da_area`) | relatos válidos fora do polígono de estudo | `descartado` (`fora_da_area`) | 2 |
| **Inválidos** (`invalido`) | payloads com um defeito cada: latitude fora da faixa, tipo inexistente, severidade 7, campo faltando, campo extra | `alertas_rejeitados` | 1 |

O status esperado de cada grupo segue a regra do estágio 4, escrita à parte do pipeline:
`confirmada` se o grupo tem pelo menos `MIN_CONFIRMACOES` sessões distintas, `pendente` se
não. Um grupo com algum relato reprovado na entrada nunca conta como acerto.

Duas opções de ESTRESSE, desligadas no gerador e ligadas por padrão na análise de
sensibilidade (R16):

- `--sessoes-variaveis`: cada aglomerado sorteia de 2 a 5 sessões distintas, então uns
  passam e outros não passam de `min_confirmacoes`.
- `--sequencias N` (população `sequencia`): linhas retas de `--barreiras-por-sequencia`
  barreiras DISTINTAS do mesmo tipo, a `--espacamento-sequencia-metros` (15 m) umas das
  outras, cada uma com `--pontos-por-aglomerado` sessões. Ficam a 4 × o maior eps usado
  de todo ponto do mesmo tipo fora delas (o DBSCAN agrupa por tipo), então só se fundem
  entre si. Esperado: cada barreira separada. É a
  população que mede o encadeamento (T5).

Regras da geração:

- Todo payload passa por `registrar_alerta(..., origem="simulacao")`, o mesmo caminho de
  `POST /alertas`; nunca inserção direta.
- Centro: centroide do campus (−23.5471938, −46.6524631). Grupos e ruído caem a até
  400 m dele; "fora da área", entre 700 e 1500 m (o polígono provisório tem 500 m).
- Separação mínima de 4 × eps (`DBSCAN_EPS_METROS`): entre os centros de dois grupos
  quaisquer e entre cada ruído e qualquer outro ponto do mesmo tipo (amostragem com
  rejeição). `--dispersao-metros` é o raio MÁXIMO em torno do centro do grupo. Relatos de
  grupos vizinhos ficam a ≥ 4 × eps − 2 × dispersão; os scripts avisam quando isso já
  está ao alcance do eps (dispersão ≥ 1,5 × eps no gerador).
- Os pontos são sorteados em metros num plano local e convertidos para graus pelos raios
  de curvatura do WGS84 na latitude do campus. Erro medido contra `geography`: no máximo
  0,002% a 1,5 km (o teste exige < 0,1%).
- Determinística pela semente (`--semente`, padrão 42). Cada população tem o seu gerador
  aleatório, então mudar a quantidade de uma não move as outras.

Comandos (a partir de `backend/`):

```bash
# gerar + pipeline + teste de eficácia (padrões: 20 aglomerados de 4 relatos, dispersão
# de até 3 m, 5 sessões repetidas, 40 ruídos, 30 fora da área, 10 inválidos)
uv run python -m scripts.gerar_dados_sinteticos --limpar --executar-pipeline --avaliar

# análise de sensibilidade: eps ∈ {2, 4, 8, 12, 20} m × min_confirmacoes ∈ {2, 3, 4},
# com --sessoes-variaveis e 5 sequências por padrão
uv run python -m scripts.analisar_sensibilidade

# figura do funil (matplotlib num grupo opcional)
uv sync --group analise
uv run python -m scripts.gerar_figura_funil --origem simulacao
```

O script reporta quantos pontos de cada categoria gerou, para comparar com o que o
pipeline classificou. Isso é o teste de eficácia do algoritmo. Com `--avaliar`, ele
mostra a matriz categoria → destino final (em alertas), as barreiras esperadas × obtidas
e a taxa de acerto por categoria. Um grupo só conta como acerto se TODOS os seus alertas
estiverem numa mesma barreira, com o status esperado e sem nenhum alerta de fora do grupo.
Com os padrões, o resultado é 100% em cada categoria: é o cenário bem separado de
propósito. **Esses 100% conferem que a implementação está correta; não são evidência de
robustez** (por construção, grupos vizinhos ficam fora do alcance do DBSCAN, e as "0
fusões" do controle não medem nada). A robustez é o que a análise de sensibilidade
mede. Relatório completo em `backend/scripts/saida/simulacao-semente-<N>.json`.

A análise de sensibilidade **não toca o banco** (R18). Numa única transação, desfeita
no fim, ela apaga a simulação existente, gera a sua uma vez e roda cada combinação da
grade num savepoint desfeito. O banco continua como estava antes (normalmente a
simulação canônica do gerador, com a sua linha em `execucoes_pipeline`), então as
estatísticas e a figura nunca mostram a população de estresse, e a ordem em que os
scripts rodam não importa. Ela avalia à parte o controle (efeito de `min_confirmacoes`
em confirmadas × pendentes) e as sequências (barreiras verdadeiras × obtidas, fusões,
por eps). Resultado só no console e em
`backend/scripts/saida/sensibilidade-semente-<N>.csv` (o nome ganha as opções fora do
padrão, para nunca sobrescrever o canônico); leitura dos números em
`docs/decisoes-pendentes.md` (#4 e T5).

A figura (`docs/figuras/funil-<origem>.svg|png`) lê `calcular_estatisticas`. Ela tem um
painel para alertas e outro para barreiras, e a legenda traz os parâmetros da última
execução. Se a origem nunca foi processada, o script recusa desenhar.

`--limpar` apaga só `origem='simulacao'` (alertas, barreiras, rejeitados e a linha de
`execucoes_pipeline`); a análise de sensibilidade faz o mesmo, mas dentro da transação
que desfaz no fim. Nenhum script toca `origem='real'`.

**Regra de honestidade acadêmica:** dado sintético é para desenvolver e testar. Em
qualquer saída, log, gráfico ou documento, deve estar rotulado como simulação. Nunca
apresentar número sintético como resultado de coleta real. No código isso significa:
`origem='simulacao'` em toda linha, descrição "SIMULAÇÃO: …" em todo relato gerado, e o
rótulo "SIMULAÇÃO" no console, no JSON, em cada linha do CSV (coluna `rotulo`) e no título
da figura.

---

## 10. Convenções de código

- Código, nomes de variáveis e comentários em **português**, seguindo o domínio
  (`alerta`, `barreira`, `severidade`). Termos técnicos consagrados ficam em inglês
  (`cluster`, `bbox`, `commit`).
- SQL de migration é **idempotente sempre que possível** (`IF NOT EXISTS`).
- Migrations são **imutáveis** depois de aplicadas. Correção vira migration nova.
- Nenhuma credencial, chave de API ou string de conexão no código ou no Git.
  Tudo via `.env`, com `.env.example` versionado sem valores reais.
- Toda função em `validacao/` tem teste.
- Commits pequenos, mensagem em português, escopo claro.

---

## 11. Decisões ainda pendentes com a orientadora

Não implemente nada que dependa destes pontos sem confirmar antes:

1. **Roteamento.** Pôster e artigo prometem "rotas mais acessíveis", mas a metodologia
   não prevê grafo viário nem pgRouting. Está em aberto se o escopo inclui roteamento
   ou apenas a base de dados que o viabiliza. **Não instale pgRouting por conta
   própria.**
2. **Taxonomia final** de tipos de barreira.
3. **Polígono exato** da área de estudo.
4. **Calibração** de `DBSCAN_EPS_METROS` e `MIN_CONFIRMACOES`.
5. **Divisão de responsabilidades** entre os integrantes.

Enquanto pendente: implemente com valor provisório, deixe configurável, e registre a
pendência em `docs/decisoes-pendentes.md`.

---

## 12. Pendências nos documentos acadêmicos

Registradas aqui porque afetam a coerência entre código e texto:

- **Divergência de dados do IBGE.** O pôster cita 14,4 milhões de pessoas com
  deficiência no Brasil; o artigo cita 18,6 milhões. Ambos atribuem a "IBGE, 2022".
  Precisa ser conferido na fonte e padronizado.
- **Referencial teórico com material fora de escopo.** Há um bloco sobre segmentação
  de lesões de pele com CNN, imagens de satélite na agricultura e câmera de
  profundidade Intel RealSense. Nada disso aparece na metodologia nem no escopo.
  Candidato a remoção ou substituição por literatura de qualidade de dados em VGI.
- **Cronograma apertado** na fase de coleta em campo (TCC II).

---

## 13. Como trabalhar comigo neste repositório

- Antes de criar arquivo novo, verifique se já existe algo equivalente.
- Mudanças em schema do banco: **sempre** via migration, nunca `ALTER` manual.
- Se uma tarefa exigir decisão de escopo listada na seção 11, **pare e pergunte**.
- Ao concluir um marco, rode os testes e resuma em uma frase o que passou a funcionar.
- Prefira a solução mais simples que resolve. Este é um TCC de graduação com prazo,
  não um sistema de produção.
