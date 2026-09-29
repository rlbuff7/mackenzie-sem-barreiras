# Arquitetura do sistema — rascunho de capítulo

> **RASCUNHO para a equipe revisar e adaptar.** Texto-base para o capítulo de
> arquitetura da monografia. Todo fato sobre o sistema vem do repositório
> (`CLAUDE.md`, `docs/api.md`, `docs/decisoes-de-implementacao.md`, `db/migrations/`,
> código); os identificadores entre parênteses (D1, G6, R19…) estão definidos em
> [`decisoes-de-implementacao.md`](../decisoes-de-implementacao.md) e servem para a equipe
> rastrear cada afirmação; tirá-los da versão final, se a orientadora preferir.
> Referências em [`referencias.md`](referencias.md).

## 1 Visão geral

O sistema Mackenzie sem Barreiras é uma plataforma de informação geográfica voluntária
(*Volunteered Geographic Information*, VGI) no sentido de Goodchild (2007): voluntários
relatam barreiras físicas de acessibilidade no entorno da Universidade Presbiteriana
Mackenzie, e o sistema filtra, agrupa e valida esses relatos antes de publicá-los como
barreiras num mapa. Ele segue a arquitetura em três camadas apresentada no TCC I
(Figura 1 do pôster): uma interface web de coleta e consulta, um servidor com a API e a
camada de validação, e um banco de dados espacial.

```
 Voluntário (navegador)
        │  HTTPS (exigido pela geolocalização do navegador)
        ▼
 ┌───────────────────────────┐   /api/ (mesma origem)   ┌──────────────────────────┐
 │ frontend (nginx)          │ ───────────────────────▶ │ api (FastAPI)            │
 │ TypeScript + Leaflet      │                          │ routers/  schemas/       │
 │ tiles do OpenStreetMap    │ ◀─────────────────────── │ validacao/ (núcleo)      │
 └───────────────────────────┘        JSON / GeoJSON    └────────────┬─────────────┘
                                                                     │ SQL parametrizado
                                                                     ▼
                                                        ┌──────────────────────────┐
                                                        │ db: PostgreSQL 16        │
                                                        │     + PostGIS 3.4        │
                                                        └──────────────────────────┘
```

*Figura X — Componentes e comunicação (serviços do Docker Compose). Fonte: autores.*

Os três componentes rodam como serviços de um único `docker-compose.yml` (`db`, `api`,
`frontend`); nada é instalado diretamente na máquina de quem desenvolve. O navegador só
fala com o `frontend`, que encaminha as requisições `/api/` para a API dentro da rede do
Compose (R19). Assim, para a coleta em campo, basta expor um único endereço HTTPS.

## 2 Componentes

### 2.1 Interface web (frontend)

Aplicação em TypeScript, empacotada com Vite, sem framework, com o mapa desenhado pela
biblioteca Leaflet sobre *tiles* do OpenStreetMap. Suas funções são:

- desenhar a área de estudo (`GET /area-estudo`) e as barreiras validadas dentro do
  retângulo visível do mapa (`GET /barreiras?bbox=…`);
- oferecer o formulário de relato, com os tipos lidos de `GET /tipos-barreira`, e enviá-lo
  a `POST /alertas`;
- gerar, na primeira visita, um identificador de sessão aleatório (UUID) guardado no
  `localStorage` do navegador, enviado com cada relato (D1);
- manter, ao lado do mapa, uma lista focável e sincronizada das barreiras visíveis, como
  alternativa acessível aos marcadores para leitores de tela (R10).

A fonte tipográfica é servida pelo próprio frontend, e não por um serviço externo, para
não expor o IP do voluntário a mais um terceiro (R24). Em produção, o frontend é servido
por um nginx que também faz o encaminhamento `/api/` (R19).

### 2.2 Servidor (backend)

API REST em Python com FastAPI; os corpos de requisição são validados por modelos
Pydantic v2, e o acesso ao banco usa psycopg 3 com SQL parametrizado, sem ORM (G3). Os
parâmetros do método (raio do DBSCAN, mínimo de confirmações, SRIDs) são lidos do arquivo
`.env` e nunca aparecem como literais no código (G7). O contrato completo está em
[`api.md`](../api.md); em resumo:

| Método | Rota | Função |
|---|---|---|
| `GET` | `/saude` | confere se a API e o banco respondem |
| `GET` | `/tipos-barreira` | taxonomia ativa, para o formulário |
| `GET` | `/area-estudo` | polígono da área de estudo, em GeoJSON |
| `POST` | `/alertas` | recebe um relato; aplica os estágios 1 e 2 da validação |
| `GET` | `/barreiras?bbox=…` | barreiras validadas dentro do retângulo pedido, em GeoJSON |
| `POST` | `/validacao/executar` | executa os estágios 3 e 4 em lote; exige o cabeçalho `X-Token-Admin` (D7) |
| `GET` | `/validacao/estatisticas` | contagens do funil de validação |

