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
├── docker-compose.yml
├── .env.example
├── CLAUDE.md
├── db/
│   ├── banco.sh             # ./db/banco.sh {migrar|testar|psql|preparar-teste}
│   ├── init/                # roda 1x com volume vazio: só habilita o postgis
│   ├── migrations/          # SQL numerado, aplicado em ordem (schema_migrations)
│   ├── seeds/               # upserts: tipos de barreira, polígono da área de estudo
│   └── tests/               # testes do schema em SQL, terminam em ROLLBACK
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py        # lê .env, nada hardcoded
│   │   ├── db.py            # pool de conexão
│   │   ├── schemas/         # modelos Pydantic
│   │   ├── routers/         # endpoints HTTP
│   │   └── validacao/       # NÚCLEO DO TCC
│   │       ├── geofence.py
│   │       ├── clustering.py
│   │       └── pipeline.py
│   ├── scripts/
│   │   └── gerar_dados_sinteticos.py
│   ├── tests/
│   └── pyproject.toml / uv.lock
├── frontend/
└── docs/
    ├── decisoes-pendentes.md  # pendências da §11 + decisões técnicas em aberto
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

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/alertas` | Recebe report do voluntário. Valida schema + geofence na entrada. |
| `GET` | `/barreiras?bbox=minLon,minLat,maxLon,maxLat` | Barreiras validadas dentro do retângulo visível do mapa. |
| `POST` | `/validacao/executar` | Roda o pipeline em lote sobre alertas com status `bruto`. |
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
- **M6** — coleta real em campo.

---

## 9. Dados sintéticos

`scripts/gerar_dados_sinteticos.py` deve gerar três populações distintas, para que o
pipeline possa ser avaliado:

- **Aglomerados verdadeiros** — N pontos do mesmo tipo, com dispersão de poucos metros,
  vindos de sessões diferentes. Devem virar barreira confirmada.
- **Ruído isolado** — pontos únicos, espalhados, sem vizinhos. Devem ser marcados como
  ruído.
- **Fora da área** — pontos fora do polígono de estudo. Devem ser descartados no
  geofence.

O script precisa reportar quantos pontos de cada categoria gerou, para comparar com o
que o pipeline classificou. Isso é o teste de eficácia do algoritmo.

**Regra de honestidade acadêmica:** dado sintético é para desenvolver e testar. Em
qualquer saída, log, gráfico ou documento, deve estar rotulado como simulação. Nunca
apresentar número sintético como resultado de coleta real.

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
