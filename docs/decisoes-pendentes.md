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
- **#4, análise de sensibilidade (SIMULAÇÃO, dados sintéticos, 29/09/2026).** Semente 42,
  20 aglomerados e 5 sessões repetidas de 4 relatos, 40 ruídos, `minpoints` = 2. O CSV
  não é versionado; o comando acima o regera igual. Com dispersão de até 3 m (padrão):

  | eps (m) | confirmadas obtidas / esperadas (min_conf 2 · 3 · 4) | acerto dos aglomerados | grupos fragmentados | fusões | ruído → barreira |
  |---|---|---|---|---|---|
  | 2 | 23 · 6 · 1 / 20 | 5% | 23 de 25 | 0 | 0 |
  | 4 | 21 · 19 · 18 / 20 | 90% | 2 de 25 | 0 | 0 |
  | 8, 12, 20 | 20 · 20 · 20 / 20 | 100% | 0 | 0 | 0 |

  Leitura: eps menor que o maior salto dentro de um grupo (4,3 m nesta simulação) divide
  o grupo. Com `min_confirmacoes` = 2, os pedaços viram barreiras confirmadas duplicadas
  (23 para 20 reais). Com 3 ou 4, os pedaços caem para `pendente`. Subir
  `min_confirmacoes` não corrige um eps pequeno: troca duplicatas por pendentes. Com eps
  certo, `min_confirmacoes` de 2 a 4 não muda nada aqui, porque todo aglomerado tem 4
  sessões e toda sessão repetida tem 1. **O eps certo depende do erro de posição dos
  relatos reais.** Na mesma análise com `--dispersao-metros 10`, eps = 8 m acerta só 30%
  dos aglomerados (16 de 25 grupos divididos) e eps = 20 m acerta 100%; com
  `--dispersao-metros 6`, eps = 8 m acerta 90%. Calibrar com a orientadora e com o erro de
  GPS medido na coleta de campo (M6), não com estes números.
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
| T5 | **Encadeamento do DBSCAN.** Com `eps` = 8 m, alertas a cada ~7 m ao longo de uma calçada viram um único cluster, de comprimento arbitrário. Medir com dados sintéticos e discutir no texto. | M3 | Aberto. Comportamento documentado em `app/validacao/clustering.py::rotular_clusters` e num teste (3 alertas a 7 m um do outro formam 1 cluster). **Medido na Task 4 (SIMULAÇÃO):** 0 fusões em todas as 15 combinações da grade (eps até 20 m), também com dispersão de 6 e 10 m. Motivo: os grupos sintéticos são compactos e separados por ≥ 4 × eps (32 m), e a menor distância real entre grupos do mesmo tipo foi 44,9 m (o script imprime essas distâncias de referência). Ou seja, as populações atuais não exercitam o encadeamento ao longo de uma calçada: o efeito de eps que elas medem é o oposto, a fragmentação (ver #4). Falta decidir: declarar o encadeamento no texto como propriedade do DBSCAN, com o teste como evidência, ou criar uma população linear (relatos em sequência ao longo de uma calçada) para medi-lo. |

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