A camada de validação (`backend/app/validacao/`) é o núcleo do trabalho e está descrita
no capítulo de validação ([`validacao.md`](validacao.md)). Ela é separada das rotas: as
mesmas funções atendem a API e os scripts de simulação, o que garante que os dados
sintéticos passem exatamente pelo caminho dos dados reais.

### 2.3 Banco de dados espacial

PostgreSQL 16 com a extensão PostGIS 3.4. O esquema é criado por *migrations* SQL
numeradas, aplicadas em ordem, cada uma numa transação, e registradas na tabela
`schema_migrations`; depois de aplicada, uma migration não é mais alterada, e toda
correção vira uma migration nova. Os dados de referência (tipos de barreira e polígono da
área) são carregados por *seeds* idempotentes.

### 2.4 Testes, integração e entrega contínuas

Os testes do backend rodam contra um PostGIS real, num banco de teste separado e
recriado a cada execução, sem simular o banco (G8). Um teste ponta a ponta sobe uma pilha
Docker isolada, percorre todo o contrato da API por HTTP e a derruba no fim. No GitHub
Actions, todo *push* executa os testes do banco, do backend, do frontend e o ponta a
ponta; um *push* no ramo principal publica as imagens Docker da API e do frontend
([`ci-cd.md`](../ci-cd.md)).

## 3 Modelo de dados

A decisão central do modelo é manter **duas tabelas**: `alertas` guarda todo relato que
chega com forma válida, inclusive os descartados depois, com o motivo; `barreiras` guarda
apenas o que sobreviveu à validação. A tabela de brutos não é redundância: sem ela não é
possível medir o funil de validação, que é o resultado empírico do trabalho.

| Tabela | Conteúdo | Observações |
|---|---|---|
| `tipos_barreira` | taxonomia (`codigo`, `nome`, `descricao`, `ativo`) | tabela de referência, não `ENUM`, porque a lista ainda não está fechada; tipo aposentado vira `ativo = false` |
| `area_estudo` | polígono da área, `GEOMETRY(Polygon, 4326)` | `CHECK (ST_IsValid(geom))`: um polígono inválido faria o geofence responder errado sem erro |
| `alertas` | ponto (`GEOMETRY(Point, 4326)`), tipo, severidade (1–3), descrição, `sessao_hash`, `criado_em`, `status`, `motivo_descarte`, `barreira_id`, `origem` | `tipo_id` e `sessao_hash` são `NOT NULL` porque o agrupamento particiona por tipo e a contagem de sessões distintas ignoraria nulos |
| `alertas_rejeitados` | corpo recebido e erros (JSONB), `recebido_em`, `origem` | relatos reprovados no estágio 1, que não caberiam nas restrições de `alertas` (T1) |
| `barreiras` | centroide do cluster, tipo, `confirmacoes` (sessões distintas), `status` (`pendente`/`confirmada`), `origem` | recriada a cada execução do pipeline (D6) |
| `execucoes_pipeline` | por origem, os parâmetros e o instante da última execução | as estatísticas leem daqui os parâmetros que produziram os números (R14) |

O ciclo de vida de um alerta é controlado pelo campo `status`, com duas restrições de
integridade: `status = 'descartado'` se e somente se há `motivo_descarte`, e
`status = 'agrupado'` se e somente se há `barreira_id`.

| status | significado | final? |
|---|---|---|
| `bruto` | passou do schema e do geofence; aguarda o agrupamento | não |
| `descartado` | reprovado depois do schema (hoje, só `fora_da_area`) | sim |
| `ruido_isolado` | sem vizinhos no último agrupamento | não: volta a ser avaliado a cada execução |
| `agrupado` | pertence a um cluster, ligado a uma barreira | não |

A coluna `origem` (`real` ou `simulacao`, D2) existe em `alertas`, `alertas_rejeitados` e
`barreiras`. Pela API ela é sempre `real`; só os scripts de simulação gravam `simulacao`.
O pipeline, as estatísticas e a consulta de barreiras sempre filtram por uma única origem,
de modo que um relato sintético nunca confirma um relato real (G10).

**Índices espaciais.** `alertas.geom` e `barreiras.geom` têm índices GiST. A consulta de
`GET /barreiras` usa o operador de sobreposição de retângulos envolventes (`&&`) contra o
`bbox` pedido, que é justamente a operação atendida por esse índice; por isso o `bbox` é
obrigatório e o mapa nunca pede o banco inteiro (e cada resposta tem um limite
configurável de itens). Conceitualmente, trata-se de uma R-Tree (GUTTMAN, 1984): o PostGIS
implementa a R-Tree sobre a GiST, a árvore de busca generalizada de Hellerstein, Naughton
e Pfeffer (1995), como descreve a documentação do PostGIS (POSTGIS PROJECT, [2026b]).
O texto do TCC I fala em "R-Trees"; na defesa, o nome correto do índice criado é GiST.

