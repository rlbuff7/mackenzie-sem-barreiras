# E4 — Plano de mapeamento do campus

> **RASCUNHO para revisão da equipe — gerado em 19/10/2026; nada aqui foi aprovado pela orientadora.**
>
> Marcações abertas: **[REF?]** citação nova a localizar; **[CONFERIR IBGE]** dado a conferir na fonte; **[DECIDIR COM A ORIENTADORA]** decisão que não é da equipe. Fonte do escopo: `CLAUDE.md` do escopo novo (14/10/2026) e cartões do Kanban no Notion (lidos em 19/10/2026).

Cartão do Kanban: E4 (prazo 20/10/2026; destino final: `docs/mapeamento-campus.md`). Cartões ligados: "Mapear o primeiro trecho do campus (protótipo)" (Maurício, 23/10), "M2 — Mapear o recorte completo do campus" (Maurício, 11/12), "Diário de campo da medição e do mapeamento" (Maurício, a partir de 30/10).

## 1 Objetivo

Decidir o recorte e o método do mapeamento **antes de sair a campo**. O resultado do mapeamento é o grafo pedonal que o pgRouting consome e a lista de pontos que o módulo de orientação pode citar. É **dado de pesquisa**: versionado em `db/seeds/`, com registro de quem mapeou cada trecho e quando.

## 2 Recorte

