# E6 — Protótipo funcional para o banner: plano de implementação

> **Para os agentes que forem executar:** use `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans`. Os passos usam caixas de seleção (`- [ ]`). Cada tarefa é de UM agente; leia a memória dele e o `CLAUDE.md` do escopo novo antes de começar.

**Status:** PLANO para revisão do Rodrigo, escrito em 22/10/2026 pelo agente `backend-api` (consultando o papel do `infra-banco`). Nada aqui foi implementado nem aprovado pela orientadora. Marcação **[DECIDIR COM A ORIENTADORA]** = toca em escopo da §13 do `CLAUDE.md` novo; o plano usa valor provisório configurável.

**Meta:** em 29/10/2026, o endereço da AWS mostra o mapa do campus, deixa escolher origem e destino entre poucos pontos do primeiro trecho mapeado, desenha a rota (laranja `mapa-rota` #d9560f), lista as instruções em texto e as lê em voz.

**Arquitetura:** `POST /rotas` roda `pgr_dijkstra` sobre `arestas` com o custo calculado na hora (comprimento × fator de tipo × fator de verificação, fatores no `.env`) e devolve a geometria em GeoJSON mais instruções em texto. O frontend só desenha e lê em voz (Web Speech API). O primeiro trecho entra por seed SQL gerado de uma planilha do Maurício.

**Stack:** FastAPI + psycopg 3 + pgRouting 3.6.1 (imagem já trocada nas duas pilhas), Vite + TypeScript + Leaflet, `SpeechSynthesis`. Nenhuma dependência nova.

**Fontes:** Kanban (cartões E6, M1, M3, M4, M5, "Mapear o primeiro trecho do campus (protótipo)", E4, "Banner do TCC I com o protótipo", lidos em 22/10/2026); `CLAUDE.md` do escopo novo (§1, §4, §5, §6, §9, §10, §13, §16); `docs/texto-tcc/rascunhos/e4-plano-mapeamento.md`; `db/migrations/004_grafo_campus.sql`, `006_pontos_controle.sql`; `docs/medicao-gps.md`; `docs/api.md`.

## Restrições globais (valem para todas as tarefas)

- Só áreas externas; o destino é sempre a **entrada** de um prédio (`pontos_interesse.tipo = 'entrada'`). Sem salas, sem indoor.
- **Silêncio é melhor que palpite.** Sem caminho mapeado, a API diz que não há (404 `sem_rota`); nunca inventa trecho nem liga ponto a ponto em linha reta.
- Aviso de segurança em toda saída de rota: "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade." E a rota é demonstração do protótipo, não orientação em tempo real.
- **A posição de quem navega nunca é gravada.** No E6 a origem é um ponto de interesse escolhido na lista (`origem_id`), não a posição do aparelho: nem o GPS do celular é lido nesta tela.
- SRID: armazena em 4326; comprimento e distância em 31983 (`ST_Length(ST_Transform(geom, 31983))`). Unidade no nome (`comprimento_m`, `distancia_m`).
- Penalidades e limites vêm do `.env`, nunca do código. `.env.example` sem segredo.
- Dado de campus mapeado à mão é **dado de pesquisa** (registro de quem mapeou e quando). Grafo provisório sai rotulado como provisório em toda saída.
- Migrations aplicadas são imutáveis; mudança de schema = migration nova (a 004 não se edita).
- Agentes não fazem push nem merge; só o Rodrigo, pelo orquestrador. Só `infra-banco` usa Docker.
- Commits pequenos em português, com o trailer do modelo.

## Pontos de atenção (leia antes de começar)

Foram conferidos no código em 22/10/2026 (main `ee4bb15`).

1. **Os seeds rodam em TODO `./db/banco.sh migrar`** (`db/banco.sh:202`, glob `db/seeds/*.sql`), inclusive na pilha E2E, no banco `_teste` do pytest, no CI e na AWS (o timer `msb-atualizar` roda `migrar` a cada imagem nova). Logo o seed do campus tem de ser idempotente e rápido. Decisão do plano: o arquivo começa com `DELETE FROM arestas; DELETE FROM nos; DELETE FROM pontos_interesse;` e reinsere tudo com `id` fixo (a planilha é a fonte da verdade). Nada referencia essas tabelas hoje; se uma tabela futura passar a referenciá-las, esta regra muda.
2. **Os testes do backend rodam num banco que já tem o seed do campus.** Testes de rota inserem o grafo de teste DENTRO da transação da fixture `conexao` (desfeita no fim), com ids altos (900000 em diante) e longe do campus real, e só consultam esses ids. O grafo de teste fica desconectado do real, então o Dijkstra não mistura.
3. **O E2E (`backend/scripts/ponta_a_ponta.py`) roda contra o seed real.** Não fixe ids: o E2E lista `GET /pontos-interesse`, acha origem e destino pelo `nome` e roda a rota.
4. **`arestas.custo` e `custo_inverso` (NOT NULL) são gravados pelo seed só como referência** (`custo = comprimento_m`, `custo_inverso = comprimento_m` ou `-1` se mão única). O custo REAL de rota é calculado em `POST /rotas` a partir de `comprimento_m`, `tipo` e proveniência, para que mudar uma penalidade no `.env` valha sem refazer seed. O `-1` de `custo_inverso` continua sendo o que diz "mão única".
5. **Direção da geometria:** a aresta é gravada de `origem_id` para `destino_id`; ao percorrê-la ao contrário, a geometria precisa de `ST_Reverse`. Sem isso a linha desenhada fica com pedaços invertidos quando há vértices intermediários. Teste obrigatório.
6. **GeoJSON é `[longitude, latitude]`; Leaflet é `[latitude, longitude]`.** O frontend inverte na entrada (função pura com teste).
7. **Numeração de migration:** a próxima é a `009`. Há branches não mescladas que podem ter migration nova (o `infra-banco` confere `ls db/migrations` na main no dia, antes de criar).

## 1. Mínimo demonstrável até 29/10

### Entra (o que aparece no banner e na demonstração)

| # | O que o visitante vê | Onde |
|---|---|---|
| 1 | Mapa do campus (tiles OSM) com os marcadores dos pontos do primeiro trecho (portão, entradas dos prédios, escada, rampa), rotulados em lista também | `index.html` |
| 2 | Dois seletores rotulados, **De** e **Para** (lista dos pontos; o mapa não é a única forma, §10), mais o perfil "Sem restrição" / "Cadeirante" | `index.html` |
| 3 | Botão **Traçar rota**: chama `POST /rotas`; rota desenhada em laranja com contorno branco; mapa enquadra a rota | `index.html` |
| 4 | Resumo (distância, "contém escada", "acessível para cadeirante: sim/não/não verificado") e lista numerada de instruções em texto (`aria-live="polite"`) | `index.html` |
| 5 | Botão **Ler em voz alta** / **Parar**: lê o aviso de segurança, as instruções e a chegada ("Você chegou à entrada do Prédio 31.") | `index.html` |
| 6 | Rótulo visível quando o dado é provisório: "PROVISÓRIO: grafo esquemático, não conferido a pé" | resposta e tela |

Instruções do E6 dizem **tipo de trecho + distância aproximada + referências citáveis no caminho** (entradas, escadas, rampas que são pontos de interesse) e a chegada. Exemplo: "Siga pela calçada por cerca de 40 metros." / "Atenção: há uma escada no caminho, cerca de 12 metros." / "Você passa pela entrada do Prédio 29." / "Você chegou à entrada do Prédio 31."

### Fica explicitamente para depois (não entra no E6)

| Fora | Marco | Por quê |
|---|---|---|
| "Vire à direita/esquerda", "à sua frente" (rumo, azimute, bússola) | M4 (`orientacao/rumo.py`) | Exige a política de quando falar e o tratamento de rumo indefinido; erro aqui tem consequência física. |
| Posição do usuário em tempo real, map matching, confiança, `PRECISAO_MINIMA_METROS` | M4 | Depende da análise da medição de GPS. |
| `POST /orientacoes`, vibração, disparo automático de mensagem | M4 / M5 | — |
| Origem por GPS ou por coordenada | M3 | Pede decisão de privacidade (não gravar) e do raio de aceitação. |
| Perfil "deficiência visual" | M3 **[DECIDIR COM A ORIENTADORA]** (§13.5 e §13.6: calibração e quem valida a acessibilidade) | No E6 só há dois perfis. |
| Busca textual de destino, `GET /pontos-interesse/{id}`, bbox livre | M3 / M5 | O E6 usa lista fixa do trecho. |
| Recorte completo do campus | M2 (Maurício, 11/12) **[DECIDIR COM A ORIENTADORA]** (§13.4) | — |
| Teste com VoiceOver e TalkBack em celular de verdade | M5 | No E6 só se confere o fluxo com leitor de tela ligado em um aparelho (tarefa F3). |
| Offline / PWA | §13.3 **[DECIDIR COM A ORIENTADORA]** | — |

Frase honesta para o banner e a demonstração: "Protótipo demonstrativo sobre um trecho piloto. Não é orientação em tempo real."

## 2. Dados: o primeiro trecho entra no banco

### 2.1 Recorte proposto (decisão da equipe, não da orientadora)

Entorno dos Prédios 29 e 31 (rascunho E4 §2): pontos de controle **P04** (entrada do 29), **P05** (entrada do 31), **P03** (passagem entre 6 e 24) e **P08** (início da escadaria externa), todos em `docs/medicao-gps.md` com coordenada de referência. Mínimo do card do Maurício: 2 ou 3 prédios, entradas, **uma escada e uma rampa**. Meta de tamanho: 8 a 12 nós, 8 a 14 arestas, 6 a 9 pontos de interesse. Conferência: tem de existir **pelo menos um caminho sem escada** e **um caminho só com escada** entre algum par, senão o perfil "cadeirante" não tem o que mostrar.

### 2.2 Formato que o Maurício entrega (até 23/10)

Uma planilha com **3 abas** (exportadas como CSV UTF-8, separador vírgula, ponto decimal). Cada linha vira uma linha de banco. Coordenadas em graus decimais (latitude, longitude) como no `docs/medicao-gps.md`, 6 casas no mínimo.

**Aba `pontos`** (vira `pontos_interesse`)

| Coluna | Obrigatória | Valores / regra |
|---|---|---|
| `ponto_id` | sim | inteiro único (1, 2, 3...) |
| `tipo` | sim | `predio`, `entrada`, `escada`, `rampa`, `quadra`, `portao` (lista do `CHECK` da 004) |
| `nome` | sim | como se fala no campus ("Prédio 31", "Entrada do Prédio 31", "Escadaria da rua Piauí") |
| `latitude`, `longitude` | sim | em 4326 |
| `descricao` | sim para `entrada`, `escada`, `rampa` | frase curta para voz; referência física (piso, degrau, corrimão, portão). Sem coordenada, sem jargão |
| `acessivel` | não | `sim`, `nao`, ou vazio = não verificado |
| `fonte` | sim | `conferido_a_pe` ou `imagem` |

**Aba `nos`** (vira `nos`)

| Coluna | Obrigatória | Regra |
|---|---|---|
| `no_id` | sim | inteiro único |
| `latitude`, `longitude` | sim | 4326 |
| `ponto_id` | só nas entradas e portões | liga o nó ao ponto (`nos.ponto_interesse_id`). Todo ponto que pode ser origem ou destino tem de ter nó |

**Aba `arestas`** (vira `arestas`)

| Coluna | Obrigatória | Regra |
|---|---|---|
| `aresta_id` | sim | inteiro único |
| `no_origem`, `no_destino` | sim | ids da aba `nos`, diferentes entre si |
| `tipo` | sim | `calcada`, `rampa`, `escada`, `travessia` |
| `acessivel_cadeirante` | não | `sim`, `nao`, vazio = não verificado. Escada = `nao` |
| `mao_unica` | sim | `nao` (padrão) ou `sim` (só vale de `no_origem` para `no_destino`) |
| `vertices_intermediarios` | não | curvas: `lon lat; lon lat; ...` (longitude primeiro, separados por `;`). Vazio = reta entre os dois nós |
| `fonte` | sim | `conferido_a_pe` ou `imagem` |
| `observacao` | não | texto livre (não vai para a voz) |

Mais, na primeira linha de cada CSV ou numa aba `cabecalho`: `mapeado_por` e `mapeado_em` (data) por aba ou por linha. Isso preenche a proveniência exigida pelo Kanban e pela §17.

Por que planilha e não GeoJSON: o Maurício já entregou os pontos de controle em tabela; GeoJSON exige que os extremos das linhas coincidam exatamente com os nós (erro silencioso comum). **Aceitar GeoJSON do geojson.io só se ele preferir**, e nesse caso o conversor (tarefa D2) ganha um adaptador que encaixa extremos a até 1 m (em 31983) no nó mais próximo.

### 2.3 Migration `009_proveniencia_grafo` (tarefa D1)

Resolve duas pendências do rascunho E4 §6 (quem mapeou/quando; como o custo reconhece "trecho não verificado") com colunas pequenas:

```sql
-- 009: proveniência do mapeamento do campus (dado de pesquisa, CLAUDE.md §17).
ALTER TABLE arestas
    ADD COLUMN IF NOT EXISTS fonte_verificacao VARCHAR(16) NOT NULL DEFAULT 'imagem',
    ADD COLUMN IF NOT EXISTS mapeado_por VARCHAR(60),
    ADD COLUMN IF NOT EXISTS mapeado_em DATE;
ALTER TABLE pontos_interesse
    ADD COLUMN IF NOT EXISTS fonte_verificacao VARCHAR(16) NOT NULL DEFAULT 'imagem',
    ADD COLUMN IF NOT EXISTS mapeado_por VARCHAR(60),
    ADD COLUMN IF NOT EXISTS mapeado_em DATE;
-- CHECK por constraint nomeada (padrão da 004; mudar a lista = migration nova).
ALTER TABLE arestas ADD CONSTRAINT arestas_fonte_valida
    CHECK (fonte_verificacao IN ('conferido_a_pe', 'imagem', 'provisorio'));
ALTER TABLE pontos_interesse ADD CONSTRAINT pontos_interesse_fonte_valida
    CHECK (fonte_verificacao IN ('conferido_a_pe', 'imagem', 'provisorio'));
```

(O `infra-banco` ajusta para ser idempotente de verdade: `ADD CONSTRAINT` não tem `IF NOT EXISTS`; use bloco `DO $$ ... $$` ou confira em `pg_constraint`, como a skill `nova-migration-tcc` manda.)

Significado: `conferido_a_pe` = a equipe percorreu; `imagem` = desenhado sobre satélite/OSM, ainda não conferido (recebe `PENALIDADE_TRECHO_NAO_VERIFICADO`); `provisorio` = esquemático para desenvolvimento (aciona o rótulo PROVISÓRIO na API). Isso **substitui** o uso de `acessivel_cadeirante IS NULL` como "não verificado" que o rascunho E4 sugeria como proxy: acessibilidade e verificação são coisas diferentes.

### 2.4 Validação (conversor e testes SQL)

O conversor (tarefa D2) **recusa gerar o seed** se qualquer item falhar, com mensagem em português apontando aba e linha:

1. Ids únicos; toda referência (`no_origem`, `no_destino`, `ponto_id`) existe.
2. Tipos e `fonte` dentro das listas; `origem ≠ destino`; coordenadas dentro do retângulo do campus (bbox grosseiro em torno de -23.5475, -46.6522, por exemplo ±0,004°; só para pegar latitude/longitude trocadas).
3. `comprimento_m > 0` (calculado em 31983) e **nenhuma aresta com comprimento absurdo** (alerta acima de 150 m: provável nó errado).
4. **Grafo conexo** (uma componente só, tratando mão única como mão dupla para esta checagem; e uma segunda checagem informativa de alcance dirigido).
5. Todo prédio com entrada tem nó; toda `escada` citável como ponto tem aresta `escada` perto (até 5 m) e toda aresta `escada` tem ponto `escada` a até 5 m **(segurança §1: nada de escada não anunciada)**.
6. Toda `entrada` tem `descricao` e `acessivel` preenchido ou explicitamente vazio.

O teste SQL (`db/tests/test_schema.sql`) repete as invariantes que dá para checar no banco depois do seed: sem aresta órfã, `comprimento_m` bate com `ST_Length(ST_Transform(geom,31983))` (tolerância 0,01 m), cada entrada tem nó, grafo conexo (via `pgr_connectedComponents`, que existe no pgRouting 3.6.1).

### 2.5 Seed gerado

`db/seeds/004_campus_trecho1.sql`, cabeçalho com autor, data e fonte; começa com os três `DELETE`; usa `ST_SetSRID(ST_MakeLine(...))` ou `ST_GeomFromText('LINESTRING(...)', 4326)`; `comprimento_m` calculado no próprio `INSERT ... SELECT` com `ST_Length(ST_Transform(geom, 31983))` (o conversor não calcula; o banco calcula, uma fonte só); termina com `SELECT setval(pg_get_serial_sequence(...), max(id))` para as três sequências. CSVs-fonte versionados em `db/seeds/campus/` (`pontos.csv`, `nos.csv`, `arestas.csv`) para o seed poder ser regenerado e revisado por diff.

### 2.6 Plano B: o mapeamento atrasa

Gatilhos: sem planilha em 24/10 à noite, ou planilha reprovada pelo conversor e sem correção até 26/10 à tarde.

| Opção | O que é | Pode ir ao banner? |
|---|---|---|
| **B1 (preferida): o Rodrigo traça sobre o OSM** | Em 1 a 2 h, no geojson.io ou JOSM sobre o OSM/satélite, o Rodrigo (ou o Rodrigo com o Maurício por chamada) desenha só o recorte de P03, P04, P05, P08 e preenche as 3 abas. Todas as linhas com `fonte = imagem`; escada e rampa só se forem visíveis e conhecidas. | **Sim, rotulado:** "trecho desenhado sobre mapa, ainda não conferido a pé" (a API já devolve o rótulo e aplica `PENALIDADE_TRECHO_NAO_VERIFICADO`). |
| **B2: grafo esquemático de desenvolvimento** | Nós nas coordenadas dos pontos de controle P03, P04, P05, P08 e arestas retas entre eles, **não são caminhos**: servem só para o backend e o frontend andarem em paralelo (já nos testes e em `db/dev/campus_esquematico.sql`, fora de `db/seeds/` para NÃO ser reaplicado em produção). `fonte = provisorio`. | **Só como último recurso**, com o rótulo PROVISÓRIO bem visível na tela, na voz ("trecho provisório de demonstração") e no banner. Nunca como "rota do campus". Decisão do Rodrigo (pergunta 1). |

O B2 também serve de fixture para as tarefas B1 a B4 desde hoje, sem esperar o Maurício (ver dependências).

## 3. Tarefas por agente

Convenções: duração = horas de trabalho do agente; "Pronto quando" = critério verificável. Datas: hoje qui 22/10; sex 23/10 (Maurício entrega); sáb 24 e dom 25 só se o Rodrigo quiser trabalhar; seg 26; ter 27 (reunião com a orientadora, ~27/10); qua 28; qui 29 (prazo do E6). Banner pronto em 30/10, apresentação ~03/11.

### Visão geral e dependências

| ID | Agente | Tarefa | Depende de | Duração | Quando |
|---|---|---|---|---|---|
| D1 | infra-banco | Migration 009 (proveniência) + testes SQL | — | 1,5 h | qui 22 a sex 23 |
| D2 | infra-banco | CSVs de modelo, conversor `csv_para_seed.py` com validações, grafo esquemático B2 (dev) | D1 | 3 h | sex 23 |
| D3 | infra-banco | Gerar e aplicar `004_campus_trecho1.sql` (planilha real do Maurício) e invariantes SQL | D2; **planilha do Maurício** | 1,5 h | seg 26 (sáb 24 se chegar) |
| B1 | backend-api | Config + fator de custo (função pura) | — | 1 h | qui 22 |
| B2 | backend-api | `GET /pontos-interesse` | D1 (coluna `fonte_verificacao`); fixture B2-dev | 1,5 h | sex 23 |
| B3 | backend-api | `POST /rotas` (SQL, geometria, resposta) | B1, D1 | 3 h | sex 23 a seg 26 |
| B4 | backend-api | Instruções em texto (função pura) + integração | B3 | 1,5 h | seg 26 |
| B5 | backend-api | `docs/api.md` + E2E | B3, B4, D3 | 1,5 h | ter 27 |
| F1 | frontend-mapa | Cliente da API, formatação, voz (módulos puros com teste) | contrato (este doc) | 2 h | qui 22 a sex 23 (contra o contrato, sem API) |
| F2 | frontend-mapa | Tela: seletores, rota desenhada, lista, botão de voz, rótulo provisório | F1, B2, B3 | 3 h | seg 26 |
| F3 | frontend-mapa | Acessibilidade e ensaio no aparelho (leitor de tela, voz no Android e no iPhone) | F2, deploy | 1,5 h | qua 28 |
| A1 | aws-implantacao | Conferir pgRouting no banco da AWS e que a próxima atualização aplica 009 e o seed | D1, D3 | 1 h | seg 26 |
| A2 | aws-implantacao | Ensaio HTTPS no celular, QR code, plano de contingência | tudo mesclado | 1,5 h | qua 28 |
| T1 | documentacao-tcc | `docs/mapeamento-campus.md` (E4 aprovado), roteiro de demonstração, texto do banner (limites do protótipo) | D2 (formato) | 2 h | sex 23 a ter 27 |

### Caminho crítico (23/10 → 29/10)

```
Maurício entrega planilha (sex 23)
  -> D3 gera/aplica seed + invariantes (seg 26, 1,5 h)
  -> B5/E2E contra o seed real (ter 27, 1,5 h)
  -> merge no main (Rodrigo) -> CI publica imagens -> timer da AWS atualiza (~1 h; ter 27 à noite)
  -> F3/A2 ensaio no celular com HTTPS (qua 28)
  -> correções e vídeo de contingência (qua 28 à noite, qui 29 manhã)
  -> E6 pronto (qui 29)
```

Folga: **1 dia** (qui 29 até o fim do dia, pois o banner só fecha em 30/10). Tudo o que não depende do mapeamento (D1, D2, B1 a B4, F1, F2 com o grafo esquemático, T1) corre em paralelo de hoje até seg 26, então o atraso do Maurício só empurra D3, B5 e o ensaio. Se a planilha não chegar até sáb 24 à noite, ativar o plano B1 (seção 2.6) no dom 25 ou seg 26 de manhã; com B1 o caminho crítico anda 1 dia e a folga acaba. **Se a planilha chegar depois de ter 27, o B2 rotulado é o que sobra** (decisão do Rodrigo).

Risco paralelo no caminho: o ciclo merge -> CI -> imagem -> timer da AWS (ver seção 6).

### Tarefa D1 — Migration 009 de proveniência (infra-banco)

**Arquivos:**
- Criar: `db/migrations/009_proveniencia_grafo.sql` (SQL da seção 2.3, idempotente).
- Alterar: `db/tests/test_schema.sql` (verificações novas).

**Interfaces:**
- Produz: colunas `arestas.fonte_verificacao`, `arestas.mapeado_por`, `arestas.mapeado_em` e as mesmas em `pontos_interesse`, `CHECK` com `conferido_a_pe | imagem | provisorio`.

- [ ] **Passo 1:** Conferir `ls db/migrations` na main (numeração) e fazer `./db/banco.sh backup` antes de tocar o banco principal; anotar contagens (170 alertas de simulação, 25 barreiras, 10 rejeitados, 0 reais).
- [ ] **Passo 2:** Escrever em `db/tests/test_schema.sql`, falhando antes da migration: as 6 colunas existem; `INSERT` em `arestas` com `fonte_verificacao = 'x'` dá `23514`; o `DEFAULT` é `'imagem'`; reaplicar a migration não dá erro.
- [ ] **Passo 3:** Rodar `./db/banco.sh testar` e ver as verificações novas falharem.
- [ ] **Passo 4:** Escrever a migration (padrão da skill `nova-migration-tcc`).
- [ ] **Passo 5:** `./db/banco.sh migrar && ./db/banco.sh testar` (verde; antes eram 140 ok + as que o main acrescentou); duas vezes seguidas o `migrar` (idempotência); pytest; contagens do banco principal iguais.
- [ ] **Passo 6:** Commit: `banco: migration 009 com proveniência do mapeamento do campus`.

**Pronto quando:** `testar` verde com as verificações novas, `migrar` repetido sem erro, contagens iguais.

### Tarefa D2 — Modelo de planilha, conversor e grafo esquemático (infra-banco)

**Arquivos:**
- Criar (o formato fica descrito em `docs/mapeamento-campus.md`, tarefa T1): `db/seeds/campus/modelo_pontos.csv`, `modelo_nos.csv`, `modelo_arestas.csv` (só cabeçalho e UMA linha de exemplo rotulada `EXEMPLO`).
- Criar: `db/scripts/csv_para_seed.py` (Python da biblioteca padrão; roda com `python3`, sem Docker) e `db/tests/test_csv_para_seed.py` (pytest ou `unittest`; ver como o CI roda os testes de `db/tests/`).
- Criar: `db/dev/campus_esquematico.sql` (B2, fora de `db/seeds/`; carregado à mão com `./db/banco.sh psql < db/dev/campus_esquematico.sql`).

**Interfaces:**
- Produz: `python3 db/scripts/csv_para_seed.py db/seeds/campus/ > db/seeds/004_campus_trecho1.sql`; código de saída 0 só se todas as validações da seção 2.4 passarem; saída de erro em português: `arestas.csv, linha 7: no_destino 12 não existe em nos.csv`.

- [ ] **Passo 1:** Escrever os testes do conversor antes: um conjunto válido pequeno gera SQL com os três `DELETE`, ids fixos e `setval`; casos que devem falhar (cada um num teste): nó órfão, id duplicado, `tipo` inválido, `origem = destino`, grafo desconexo, aresta `escada` sem ponto `escada` a 5 m, coordenada fora do retângulo do campus, latitude/longitude trocadas.
- [ ] **Passo 2:** Rodar e ver falhar.
- [ ] **Passo 3:** Implementar: leitura com `csv`, validações, geração do SQL (strings escapadas com aspas dobradas; **nunca** formatar valor sem escapar), conectividade por busca em largura (mão única tratada como mão dupla), distância ponto-aresta em metros por projeção local (aproximação plana de 31983 não é necessária aqui: usar fórmula equiretangular, suficiente para 5 m a 150 m).
- [ ] **Passo 4:** Escrever `db/dev/campus_esquematico.sql` (nós nas coordenadas de P03, P04, P05, P08 de `docs/medicao-gps.md`; `fonte_verificacao = 'provisorio'`; ids de 800001 em diante para nunca colidir com o seed real; cabeçalho gritando "ESQUEMÁTICO, NÃO SÃO CAMINHOS, SÓ PARA DESENVOLVIMENTO").
- [ ] **Passo 5:** Rodar o conversor sobre o modelo e carregar o SQL gerado num banco temporário (`banco.sh preparar-teste` ou o banco `_teste`), conferindo as invariantes.
- [ ] **Passo 6:** Commit: `banco: conversor de planilha para seed do campus e grafo esquemático de desenvolvimento`.

**Pronto quando:** testes do conversor verdes (todos os casos de falha recusam com mensagem útil), seed gerado a partir do modelo aplica e reaplica sem erro, `db/dev/campus_esquematico.sql` carrega e permite um `pgr_dijkstra` de teste (comando no relatório).

### Tarefa D3 — Seed real do primeiro trecho (infra-banco)

**Arquivos:**
- Criar: `db/seeds/campus/pontos.csv`, `nos.csv`, `arestas.csv` (a planilha do Maurício exportada, sem editar à mão os valores dele; erros voltam para ele).
- Criar: `db/seeds/004_campus_trecho1.sql` (gerado).
- Alterar: `db/tests/test_schema.sql` (invariantes pós-seed).

- [ ] **Passo 1:** Rodar o conversor; se falhar, devolver a mensagem ao Maurício (via Rodrigo) em vez de "consertar" dado de campo.
- [ ] **Passo 2:** Escrever as invariantes pós-seed no `test_schema.sql` (seção 2.4, últimas linhas) e ver falharem antes do seed.
- [ ] **Passo 3:** `./db/banco.sh migrar && ./db/banco.sh testar` verde, duas vezes (idempotência do seed com os `DELETE`).
- [ ] **Passo 4:** Rodar à mão um `pgr_dijkstra` entre as duas entradas e conferir a distância (cálculo independente com `ST_Length` das arestas esperadas); registrar no relatório.
- [ ] **Passo 5:** `./scripts/ponta-a-ponta.sh` e pytest verdes; contagens do banco principal iguais (o seed só mexe em tabelas do grafo).
- [ ] **Passo 6:** Commit: `banco: seed do primeiro trecho do campus (mapeamento do Maurício, 23/10/2026)`.

**Pronto quando:** testes SQL verdes com o seed real, grafo conexo, pgr_dijkstra entre as entradas devolve caminho, sem escada quando existe alternativa com `perfil` cadeirante (verificação na tarefa B3/B5).

### Tarefa B1 — Configuração e fator de custo (backend-api)

**Arquivos:**
- Alterar: `backend/app/config.py` (campos novos), `.env.example`.
- Criar: `backend/app/rotas/__init__.py`, `backend/app/rotas/custo.py`.
- Teste: `backend/tests/test_rotas_custo.py`.

**Interfaces:**
- Produz (`config.py`): `penalidade_escada: float = 4.0`, `penalidade_travessia: float = 2.0`, `penalidade_trecho_nao_verificado: float = 1.5`, `penalidade_proibitiva: float = 1000.0`, `limite_pontos_interesse_por_consulta: int = 500`. Validação `> 0` (e `penalidade_proibitiva >= 100`). Nomes de variável: `PENALIDADE_ESCADA`, `PENALIDADE_TRAVESSIA`, `PENALIDADE_TRECHO_NAO_VERIFICADO`, `PENALIDADE_PROIBITIVA`, `LIMITE_PONTOS_INTERESSE_POR_CONSULTA`.
- Produz (`rotas/custo.py`): `Perfil = Literal["sem_restricao", "cadeirante"]`; `fator_do_trecho(*, tipo: str, acessivel_cadeirante: bool | None, fonte_verificacao: str, perfil: Perfil, config: Configuracoes) -> float` (multiplicador do comprimento).

Regras do fator (provisórias, **[DECIDIR COM A ORIENTADORA]** a calibração, §13.5): `fator = base_do_tipo × fator_verificacao × fator_perfil`, com `base_do_tipo` = 1 (calcada, rampa), `penalidade_escada` (escada), `penalidade_travessia` (travessia); `fator_verificacao` = 1 se `conferido_a_pe`, senão `penalidade_trecho_nao_verificado`; `fator_perfil` = 1 para `sem_restricao`; para `cadeirante`, `penalidade_proibitiva` quando `tipo = escada` ou `acessivel_cadeirante IS FALSE`, e `penalidade_trecho_nao_verificado` adicional quando `acessivel_cadeirante IS NULL`. Perfil que não pode usar escada recebe custo proibitivo, **não exclusão** (§6): a rota nunca fica sem solução em silêncio; se a melhor rota ainda tiver custo proibitivo, a resposta traz o aviso (ver contrato).

- [ ] **Passo 1: teste falhando**

```python
def test_escada_pesa_penalidade_e_rampa_nao(config):
    escada = fator_do_trecho(tipo="escada", acessivel_cadeirante=False,
                             fonte_verificacao="conferido_a_pe", perfil="sem_restricao", config=config)
    rampa = fator_do_trecho(tipo="rampa", acessivel_cadeirante=True,
                            fonte_verificacao="conferido_a_pe", perfil="sem_restricao", config=config)
    assert escada == config.penalidade_escada and rampa == 1.0

def test_cadeirante_em_escada_recebe_custo_proibitivo_e_nao_infinito(config):
    f = fator_do_trecho(tipo="escada", acessivel_cadeirante=False,
                        fonte_verificacao="conferido_a_pe", perfil="cadeirante", config=config)
    assert f >= config.penalidade_proibitiva and f != float("inf")

def test_trecho_nao_conferido_a_pe_pesa_mais(config):
    base = fator_do_trecho(tipo="calcada", acessivel_cadeirante=True,
                           fonte_verificacao="conferido_a_pe", perfil="sem_restricao", config=config)
    nao = fator_do_trecho(tipo="calcada", acessivel_cadeirante=True,
                          fonte_verificacao="imagem", perfil="sem_restricao", config=config)
    assert nao == base * config.penalidade_trecho_nao_verificado
```

- [ ] **Passo 2:** `uv run pytest backend/tests/test_rotas_custo.py -q` e ver falhar (`ImportError`).
- [ ] **Passo 3:** Implementar `custo.py` e os campos em `config.py` (validadores no padrão do arquivo), `.env.example` com os quatro valores provisórios e o comentário "provisório, calibrar com a orientadora".
- [ ] **Passo 4:** Teste de `config.py` (padrão de `test_config.py`): valor `<= 0` é recusado.
- [ ] **Passo 5:** `uv run pytest -q`, `ruff check`, `ruff format --check`; commit `api: configuração e fator de custo das rotas`.

**Pronto quando:** testes verdes, ruff limpo, `.env.example` atualizado.

### Tarefa B2 — `GET /pontos-interesse` (backend-api)

**Arquivos:**
- Criar: `backend/app/routers/pontos_interesse.py`, `backend/app/schemas/ponto_interesse.py` (só se precisar de modelo de query estrito).
- Alterar: `backend/app/main.py` (registrar o router).
- Teste: `backend/tests/test_api_pontos_interesse.py`.

Contrato (coerente com a §9 do `CLAUDE.md` novo e com `GET /barreiras`): `GET /pontos-interesse?bbox=minLon,minLat,maxLon,maxLat[&tipo=entrada,portao]`. `bbox` **obrigatório** (reusar `interpretar_bbox` de `backend/app/routers/barreiras.py:16` e o mesmo formato de 422, `campo: "bbox"`). `tipo` opcional, lista separada por vírgula, cada valor do `CHECK` (422 com `campo: "tipo"` se inválido). Até `LIMITE_PONTOS_INTERESSE_POR_CONSULTA` itens, ordenados por `nome`. 200 GeoJSON `FeatureCollection` (membro extra `rotulo`); cada Feature: `geometry` Point `[lon, lat]` e `properties: {"id", "tipo", "nome", "descricao", "acessivel", "fonte_verificacao", "tem_no": bool}`. `tem_no` diz se o ponto pode ser origem ou destino (o frontend só oferece pontos com `tem_no = true`). Consulta usa o índice GiST: `WHERE geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)`.

- [ ] **Passo 1:** Testes falhando: sucesso (ponto dentro do bbox aparece, fora não), bbox ausente/malformado/min ≥ max (422), `tipo` inválido (422), filtro por `tipo`, limite, ordem por nome, `rotulo` presente, `tem_no`. Os pontos de teste entram na fixture `conexao` com ids ≥ 900000, longe do campus.
- [ ] **Passo 2:** Ver falhar; **Passo 3:** implementar; **Passo 4:** verde + ruff.
- [ ] **Passo 5:** Commit `api: GET /pontos-interesse com bbox obrigatório`.

**Pronto quando:** testes verdes (sucesso, 422, limite); a rota aparece no `/docs` do dev.

### Tarefa B3 — `POST /rotas` (backend-api)

**Arquivos:**
- Criar: `backend/app/schemas/rota.py` (entrada estrita, saída), `backend/app/rotas/caminho.py` (SQL e montagem), `backend/app/routers/rotas.py`.
- Alterar: `backend/app/main.py`.
- Teste: `backend/tests/test_api_rotas.py` e `backend/tests/test_rotas_caminho.py`.

**Interfaces:**
- Consome: `fator_do_trecho` (B1), colunas da 009 (D1).
- Produz: `calcular_caminho(conexao, *, origem_id: int, destino_id: int, perfil: Perfil, config: Configuracoes) -> Caminho | None` (`Caminho` = lista ordenada de trechos com `aresta_id`, `tipo`, `comprimento_m`, `acessivel_cadeirante`, `fonte_verificacao`, `no_de`/`no_para`, `geom_orientada` em GeoJSON, mais os nós percorridos).

**Forma do SQL** (custo calculado na hora; valores numéricos entram por `psycopg.sql.Literal` de `float` vindo do config, nunca texto livre do cliente; o texto da subconsulta do pgRouting é montado em Python a partir de constantes):

```sql
SELECT d.seq, d.node, d.edge, d.cost,
       a.tipo, a.comprimento_m, a.acessivel_cadeirante, a.fonte_verificacao,
       CASE WHEN d.node = a.origem_id THEN a.geom ELSE ST_Reverse(a.geom) END AS geom_orientada
FROM pgr_dijkstra(
        $arestas$ SELECT id, origem_id AS source, destino_id AS target,
                         comprimento_m * <fator_sql> AS cost,
                         CASE WHEN custo_inverso = -1 THEN -1
                              ELSE comprimento_m * <fator_sql> END AS reverse_cost
                  FROM arestas $arestas$,
        %(no_origem)s, %(no_destino)s, directed := true) AS d
JOIN arestas a ON a.id = d.edge          -- a última linha do Dijkstra tem edge = -1 e some no JOIN
ORDER BY d.seq;
```

`<fator_sql>` é o `CASE` equivalente a `fator_do_trecho` escrito em SQL com as penalidades como literais. **Risco de duplicação:** a lógica do fator existe em Python (testável) e em SQL (executada). Para não divergir, o teste `test_fator_sql_igual_ao_python` roda os dois para a mesma tabela de combinações (tipo × acessibilidade × fonte × perfil) e exige igualdade. Alternativa (a preferida se o SQL ficar feio): calcular o fator em Python por aresta, carregar `arestas` do grafo piloto (dezenas de linhas) e passar o custo por `VALUES` na subconsulta. Escolher a que passar nos testes com menos código; registrar a escolha no relatório.

Nó do ponto: `SELECT id FROM nos WHERE ponto_interesse_id = %s` (se houver mais de um nó por ponto, usar o de menor `id` e registrar no relatório; o conversor D2 recusa mais de um nó por ponto, então o caso é raro).

**Contrato HTTP (proposta, vai para `docs/api.md`)**

`POST /rotas`, corpo JSON estrito (`extra="forbid"`, `StrictInt`), até `LIMITE_CORPO_BYTES`:

```json
{"origem_id": 3, "destino_id": 7, "perfil": "sem_restricao"}
```

- `origem_id`: id de um ponto de interesse com nó (entrada ou portão). `destino_id`: id de uma **entrada** (`tipo = 'entrada'`) com nó. `perfil`: `"sem_restricao"` (padrão) ou `"cadeirante"`. (`"deficiencia_visual"` não existe no E6: 422 "Perfil ainda não disponível." **[DECIDIR COM A ORIENTADORA]**.)
- Rota pública, sem token (não grava nada, não recebe posição). Nenhum log do corpo.

200:

```json
{
  "rotulo": "Trecho piloto, desenhado sobre mapa e conferido a pé pela equipe (dado de pesquisa)",
  "provisorio": false,
  "perfil": "sem_restricao",
  "origem": {"id": 3, "nome": "Portão da rua Piauí", "latitude": -23.5478, "longitude": -46.6527},
  "destino": {"id": 7, "nome": "Entrada do Prédio 31", "latitude": -23.5474, "longitude": -46.6515},
  "distancia_m": 182.4,
  "custo": 310.2,
  "acessivel_cadeirante": true,
  "avisos": ["O caminho tem escada (cerca de 12 metros)."],
  "aviso_seguranca": "Apoio à orientação. Nunca substitui a bengala, o cão-guia ou as técnicas de mobilidade.",
  "trechos": [{"ordem": 1, "aresta_id": 5, "tipo": "calcada", "comprimento_m": 40.2,
               "acessivel_cadeirante": true, "fonte_verificacao": "conferido_a_pe"}],
  "instrucoes": [{"ordem": 1, "texto": "Siga pela calçada por cerca de 40 metros."}],
  "geometria": {"type": "LineString", "coordinates": [[-46.6527, -23.5478], [-46.6525, -23.5477]]}
}
```

`distancia_m` = soma de `comprimento_m` (1 casa); `custo` = soma dos custos (informativo, 1 casa). `acessivel_cadeirante`: `true` se todos os trechos são `true`; `false` se algum é `false` ou for escada; `null` se algum não verificado e nenhum `false`. `provisorio` = `true` se algum trecho tem `fonte_verificacao = 'provisorio'`; nesse caso o `rotulo` é "PROVISÓRIO: grafo esquemático, não conferido a pé. Só para demonstração." Se algum trecho é `imagem` (e nenhum provisório), o rótulo diz "desenhado sobre mapa, ainda não conferido a pé". `avisos` inclui: escada no caminho; trecho não verificado; **para `cadeirante`, o aviso "Não há caminho acessível mapeado; este caminho tem trecho que não serve para cadeira de rodas." quando a rota usa custo proibitivo** (sem eliminar a resposta, §6). `geometria` é a concatenação das arestas já orientadas, sem repetir o vértice de junção. Coordenadas na ordem **[longitude, latitude]**.

Erros (todos com corpo `{"mensagem": "...", ...}` em português, no padrão da API):

| Código | Quando | Corpo |
|---|---|---|
| 422 | JSON malformado, campo ausente, tipo errado, campo extra, `perfil` inválido, `origem_id == destino_id` | `{"mensagem": "Pedido de rota inválido.", "erros": [{"campo": "destino_id", "erro": "..."}]}` |
| 422 | `destino_id` existe mas não é entrada, ou o ponto não tem nó | `campo: "destino_id"`, "Escolha uma entrada de prédio." / "Este ponto ainda não está ligado ao mapa de caminhos." |
| 404 | `origem_id` ou `destino_id` não existe | `{"mensagem": "Ponto de interesse não encontrado.", "campo": "destino_id"}` |
| 404 | existe nó nos dois pontos, mas nenhum caminho entre eles | `{"mensagem": "Não há caminho mapeado entre esses dois pontos.", "codigo": "sem_rota"}` (silêncio, sem palpite) |
| 413 | corpo acima de `LIMITE_CORPO_BYTES` | igual ao de `/alertas` (reusar `_ler_corpo_limitado`) |
| 503 | `arestas` vazia (mapa não carregado) | `{"mensagem": "O mapa de caminhos do campus ainda não foi carregado."}` |

Limites: corpo de 16 KiB (padrão da API); resposta é pequena (dezenas de trechos); sem paginação; o Dijkstra roda sobre o grafo inteiro do campus (centenas de arestas no M2, sem problema). Nginx: o `/api/` atual já limita; não precisa de regra nova (conferir com `infra-banco` se o limite de envio por minuto não atrapalha a demonstração em evento; ver risco R7).

- [ ] **Passo 1: testes falhando**, grafo de teste na fixture `conexao` (ids ≥ 900000), em losango: dois caminhos entre A e D, um curto com escada e um longo com rampa.

```python
def test_sem_restricao_pega_o_desvio_quando_a_escada_custa_mais(cliente, grafo_losango):
    r = cliente.post("/rotas", json={"origem_id": grafo_losango.a, "destino_id": grafo_losango.d})
    corpo = r.json()
    assert r.status_code == 200
    assert [t["aresta_id"] for t in corpo["trechos"]] == grafo_losango.caminho_pela_rampa
    assert corpo["distancia_m"] > grafo_losango.comprimento_pela_escada   # prova que desviou

def test_cadeirante_nunca_recebe_escada_se_ha_alternativa(cliente, grafo_losango): ...
def test_cadeirante_sem_alternativa_devolve_rota_com_aviso(cliente, grafo_so_escada): ...
def test_geometria_vem_em_ordem_mesmo_atravessando_aresta_ao_contrario(cliente, grafo_losango_invertido): ...
def test_mao_unica_nao_volta(cliente, grafo_mao_unica): ...   # custo_inverso = -1 -> 404 sem_rota na volta
def test_sem_caminho_devolve_404_sem_rota(cliente, grafo_dois_componentes): ...
def test_destino_que_nao_e_entrada_da_422(cliente, grafo_losango): ...
def test_origem_igual_destino_da_422(cliente, grafo_losango): ...
def test_perfil_deficiencia_visual_ainda_nao_existe(cliente, grafo_losango): ...
def test_corpo_grande_da_413(cliente): ...
def test_trecho_provisorio_marca_rotulo_e_flag(cliente, grafo_provisorio): ...
def test_fator_sql_igual_ao_python(conexao, config): ...
```

Os casos de borda que a §7 pede para a orientação (precisão ruim, usuário parado, fora da rota) não se aplicam a esta rota; o equivalente é "sem caminho", "só escada" e "mão única".

- [ ] **Passo 2:** Rodar e ver falhar. **Passo 3:** Implementar `caminho.py`, `schemas/rota.py`, `routers/rotas.py` (rota `async` lendo o corpo cru em fluxo, como `alertas.py` e `medicoes.py`; erros de validação via `traduzir_erros_da_requisicao`). **Passo 4:** Verde, suíte inteira (`echo $?`), ruff.
- [ ] **Passo 5:** Commit `api: POST /rotas com pgr_dijkstra e custo por tipo, verificação e perfil`.

**Pronto quando:** todos os testes acima verdes; a suíte inteira verde; `echo $?` = 0; a rota aparece no `/docs`; nenhum log nem tabela guarda `origem_id` de forma ligada a pessoa (não há identificador de pessoa na rota).

### Tarefa B4 — Instruções em texto (backend-api)

**Arquivos:**
- Criar: `backend/app/rotas/instrucoes.py`; teste `backend/tests/test_rotas_instrucoes.py`.
- Alterar: `backend/app/rotas/caminho.py` (usa as instruções), `backend/app/schemas/rota.py`.

**Interfaces:**
- Produz: `montar_instrucoes(trechos: list[Trecho], referencias_no_caminho: list[Referencia], destino_nome: str) -> list[str]`.

Regras: agrupa trechos consecutivos do mesmo `tipo`; distância arredondada para múltiplos de 5 m, mínimo "cerca de 5 metros" (a imprecisão é honesta: não promete metragem exata); frases curtas, sem jargão, sem coordenada, sem esquerda/direita; escada e travessia sempre anunciadas **antes** do trecho ("Atenção: há uma escada no caminho, cerca de 12 metros."), nunca depois; referências citáveis são os pontos de interesse com nó no caminho (entradas, escadas, rampas), no máximo 2 por instrução (o texto "Citar tudo é tão ruim quanto não citar nada", §7); a última instrução é sempre a chegada: "Você chegou à entrada do {destino_nome}." Trecho com `fonte_verificacao = 'provisorio'` nunca gera frase direcional; gera "Trecho provisório de demonstração."

- [ ] **Passo 1:** Testes falhando: agrupamento (3 calçadas seguidas viram uma instrução), arredondamento (12 m escada vira "cerca de 10 metros" ou "cerca de 15 metros", escolher a regra e testar os limites 7,4 / 7,5 / 12,5), aviso de escada vem antes, no máximo 2 referências, chegada sempre por último, rota de um trecho só, rota provisória.
- [ ] **Passo 2 a 4:** ver falhar, implementar, verde. **Passo 5:** commit `api: instruções em texto para a rota`.

**Pronto quando:** testes verdes e as frases de uma rota de exemplo coladas no relatório para o Rodrigo ler em voz alta antes do frontend.

### Tarefa B5 — Documentação da API e E2E (backend-api)

**Arquivos:**
- Alterar: `docs/api.md` (nova seção "Escopo novo: `/pontos-interesse` e `/rotas`", e a nota do topo, que hoje diz que essas rotas não existem), `backend/scripts/ponta_a_ponta.py` (bloco novo), `.env.example` (conferir).

- [ ] **Passo 1:** Escrever o bloco do E2E (falhando antes do deploy do seed): `GET /pontos-interesse` com o bbox do campus devolve ≥ 2 entradas com `tem_no`; achar origem e destino pelo **nome** (não por id); `POST /rotas` devolve 200 com `geometria.type == "LineString"`, `distancia_m > 0`, última instrução começa com "Você chegou"; destino que não é entrada dá 422; ponto inexistente dá 404; corpo de 20 KiB dá 413 (pelo nginx a mensagem é HTML do nginx, conferir só o código, como o E2E já faz).
- [ ] **Passo 2:** `./scripts/ponta-a-ponta.sh` (a pilha isolada tem o seed real porque o `migrar` o aplica). O agente de backend só roda se o orquestrador garantir que nenhum outro agente usa Docker.
- [ ] **Passo 3:** Atualizar `docs/api.md` com o contrato da B2 e da B3 acima, tabela de erros e exemplo `curl`.
- [ ] **Passo 4:** Commit `docs: contrato de /pontos-interesse e /rotas; E2E das rotas`.

**Pronto quando:** E2E verde (com `MEDICAO_CODIGO_EQUIPE` e `TOKEN_ADMIN` como na memória do backend), `docs/api.md` bate com a resposta real (conferir um exemplo colado contra a API de dev).

### Tarefa F1 — Módulos puros do frontend (frontend-mapa)

**Arquivos:**
- Criar: `frontend/src/rotas/api.ts` (chamadas `GET /api/pontos-interesse` e `POST /api/rotas`, erros tratados), `frontend/src/rotas/geometria.ts` (GeoJSON `[lon,lat]` para Leaflet `[lat,lon]`) e `geometria.test.ts`, `frontend/src/rotas/voz.ts` (`SpeechSynthesis`) e `voz.test.ts`, `frontend/src/rotas/resumo.ts` (texto do resumo, rótulo provisório) e `resumo.test.ts`.
- Alterar: `frontend/package.json` (script `testar` passa a incluir os arquivos novos).

**Interfaces:**
- Consome: contrato de `POST /rotas` e `GET /pontos-interesse` (seção B3 e B2 deste plano; o frontend trabalha contra o contrato e contra respostas gravadas em fixtures dos testes, sem esperar o backend).
- Produz: `paraLatLng(coordenadas: [number, number][]): [number, number][]`; `montarFalas(rota: RotaResposta): string[]` (aviso de segurança + preâmbulo "Demonstração do protótipo" + instruções + chegada; se `provisorio`, começa com "Trecho provisório de demonstração."); `falar(textos: string[], opcoes): { parar(): void } | null` (`null` se `speechSynthesis` não existe: a tela mostra "Seu navegador não lê em voz alta; use a lista." sem erro); escolha de voz `pt-BR` quando houver, com `lang = "pt-BR"` mesmo sem voz específica.

- [ ] **Passo 1: testes falhando** (`node:test`, como `itens.test.ts`): inversão de coordenadas; `montarFalas` começa pelo aviso de segurança e termina na chegada; `provisorio` muda a primeira fala; `falar` devolve `null` sem `speechSynthesis`; fala em fila (uma `SpeechSynthesisUtterance` por instrução), `parar` chama `cancel`.
- [ ] **Passo 2 a 4:** ver falhar, implementar (lógica separada do DOM; `falar` recebe o objeto de síntese por parâmetro para o teste), `npm run testar`, `npm run verificar`.
- [ ] **Passo 5:** commit `frontend: módulos de rota e voz com testes`.

**Pronto quando:** `npm run testar` e `npm run verificar` verdes.

### Tarefa F2 — Tela de rota (frontend-mapa)

**Arquivos:**
- Alterar: `frontend/index.html` (troca o botão desabilitado "Escolher destino · em novembro" por formulário e área de resultado), `frontend/src/inicio/pagina.ts` (ligações), `frontend/src/inicio/inicio.css` (estilos com os tokens de `tokens.json`; linha da rota `mapa-rota` com contorno `mapa-contorno`, largura `linha-rota`).

Comportamento: ao carregar, `GET /api/pontos-interesse?bbox=<retângulo do campus>`; marcadores para os pontos (decorativos, `aria-hidden`, como os de `marcadores.ts`) e as duas listas `<select>` com `<label>` (De, Para) preenchidas pelo mesmo resultado (só `tem_no = true`; "Para" só entradas); `<fieldset>` do perfil (dois `radio`); botão **Traçar rota** (alvo ≥ 44 px); o resultado vai numa região `role="region"` com `aria-live="polite"` e foco movido para o título do resultado; polilinha laranja; `fitBounds` na rota **sem animação** (`SEM_ANIMACAO` já existe em `pagina.ts`); botão **Ler em voz alta** vira **Parar**; rótulo provisório sempre visível acima do resultado, com ícone + texto (nunca só cor). Erros (404 `sem_rota`, 422, rede) viram frase em português na mesma região, sem alert. Mapa continua não sendo a única forma de completar a tarefa (a lista basta). Se a API falhar, a página inicial continua inteira (como já faz hoje quando o mapa falha).

**Cuidado com o E2E:** a memória do `infra-banco` registra que o E2E confere no `GET /` o título "Navegação Acessível no Campus" e "Aviso de segurança" (e a ausência de "Relatar barreira"); manter esses textos. A linha do botão antigo "Escolher destino · em novembro" **não** é conferida em `backend/scripts/ponta_a_ponta.py` nem no `frontend/src` (conferido por busca em 22/10/2026), então pode sair.

- [ ] **Passo 1:** estrutura HTML + CSS (sem lógica); **Passo 2:** ligar `api.ts`/`geometria.ts`/`voz.ts` em `pagina.ts`; **Passo 3:** `npm run testar`, `verificar`, `build`; a página aparece em `frontend/dist/`; **Passo 4:** conferir com a API de dev (`http://localhost:8081`) com o grafo esquemático B2 carregado; **Passo 5:** commit `frontend: escolher origem e destino, rota desenhada e leitura em voz`.

**Pronto quando:** build verde; no navegador (dev), escolher dois pontos mostra a linha laranja, a lista de instruções, e o botão de voz lê; sem JavaScript de terceiros e sem Google Fonts.

### Tarefa F3 — Acessibilidade e ensaio em aparelho (frontend-mapa, com o Rodrigo)

- [ ] **Passo 1:** Passar a tela no teclado (Tab, Enter, setas nos `select`, foco visível em todo controle, ordem coerente).
- [ ] **Passo 2:** Rodar com VoiceOver (iPhone) ou TalkBack (Android) ligado: ouve o rótulo dos campos, o resultado (aria-live) e o botão de voz sem sobreposição. (O leitor de tela e a voz do botão podem competir; se competirem, o botão de voz avisa "Pare o leitor de tela para ouvir a voz do aplicativo" ou a voz só começa por toque explícito.)
- [ ] **Passo 3:** No iPhone, a voz só começa dentro do toque do botão (`speak` chamado no próprio manipulador de clique, sem `await` antes); conferir. No Android, conferir voz `pt-BR`.
- [ ] **Passo 4:** Tema escuro e alto contraste: a linha laranja contornada de branco continua visível sobre tiles claros (os tiles OSM são sempre claros).
- [ ] **Passo 5:** Registrar o resultado em uma linha no relatório e, se algo falhar, abrir ajuste pequeno (commit `frontend: ajustes da revisão de acessibilidade do E6`).

**Pronto quando:** fluxo completo feito no celular real em HTTPS (a AWS), com anotação do que não funcionou. **Isto não é avaliação de usabilidade**; é conferência técnica.

### Tarefa A1 — Banco da AWS pronto para o E6 (aws-implantacao)

- [ ] **Passo 1:** Conferir no banco de produção da AWS `SELECT pgr_version();` e `SELECT postgis_version();` (a imagem `pgrouting/pgrouting:16-3.4-3.6.1` já está no `docker-compose.prod.yml:23`; confirmar que a EC2 está de fato com ela, não com a imagem antiga em volume herdado).
- [ ] **Passo 2:** Conferir que `./db/banco.sh --prod migrar` aplica a `009` e o seed e é idempotente (rodar duas vezes depois do merge), e que o auto-atualizador (`msb-atualizar.timer`) está ativo.
- [ ] **Passo 3:** `backup` do banco de produção antes da primeira migração com o seed (`./db/banco.sh --prod backup`).
- [ ] **Passo 4:** Relatório com o tempo real entre o merge e a página nova no ar (mede o risco R4).

**Pronto quando:** `pgr_version()` responde na AWS; a `009` e o seed estão aplicados; o tempo de atualização foi medido.

### Tarefa A2 — Ensaio de ponta a ponta na AWS e contingência (aws-implantacao, com o Rodrigo)

- [ ] **Passo 1:** Abrir a URL HTTPS da AWS no celular (Android e iPhone), fazer o fluxo completo, anotar o tempo de resposta de `POST /rotas` (esperado: bem abaixo de 1 s).
- [ ] **Passo 2:** Confirmar que o endereço que vai no **QR code** do banner é o definitivo (Elastic IP + sslip.io, ver a memória do agente): se o IP mudar, o QR vira lixo impresso. Testar o QR impresso em tela e em papel de teste.
- [ ] **Passo 3:** Contingência de apresentação: **gravar um vídeo de tela** (30 a 60 s) e tirar 3 capturas (mapa, rota com escada evitada, lista de instruções) na quinta 29/10, para o caso de falta de internet no evento. Entregar ao Rodrigo e à equipe do banner.
- [ ] **Passo 4:** Confirmar que a AWS Academy Learner Lab não vai ser pausada antes de ~03/11 (limite de sessão e de créditos; a memória do agente tem o procedimento).

**Pronto quando:** fluxo completo no celular por HTTPS; QR testado; vídeo e capturas entregues.

### Tarefa T1 — Documentação (documentacao-tcc)

**Arquivos:**
- Criar: `docs/mapeamento-campus.md` (E4 aprovado pela equipe, a partir de `docs/texto-tcc/rascunhos/e4-plano-mapeamento.md`, com o formato de planilha da seção 2.2 deste plano e a coluna `fonte`).
- Alterar: `README.md` e `docs/decisoes-pendentes.md` (acrescentar pendências: perfil "deficiência visual", como identificar caminho acessível, calibração das penalidades; marcar o que o E6 usou como provisório).
- Criar: roteiro de demonstração de 60 s e texto de "limites do protótipo" para o banner (em `docs/texto-tcc/rascunhos/e6-roteiro-banner.md`, marcado RASCUNHO).

- [ ] **Passo 1:** O agente de documentação **não** mexe em código nem banco; só recebe o formato final de D2 e as frases reais de B4.
- [ ] **Passo 2:** Texto do banner: o que o protótipo faz, o que **não** faz (lista da seção 1, "Fica explicitamente para depois"), e a frase de segurança.
- [ ] **Passo 3:** Registrar o rótulo: "Protótipo demonstrativo sobre um trecho piloto de dado de pesquisa; não é orientação em tempo real."
- [ ] **Passo 4:** Commit `docs: mapeamento do campus (E4), roteiro e limites do protótipo do banner`.

**Pronto quando:** `docs/mapeamento-campus.md` existe e a equipe consegue entregar a planilha só lendo-o; roteiro de 60 s e texto de limites prontos para o Rodrigo revisar.

## 4. Testes e E2E: resumo do que prova o quê

| Camada | O que prova | Onde |
|---|---|---|
| SQL | invariantes do grafo carregado (sem órfã, conexo, `comprimento_m` bate com 31983, entrada com nó, constraint da 009) | `db/tests/test_schema.sql` |
| Conversor | recusa planilha ruim com mensagem útil | `db/tests/test_csv_para_seed.py` |
| Unidade | fator de custo, instruções, geometria, montagem de falas | `backend/tests/test_rotas_custo.py`, `test_rotas_instrucoes.py`; `frontend/src/rotas/*.test.ts` |
| API (PostGIS real) | desvio por rampa, cadeirante sem escada, mão única, sem rota, 422, 404, 413, rótulo provisório, ordem da geometria | `backend/tests/test_api_rotas.py`, `test_api_pontos_interesse.py` |
| E2E (pilha isolada, seed real) | contrato HTTP pelo nginx: lista de pontos, rota, erros, página inicial com os textos de sempre | `backend/scripts/ponta_a_ponta.py` |
| Aparelho real | voz `pt-BR`, VoiceOver/TalkBack, HTTPS, QR | F3 e A2 (manual, registrado) |

Regra de honestidade acadêmica: qualquer número de rota gerado a partir de grafo provisório ou esquemático, em captura, vídeo ou texto, leva o rótulo.

## 5. Estimativa total

Horas de agente: D 6 h, B 8,5 h, F 6,5 h, A 2,5 h, T 2 h = **~25 h**, em paralelo, concentradas entre 22/10 e 28/10. O card do Kanban estima 6 h para o E6 (só a parte do Rodrigo, que revisa, integra e ensaia). Sugestão: **ajustar a estimativa do card para ~10 a 12 h do Rodrigo** (revisão de 5 tarefas, decisões, ensaio no celular, vídeo de contingência).

## 6. Riscos

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| R1 | O Maurício não entrega o primeiro trecho em 23/10 | Sem dado real, só o B2 rotulado | Planilha-modelo e conversor prontos em 23/10 (D2); gatilho do plano B1 (seção 2.6) no sábado 24 à noite; B2 só com rótulo PROVISÓRIO e decisão do Rodrigo |
| R2 | A planilha chega com erro (nó órfão, grafo desconexo, extremo errado) | Atrasa D3 | O conversor devolve linha e coluna; o Rodrigo devolve ao Maurício em uma mensagem; revisão por segunda pessoa (E4 §4) |
| R3 | pgRouting na imagem de produção | Rota não funciona na AWS | Já resolvido nas duas pilhas (`pgrouting/pgrouting:16-3.4-3.6.1`, `docker-compose.prod.yml:23`); A1 confere `pgr_version()` na EC2 de verdade. Risco residual: volume antigo da AWS com extensão `postgis` 3.4.3 e imagem com 3.4.2 (aviso "core procs need upgrade" registrado na memória do `infra-banco`): funciona, mas rodar `SELECT postgis_full_version()` e registrar |
| R4 | Merge para publicar: CI -> imagem no GHCR -> timer da AWS leva tempo, e uma falha de CI trava tudo | Demonstração sem a versão nova | Mesclar até ter 27/10 à noite; A1 mede o tempo real; plano de deploy manual por SSH (já documentado em `docs/implantacao-aws.md`); vídeo de contingência (A2) |
| R5 | Seed reaplicado em toda atualização da AWS apaga dado | Perda de dado do grafo se alguém editar o banco à mão | O grafo só muda por seed (regra do projeto); backup antes da migração (A1); o seed NÃO guarda nada que não esteja nos CSVs versionados |
| R6 | A tela depende de HTTPS para qualquer recurso futuro de posição | No E6 não usa GPS, então não há dependência | Manter assim; a leitura em voz funciona em HTTPS e em `localhost` |
| R7 | Rate limit do nginx e o pico de visitantes no evento (vários celulares na mesma rede) | 429 durante a demonstração | `POST /api/rotas` herda o limite geral de `/api/`; `infra-banco` confere se o limite atual comporta ~10 pessoas em 1 minuto ou abre uma zona própria generosa (proposta, não decide sozinho) |
| R8 | Voz no iPhone só toca dentro do toque do botão; voz `pt-BR` pode faltar | Demo muda de aparelho para aparelho | F3 testa nos dois sistemas; fallback é a lista de instruções (nada existe só na voz) |
| R9 | Instrução sem esquerda/direita parece pobre na demonstração | Percepção fraca do banner | É escolha de segurança (§1) e escopo (M4); o texto do banner explica; o diferencial do TCC é o M4, não o E6 |
| R10 | Numeração `009` colidir com migration de outra branch | CI vermelho | D1, passo 1: conferir a main e as branches abertas antes de numerar |
| R11 | Penalidades e perfis são provisórios | Alguém trata a "melhor rota" como validada | **[DECIDIR COM A ORIENTADORA]** calibração (§13.5) e quem valida acessibilidade (§13.6): o banner e o texto dizem "valores provisórios" |
| R12 | O grafo do E6 é minúsculo (2 prédios) e o Dijkstra "parece trivial" | — | Garantir no recorte pelo menos um par de pontos com dois caminhos (um com escada, um com rampa), para o desvio aparecer (seção 2.1) |

## 7. O que o Rodrigo precisa decidir (no máximo 4)

1. **Plano B se a planilha não chegar até sáb 24/10 à noite:** B1 (você traça sobre o OSM em 1 a 2 h, rotulado "não conferido a pé") ou B2 (grafo esquemático rotulado PROVISÓRIO, só como último recurso)? Recomendação: B1.
2. **Migration 009 de proveniência** (`fonte_verificacao`, `mapeado_por`, `mapeado_em`): aprova? Ela resolve "quem mapeou e quando" e "trecho não verificado" (pendências do E4), mas é migration nova na produção. Recomendação: sim; alternativa sem migration é só comentário no seed, que perde o rótulo PROVISÓRIO na API.
3. **Escopo da fala no banner:** manter E6 sem "vire à direita/esquerda" (só tipo de trecho, distância e referências), deixando rumo para o M4? Recomendação: sim, por segurança e prazo. Se a resposta for não, B4 ganha 3 a 4 h e o risco sobe (**[DECIDIR COM A ORIENTADORA]** a faixa de ângulo de "frente/direita/esquerda", §7).
4. **Planilha (3 abas) ou GeoJSON** para o Maurício? Recomendação: planilha, formato da seção 2.2. Se ele já está desenhando em geojson.io, aceitar GeoJSON e o conversor ganha um adaptador (+1,5 h).

## Revisão de cobertura (feita pelo autor)

- Mínimo demonstrável e o que fica para M3 a M5: seção 1.
- Dados, formato, validação e plano B: seção 2.
- Tarefas por agente, dependências, estimativas, critério de pronto e caminho crítico: seção 3.
- Contrato de `POST /rotas` (e `GET /pontos-interesse`), testes e E2E: B2, B3, B5 e seção 4.
- Riscos e decisões: seções 6 e 7.
- Itens que toquei de escopo e marquei **[DECIDIR COM A ORIENTADORA]**: perfil "deficiência visual", calibração de penalidades, quem valida acessibilidade, recorte completo, offline, faixas de rumo (M4).