## 4 Fluxo de um relato

1. O voluntário marca o ponto (pela geolocalização do aparelho, tocando no mapa ou pelo
   centro do mapa),
   escolhe o tipo e, opcionalmente, a severidade e uma descrição; o frontend envia o
   relato com o `sessao_id`.
2. **Estágio 1 (schema), na entrada.** O corpo é validado (faixas de latitude e
   longitude, tipo existente e ativo, severidade de 1 a 3, campos extras proibidos). Se
   reprovado, a API responde 422 com os erros em português, e o corpo recebido vai
   inteiro para `alertas_rejeitados.payload`, com o `sessao_id` cru (R27).
3. **Estágio 2 (geofence), na entrada.** O ponto é testado contra a área de estudo. Dentro
   dela, o alerta é gravado como `bruto`; fora, é gravado como `descartado`, com
   `motivo_descarte = 'fora_da_area'`, e a API responde 201 informando o descarte (D4).
   Nos dois casos (relatos aceitos) o servidor grava apenas `sha256(sessao_id)`, nunca o
   identificador cru nem o IP (D1).
4. **Estágios 3 e 4, em lote.** `POST /validacao/executar` agrupa os alertas não
   descartados e cria as barreiras, `pendente` ou `confirmada`.
5. O mapa pede `GET /barreiras` com o retângulo visível e mostra as barreiras com o seu
   status e número de confirmações.

Os estágios 1 e 2 dependem só do próprio relato e, por isso, rodam um a um. Os estágios 3
e 4 só fazem sentido sobre o conjunto: um relato só se confirma na presença de outros.

## 5 Decisões de projeto

| Decisão | Alternativa descartada | Motivo |
|---|---|---|
| Armazenar em SRID 4326 e medir distâncias em 31983 (SIRGAS 2000 / UTM 23S, em metros) (G6) | calcular direto em graus | em 4326 o raio do DBSCAN seria lido em graus e agruparia a cidade inteira sem erro (ver [`validacao.md`](validacao.md)) |
| Taxonomia em tabela | `ENUM` do PostgreSQL | a lista ainda depende da orientadora; `ENUM` exigiria migration a cada mudança |
| Tabela à parte para reprovados no schema (T1) | afrouxar as restrições de `alertas` | preserva `geom NOT NULL` e a chave estrangeira do tipo, e o funil ainda conta o estágio 1 |
| Sessão = `sha256` de um UUID gerado no navegador, sem IP (D1) | IP, conta de usuário | identifica relatos do mesmo aparelho sem dado de identificação direta (LGPD); limitação: limpar o navegador cria uma sessão nova |
| Reconstruir o agrupamento a cada execução (D6) | atualizar só o que mudou | no DBSCAN o rótulo de um alerta depende de todos os outros; recalcular torna o resultado idempotente e reavalia o ruído; custo: os ids das barreiras mudam a cada execução |
| Origem `real`/`simulacao` no próprio dado (D2) | bancos separados | as mesmas funções servem aos dois casos, e toda consulta filtra por origem |
| Gravar os parâmetros de cada execução (R14) | ler a configuração atual | a figura do funil nunca mostra parâmetros que não produziram os números |
| Estatísticas numa única consulta (R15) | várias consultas | em READ COMMITTED, consultas separadas poderiam misturar o estado de antes e o de depois de uma execução |
| Frontend e API na mesma origem (R19) | API pública própria, com CORS | um único endereço HTTPS na coleta, sem configuração de CORS |

## 6 Diferenças em relação ao desenho do TCC I

- **Mapa:** o pôster previa a Google Maps API; o protótipo usa Leaflet com *tiles* do
  OpenStreetMap, como previsto para a fase de protótipo no planejamento do TCC II.
- **Índice:** "R-Trees" no artigo; o índice criado é GiST, que implementa a R-Tree no
  PostGIS (seção 3).
- **Vizinho mais próximo:** a Etapa 2 do artigo cita buscas de *Nearest Neighbor*; o
  sistema implementa consulta por retângulo (`bbox`), não por k vizinhos mais próximos.
- **Atributos quantitativos:** a Etapa 1 cita altura do degrau e ângulo da rampa; o
  modelo tem só tipo e severidade (1–3), pendência #6.
- **Roteamento:** não implementado; o sistema entrega a base que o viabilizaria
  (pendência #1).

Todas essas diferenças estão listadas, com sugestão de texto, em
[`revisao-artigo-tcc1.md`](revisao-artigo-tcc1.md).