- **Dentro:** vias internas, praças, caminhos e acessos entre prédios do campus Higienópolis, até a entrada dos prédios. Nada dentro dos prédios e nada no entorno (decisão de 14/10/2026).
- **Extensão no TCC I:** recorte do campus, não o campus inteiro. Qual recorte: **[DECIDIR COM A ORIENTADORA]** (pendência #4; o Kanban liga o M2 a essa decisão).
- **Primeiro trecho (protótipo do banner).** Um trecho pequeno com 2 ou 3 prédios, suas entradas, uma escada e uma rampa. Proposta da equipe, a confirmar: o entorno dos Prédios 29 e 31, que já têm pontos de controle da medição de GPS (P04 e P05 em `docs/medicao-gps.md`) e fica perto da escadaria externa (P08) e da passagem entre os Prédios 6 e 24 (P03). A escolha final é da equipe; não depende da orientadora.

## 3 O que mapear

Os tipos abaixo são os que a migration 004 aceita hoje (`CHECK`, não `ENUM`; mudar a lista exige migration nova).

**Pontos de interesse** (tabela `pontos_interesse`)

| Tipo (`tipo`) | O que mapear | Campos |
|---|---|---|
| `predio` | Cada prédio do recorte, com o nome usado no campus ("Prédio 31"). | `nome`, `descricao` |
| `entrada` | Cada entrada de prédio; **uma ou mais por prédio**; é o destino das rotas. | `nome`, `descricao`, `acessivel` (`TRUE`/`FALSE`; `NULL` = não verificado) |
| `escada` | Escadas e escadarias externas. | `nome`, `descricao` |
| `rampa` | Rampas. | `nome`, `descricao` |
| `quadra` | Quadras poliesportivas. | `nome`, `descricao` |
| `portao` | Portões de acesso ao campus. | `nome`, `descricao` |

A `descricao` é o texto lido em voz: curta, sem jargão, sem coordenada. **Referências físicas para confirmação** (algo que a pessoa possa perceber com bengala, cão-guia ou audição: mudança de piso, degrau, corrimão, portão, fonte de som, desnível) vão na `descricao` em texto livre, porque a migration 004 não tem coluna própria para isso. Se a equipe quiser campo estruturado, é migration nova (não editar a 004).

**Nós** (tabela `nos`): cruzamentos, bifurcações, extremidades de trecho e **cada entrada de prédio**. O nó que é entrada tem `ponto_interesse_id` apontando para o ponto `entrada`.

**Arestas** (tabela `arestas`): trechos caminháveis entre dois nós.

| Tipo (`tipo`) | Uso |
|---|---|
| `calcada` | Caminho pedonal comum, calçada, passagem. |
| `rampa` | Trecho em rampa. |
| `escada` | Escada ou escadaria (penalidade `PENALIDADE_ESCADA`, provisória 4,0). |
| `travessia` | Travessia de via ou área com circulação de veículos (`PENALIDADE_TRAVESSIA`, provisória 2,0). |

Por aresta: `geom` (LineString em 4326), `origem_id`, `destino_id`, `comprimento_m` (calculado em SRID 31983), `acessivel_cadeirante` (`NULL` = não verificado), `custo` e `custo_inverso` (`-1` se mão única).

**Cuidados de segurança (CLAUDE.md §1).** Todo trecho com escada deve estar mapeado como `escada`, e toda escada citável deve existir como ponto, para que o sistema nunca conduza a pessoa a uma escada "não anunciada". Trecho que não foi percorrido e conferido não deve entrar como confiável; ver "Verificação" abaixo.

## 4 Como mapear

1. **Base de partida: OpenStreetMap.** Desenhar o esboço do grafo sobre a imagem e as vias do OSM e do satélite, como a equipe já fez para as coordenadas de referência dos pontos de controle (`docs/medicao-gps.md`: coordenadas "estimadas por imagens de satélite, não medições topográficas"). Ferramenta de edição e exportação (por exemplo, JOSM, QGIS ou geojson.io): **a equipe escolhe; nenhuma está definida no repositório [REF?]** (citar OSM e a ferramenta escolhida).
2. **Conferência a pé.** Percorrer cada trecho no campus para confirmar o que o satélite não mostra: existência e posição de degraus, escadas, rampas, desníveis, portões e piso, e a **entrada acessível** de cada prédio. É esta caminhada que transforma `acessivel = NULL` em `TRUE` ou `FALSE`.
3. **Diário de campo.** Para cada ida: data, horário, clima, quem foi, aparelhos e ocorrências (cartão do Kanban, Maurício).
4. **Revisão por segunda pessoa** de cada trecho antes de ir para o seed. Quem programou o trecho não é o único a conferir (mesma lógica do teste com vendas, CLAUDE.md §12.1).
5. **Quem valida a classificação de acessibilidade** por perfil (cadeirante, deficiência visual): **[DECIDIR COM A ORIENTADORA]** (pendência #6). Até lá, a equipe marca o que viu e deixa `NULL` o que não verificou.

## 5 Ordem de trabalho

| Etapa | O que | Responsável (Kanban) | Prazo |
|---|---|---|---|
| 1 | Este plano aprovado pela equipe (`docs/mapeamento-campus.md`) | Equipe | 20/10 |
| 2 | **Primeiro trecho** digitalizado em `db/seeds/`: 2 ou 3 prédios, entradas, uma escada e uma rampa. É o que o protótipo do banner (E6) usa. Depende da migration 004 (M1) e do E4 | Maurício | 23/10 |
| 3 | Protótipo funcional: mapa, um destino, rota por pgRouting sobre o primeiro trecho e uma orientação falada (E6) | Rodrigo | 29/10 |
| 4 | Banner pronto para impressão | Equipe | 30/10 (apresentação ~03/11) |
| 5 | Decisão do recorte completo com a orientadora (pendência #4) | Orientadora | reunião de ~27/10 |
| 6 | **Recorte completo (M2):** pontos de interesse, nós e arestas, com tipo, acessibilidade e registro de quem mapeou e quando | Maurício | 11/12 |
| 7 | `GET /pontos-interesse` e `POST /rotas` (M3) sobre o recorte mapeado | Rodrigo | 15/01/2027 |

Risco: se a orientadora definir um recorte maior que o previsto, o M2 (16 h estimadas no Kanban) pode estourar o prazo de 11/12. Registrar no `docs/decisoes-pendentes.md`.

## 6 Como entra no banco

Pelas tabelas da migration 004 (`db/migrations/004_grafo_campus.sql`), em ordem de dependência de chaves:

1. `pontos_interesse`: todos os prédios, entradas, escadas, rampas, quadras e portões;
2. `nos`: vértices do grafo; os que são entradas recebem `ponto_interesse_id`;
3. `arestas`: trechos entre nós, com `comprimento_m` e `custo` calculados em SRID 31983 e depois gravados.

Regras:

- Tudo em **SRID 4326**; comprimento e custo calculados com `ST_Transform(geom, 31983)` por quem insere (CLAUDE.md §5). A 004 não calcula esses campos.
- O mapeamento vira **seeds versionados** em `db/seeds/` (hoje só existem `001_tipos_barreira.sql` e `002_area_estudo.sql`, do escopo antigo; os do campus são arquivos novos). Seeds são reaplicados a cada `migrar` (decisão T2), então precisam ser idempotentes, com identificadores fixos. Confirmar o padrão com o agente de banco antes de escrever.
- A 004 **não tem colunas** para "quem mapeou" e "quando". Opções: (a) comentário de cabeçalho em cada arquivo de seed com autor, data e fonte; (b) migration nova com colunas de proveniência. Escolha: equipe (com o responsável pelo banco). O Kanban exige o registro; a forma está em aberto.
- Não há coluna "trecho verificado" em `arestas`, embora exista `PENALIDADE_TRECHO_NAO_VERIFICADO` no `.env.example`. Hoje o único "não verificado" é `acessivel_cadeirante IS NULL`. A equipe precisa decidir como o cálculo de custo identifica um trecho não verificado (pode exigir migration).
- A lista de `tipo` é `CHECK`: um tipo novo (por exemplo, "passagem coberta") exige migration que troque a constraint.
- Migrations aplicadas são imutáveis; correção vira migration nova.

## 7 Verificação do mapeamento

- Cada prédio do recorte tem pelo menos um nó de entrada ligado a um ponto `entrada`.
- O grafo do recorte é conexo (nenhuma entrada isolada).
- `comprimento_m > 0` e origem diferente de destino (já garantidos por constraints da 004).
- Revisão visual das arestas sobre o OSM, e conferência de amostra a pé por pessoa diferente da que mapeou.
- Dado de campus mapeado manualmente é rotulado como tal (dado de pesquisa) em qualquer saída.

## 8 Para a equipe decidir ao revisar

- Ferramenta de digitalização e formato de troca.
- Primeiro trecho (proposta: Prédios 29 e 31).
- Forma do registro de autoria (seed comentado ou migration).
- Como o custo identifica trecho não verificado.
