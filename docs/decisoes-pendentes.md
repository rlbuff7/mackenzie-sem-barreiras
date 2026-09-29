# Decisões pendentes

Registro dos pontos em aberto (ver CLAUDE.md §11). Enquanto uma decisão estiver
pendente, o código usa um **valor provisório configurável** e a pendência fica
anotada aqui.

Última revisão: 29/09/2026.

## Com a orientadora

| # | Decisão | Valor provisório | Onde está no código | Status |
|---|---|---|---|---|
| 1 | **Escopo de roteamento.** Rotas acessíveis ou só a base de dados que as viabiliza? | Nenhum. Sem pgRouting. | — | Aberto |
| 2 | **Taxonomia** de tipos de barreira | Os 4 tipos do pôster: `calcada_irregular`, `ausencia_rampa`, `degrau`, `obstaculo` | `db/seeds/001_tipos_barreira.sql` | Aberto |
| 3 | **Polígono** da área de estudo | Círculo de 500 m em torno do centroide do campus no OSM (-23.54719, -46.65246), ~0,78 km² | `db/seeds/002_area_estudo.sql` | Aberto |
| 4 | **Calibração** do DBSCAN e da promoção | `eps` = 8 m, `minpoints` = 2, `MIN_CONFIRMACOES` = 3 | `.env` | Aberto. Subsídio (SIMULAÇÃO): `backend/scripts/saida/sensibilidade-semente-42.csv`, gerado por `uv run python -m scripts.analisar_sensibilidade`; leitura abaixo |
| 5 | **Divisão de responsabilidades** entre os integrantes | — | — | Aberto |
| 6 | **Atributos quantitativos** da barreira (altura do degrau, inclinação da rampa) | Não modelados. Só `tipo` + `severidade` (1–3). | — | Aberto (novo) |

Observações:

- **#1 afeta o texto, não só o código.** A hipótese do artigo diz "permitindo o
  cálculo de rotas inclusivas" e o objetivo fala em "consultas de proximidade e
  roteamento". Se o escopo for só a base, esses trechos precisam ser reescritos.
- **#4, análise de sensibilidade (SIMULAÇÃO, dados sintéticos, 29/09/2026).**
  `uv run python -m scripts.analisar_sensibilidade`: semente 42, dispersão de até 3 m,
  `minpoints` = 2. CONTROLE com 20 aglomerados de 2 a 5 sessões distintas, 5 sessões
  repetidas e 40 ruídos; 5 SEQUÊNCIAS de 4 barreiras distintas a 15 m (ver T5). O CSV não
  é versionado; o comando o regera igual.

  **Efeito de `min_confirmacoes`** (controle, eps = 8 m; o status esperado de cada
  grupo segue a regra das sessões):

  | min_confirmacoes | confirmadas obtidas / esperadas | pendentes obtidas / esperadas | acerto dos aglomerados |
  |---|---|---|---|
  | 2 | 20 / 20 | 5 / 5 | 100% |
  | 3 (atual) | 11 / 11 | 14 / 14 | 100% |
  | 4 | 9 / 9 | 16 / 16 | 100% |

  Leitura: com eps adequado, o pipeline aplica a regra exatamente. O que
  `min_confirmacoes` decide é quantas barreiras **reais** ficam pendentes. Dos 20
  aglomerados (todos barreiras reais):
  - com 2, todos são confirmados;
  - com 3, ficam pendentes os 9 que têm 2 sessões;
  - com 4, ficam pendentes 11.

  A sessão repetida (uma pessoa só) fica pendente com qualquer valor ≥ 2. A simulação
  não tem relatos FALSOS vindos de sessões distintas no mesmo lugar, então mostra só o
  custo de subir `min_confirmacoes`, não o benefício. Calibrá-lo exige estimar, com dados
  reais, com que frequência relatos falsos se corroboram. Subir `min_confirmacoes`
  também não corrige um eps pequeno: com eps = 2 m, 20 dos 25 grupos se dividem, e os
  pedaços só trocam de confirmada para pendente.

  **Efeito de eps:**
  - O controle acerta 100% com eps de 8 a 20 m. Abaixo de 5 m (o maior salto dentro de
    um grupo), os grupos se dividem.
  - Na grade, as sequências só ficam 100% separadas com eps = 8 m; a janela medida é de
    cerca de [5; 10,3) m, do maior salto dentro de uma barreira à menor distância entre
    barreiras vizinhas (ver T5).
  - **O eps certo depende do erro de posição dos relatos reais E da distância entre
    barreiras vizinhas de verdade.** Com `--dispersao-metros 6`, eps = 8 m acerta 90%
    dos aglomerados e 55% das barreiras em sequência. Com `--dispersao-metros 10`, os
    aglomerados precisam de eps acima de 16,6 m (o maior salto), e nenhum eps da grade
    separa mais de 20% das barreiras a 15 m.
  - Calibrar com a orientadora e com o erro de GPS medido na coleta de campo (M6), não
    com estes números.
- **#6** vem da Etapa 1 da metodologia do artigo ("atributos quantificáveis
  (altura do degrau, ângulo da rampa)"). Se entrar no escopo, cabe como coluna
  opcional sem quebrar o pipeline.

## Técnicas (equipe)

| # | Decisão | Afeta | Status |
|---|---|---|---|
| T1 | **Como registrar descartes do estágio 1 (`schema_invalido`).** `alertas.geom` é `NOT NULL` e `tipo_id` é FK, então um payload inválido não cabe na tabela. Sem registro, o funil não conta esse estágio. | M1 | **Decidido 28/09:** tabela `alertas_rejeitados` (payload JSONB + erros JSONB) |
| T2 | **Aplicação de migrations.** O `docker-entrypoint-initdb.d` só roda com o volume vazio, então não aplica migrations novas num banco existente. | M1 | **Decidido 28/09:** `db/banco.sh migrar` aplica as pendentes em transação e registra em `schema_migrations`; seeds são upserts reaplicados sempre |
| T3 | **Geração do `sessao_hash`.** Proposta: UUID aleatório no `localStorage` do navegador, gravado como SHA-256 (64 hex). Nenhum IP é armazenado (LGPD). Limitação a declarar no texto: quem limpa o navegador vira uma "sessão nova". | M2 | **Decidido 28/09: D1** — o cliente gera o UUID; o servidor grava só `sha256(uuid)` (`app/validacao/entrada.py::calcular_sessao_hash`), nunca o UUID cru nem IP. |
| T4 | **Reavaliação de ruído.** `ruido_isolado` não pode ser estado final: um alerta isolado hoje pode ganhar vizinhos depois. Alertas novos perto de uma barreira existente também precisam se juntar a ela. | M3 | **Decidido 28/09: D6.** Cada execução do pipeline reconstrói a origem do zero, numa transação com `pg_advisory_xact_lock`: `agrupado`/`ruido_isolado` voltam a `bruto`, as barreiras da origem são apagadas e tudo que não é `descartado` é reagrupado (`app/validacao/pipeline.py::executar_pipeline`). Custo aceito: os ids das barreiras mudam a cada execução. |
| T5 | **Encadeamento do DBSCAN.** Com `eps` = 8 m, alertas a cada ~7 m ao longo de uma calçada viram um único cluster, de comprimento arbitrário. Medir com dados sintéticos e discutir no texto. | M3 | **Medido (SIMULAÇÃO, população `sequencia`, R16): barreiras distintas a 15 m em linha, com dispersão de até 3 m, ficam separadas com eps = 8 m (20 de 20) e começam a se fundir a partir de eps ≈ 10,3 m** (a menor distância entre relatos de barreiras vizinhas). Com eps = 12 m, as 20 barreiras viram 9 (6 fusões, só 3 separadas); com eps = 20 m, cada sequência de 45 m vira UMA barreira (20 → 5), com o centroide no meio. Com dispersão de 6 m, eps = 8 m já funde (11 de 20 separadas); com 10 m, nenhum eps da grade separa mais de 4 de 20. A janela útil de eps vai do maior salto dentro de uma barreira até a distância entre barreiras vizinhas, e fecha quando o erro de posição chega perto da metade dessa distância. **As "0 fusões" das populações de controle são por construção** (grupos a ≥ 4 × eps entre si) **e não podem ser citadas como robustez.** O comportamento está documentado em `app/validacao/clustering.py::rotular_clusters` e num teste (3 alertas a 7 m formam 1 cluster). Falta decidir: como o texto declara essa limitação e se vale alguma mitigação (por exemplo, limitar a extensão de um cluster), fora do escopo atual. |

## Documentos acadêmicos

Achados da revisão de 28/09/2026 (complementa CLAUDE.md §12):

- **IBGE 14,4 × 18,6 milhões.** Os dois números parecem vir de pesquisas
  diferentes: 18,6 mi (8,9%) da **PNAD Contínua 2022** e 14,4 mi (7,3%) do
  **Censo Demográfico 2022**, divulgado em 2025. O pôster usa 14,4 mas cita a
  PNAD nas referências. *Conferir na fonte* e padronizar.
- **"1 em cada 7 / 1 bilhão"** (resumo do artigo) é o dado da OMS de 2011, e está
  sem citação. O relatório da OMS de 2022 fala em 1,3 bilhão (1 em cada 6).
- **Falta citar o DBSCAN** (Ester et al., 1996), que é o núcleo técnico.
  Candidatos para substituir o bloco fora de escopo: Goodchild & Li (2012) sobre
  qualidade de VGI; Senaratne et al. (2017), revisão de métodos de qualidade em
  VGI; Saha et al. (2019), Project Sidewalk; Guttman (1984), R-Tree; Hellerstein
  et al. (1995), GiST.
- **Funil do pôster (250 → 205 → 120 → 120):** a unidade muda de *alertas* para
  *barreiras* no estágio de agrupamento, e o funil não mostra ruído nem
  pendentes. A versão final deve deixar a unidade explícita.
- **Cronograma** (agosto a maio) não corresponde ao calendário real do TCC II.
- Menores: os títulos diferem entre pôster e artigo; o resumo termina com ".."; o
  `.doc` guarda metadados de outro documento.
