# E2 — Requisitos funcionais (RF01–RF12) e não funcionais (RNF01–RNF10)

> **RASCUNHO para revisão da equipe — gerado em 19/10/2026; nada aqui foi aprovado pela orientadora.**
>
> Marcações abertas: **[REF?]** citação nova a localizar; **[CONFERIR IBGE]** dado a conferir na fonte; **[DECIDIR COM A ORIENTADORA]** decisão que não é da equipe. Fonte do escopo: `CLAUDE.md` do escopo novo (14/10/2026) e cartões do Kanban no Notion (lidos em 19/10/2026).

Cartão do Kanban: E2 (prazo 22/10/2026; depende de E1; destino final: `docs/requisitos.md`). O Kanban pede, para cada requisito, um critério de verificação (como saber que foi atendido).

**Honestidade sobre a origem da lista.** O Kanban e o CLAUDE.md fixam apenas a *quantidade* (12 RF e 10 RNF) e três RNF de acessibilidade (RNF01, RNF02, RNF07, CLAUDE.md §10). O enunciado de cada requisito abaixo é **proposta deste rascunho**, derivada do CLAUDE.md §1–§10, §12 e do Kanban, para a equipe corrigir.

**Como ler a coluna "Componente".** Cada requisito aponta para algo que **existe hoje** na branch (marcado *existe*) ou para o componente previsto no marco M3, M4 ou M5 (marcado *previsto*). Em 19/10/2026 existem apenas a migration 004 (grafo), a 005 (medições de GPS), a página `/medicao.html` e o sistema de design do frontend. Não existem ainda `backend/app/rotas/`, `backend/app/orientacao/`, `/pontos-interesse`, `/rotas` nem `/orientacoes`.

## 1 Requisitos funcionais

| ID | Requisito (proposto) | Componente no sistema | Marco | Critério de verificação (proposto) |
|---|---|---|---|---|
| RF01 | O sistema exibe um mapa 2D do campus com os pontos de interesse (prédios, entradas, escadas, rampas, quadras, portões). | Tabela `pontos_interesse` (*existe*, `db/migrations/004_grafo_campus.sql`); `GET /pontos-interesse?bbox=minLon,minLat,maxLon,maxLat` e mapa Leaflet em `frontend/` (*previstos*) | M3, M5 | Com o recorte mapeado, todos os pontos de interesse seeds aparecem no mapa; a requisição sem `bbox` é rejeitada (422). |
| RF02 | Cada ponto de interesse tem uma descrição própria para leitura em voz. | Coluna `pontos_interesse.descricao` (*existe*); `GET /pontos-interesse/{id}` (*previsto*) | M3 | 100% dos pontos do recorte têm `descricao` preenchida; a API devolve o texto sem coordenadas. |
| RF03 | O usuário escolhe o destino, que é sempre a entrada de um prédio, tocando no mapa. | Nós com `nos.ponto_interesse_id` apontando para uma entrada (*existe* no esquema); seleção no frontend (*previsto*) | M5 | Em teste com o protótipo, é possível escolher qualquer entrada do recorte pelo mapa. Não existe destino do tipo sala. |
| RF04 | O usuário escolhe o destino por busca textual ou lista, sem usar o mapa. | Busca/lista no frontend sobre `GET /pontos-interesse` (*previsto*) | M5 | Toda entrada escolhível no mapa é escolhível por texto, só com teclado e leitor de tela. |
| RF05 | O sistema calcula a rota até a entrada escolhida. | `POST /rotas`, `pgr_dijkstra` sobre `arestas` com `custo`/`custo_inverso` (tabela *existe*, `pgrouting` habilitado na 004; rota *prevista*, `backend/app/rotas/`) | M3 | Para pares origem-destino do recorte, a rota devolvida liga os dois pontos pelas arestas do grafo; teste automatizado em `backend/tests/`. |
| RF06 | O custo da rota considera o tipo do trecho e o perfil do usuário (deficiência visual, cadeirante, sem restrição). Um perfil que não pode usar escada recebe custo proibitivo, não exclusão da aresta. | `arestas.tipo`, `arestas.acessivel_cadeirante` (*existem*); `PENALIDADE_ESCADA`, `PENALIDADE_TRAVESSIA`, `PENALIDADE_TRECHO_NAO_VERIFICADO` em `.env.example` (*existem*); lógica de perfis (*prevista*) | M3 | Rota por rampa é escolhida em vez de rota mais curta por escada para o perfil sem escada; nunca "sem solução" silencioso. Valores das penalidades e critério de acessibilidade por perfil: **[DECIDIR COM A ORIENTADORA]** (pendências #5 e #6). |
| RF07 | A rota é desenhada no mapa. | Frontend Leaflet (*previsto*) | M5 | A linha da rota coincide com as arestas devolvidas por `POST /rotas`. |
| RF08 | O sistema projeta a posição do usuário no caminho mais próximo da rota (*map matching*) e informa o nível de confiança. | `backend/app/orientacao/posicao.py` (*previsto*) | M4 | Testes de borda: precisão ruim, usuário fora da rota. Calibrado com o resultado da medição de GPS. |
| RF09 | O sistema calcula o rumo do usuário e indica se o alvo está à frente, à direita, à esquerda ou atrás. | `backend/app/orientacao/rumo.py` (*previsto*); a decisão "seta ou só bola" já existe no cliente em `frontend/src/mapa/rumo.ts` (*existe*, com teste `rumo.test.ts`) | M4 | Testes cobrem o giro 0°/360° e o usuário parado (rumo indefinido, sem seta). Faixas angulares: **[DECIDIR COM A ORIENTADORA]** (pendência #5). |
| RF10 | O sistema escolhe quais pontos de referência citar (dentro de um raio, à frente, no máximo N por mensagem) e monta a mensagem falada, sem repetir a mesma antes de um intervalo mínimo. | `backend/app/orientacao/referencias.py` e `mensagens.py` (*previstos*); `POST /orientacoes` (*previsto*) | M4 | Testes de política de disparo (sem repetição; aviso de mudança de direção tem prioridade sobre descrição do ambiente). |
| RF11 | A orientação é falada durante o percurso; a vibração complementa o áudio e nunca é o único canal. | Web Speech API (`SpeechSynthesis`) e Vibration API no frontend (*previstos*); a página `/medicao.html` já testa `navigator.vibrate` e a bússola (*existe*, `frontend/src/medicao/pagina.ts`) | M5 | Toda informação dada por vibração também é dada por voz e por texto na tela. No iOS a vibração não existe e o sistema segue funcionando. |
| RF12 | O sistema avisa a chegada à entrada, avisa quando o usuário sai da rota e diz explicitamente que não sabe onde ele está quando a precisão é insuficiente. | `orientacao/mensagens.py` e `posicao.py` (*previstos*); `PRECISAO_MINIMA_METROS` (provisório 15 m; valor final **[DECIDIR COM A ORIENTADORA]**, pendência #1) | M4, M5 | Teste de fim de percurso emite mensagem de chegada; com `accuracy` pior que o limite, nenhuma orientação direcional é emitida. |

## 2 Requisitos não funcionais

| ID | Requisito (proposto) | Componente no sistema | Critério de verificação (proposto) |
|---|---|---|---|
| RNF01 | **Acessibilidade — teclado e leitor de tela.** Conformidade com WCAG 2.2 nível AA **[REF?]**: HTML semântico, foco visível, ordem de tabulação coerente, todo controle alcançável por teclado e rotulado para leitor de tela. | Interface do frontend. *Existe* parcialmente na página de medição (`frontend/medicao.html`: `lang="pt-BR"`, `aria-*`, `role="switch"`) | Percurso completo (escolher destino, iniciar, encerrar) só com teclado; teste manual com VoiceOver (iOS) e TalkBack (Android) em celular de verdade, não só emulador. |
| RNF02 | **Acessibilidade — contraste, cor e alvos.** Contraste mínimo AA (texto 4,5:1; borda de controle, foco e marcadores 3:1); **nunca cor como única forma de transmitir informação**; alvos de toque de pelo menos ~44 px. | *Existe:* tokens de design `frontend/src/design/tokens.json` e `tokens.css`, com teste de contraste `frontend/src/design/contraste.test.ts` (três temas, inclusive alto contraste) | O teste de contraste passa em CI; revisão manual de que cada estado (rota, erro, fora da rota) tem também texto ou ícone. |
| RNF03 | **Desempenho de `POST /orientacoes`.** A rota é chamada repetidamente durante a navegação, então precisa ser barata; se virar gargalo, o caminho é cache no cliente. | `backend/app/routers/` (*previsto*) | Tempo de resposta medido sobre o recorte e registrado; valor-alvo a definir pela equipe **(sem número no CLAUDE.md)**. |
| RNF04 | **Privacidade — posição de quem navega nunca é gravada.** O servidor usa a posição para responder e a descarta; não há tabela, log ou arquivo com a trilha de quem navega. | A migration 005 (`medicoes_gps`, *existe*) guarda apenas medições **da equipe** nos pontos de controle, sem nome de pessoa; a regra do M4 proíbe gravar a posição de quem navega | Revisão do esquema (nenhuma coluna de posição de usuário em tabela de navegação) e dos logs da API; termo de consentimento cita que a AWS (ou a Cloudflare, no plano B) recebe o IP de quem usa o protótipo. |
| RNF05 | **Segurança de orientação — silêncio é melhor que palpite.** Sem precisão suficiente, o sistema diz que não sabe; nenhuma orientação empurra o usuário para a via, para escada não anunciada ou trecho não mapeado. Número de orientações erradas emitidas é métrica crítica da avaliação. | `orientacao/posicao.py` e `mensagens.py` (*previstos*); regra já aplicada no cliente em `frontend/src/mapa/rumo.ts` (*existe*) | Casos de borda testados (precisão ruim, parado, fora da rota, fim do percurso); na avaliação, contagem de orientações erradas; orientação perigosa interrompe a sessão e é registrada como falha grave. A frase do princípio aparece na interface. |
| RNF06 | **Custo zero.** Sem chave paga nem cartão: tiles OpenStreetMap, pgRouting no próprio banco, Web Speech API e APIs do navegador. | Stack do CLAUDE.md §2 e §14 | Nenhuma dependência paga em `frontend/package.json`, `backend/pyproject.toml` e `docker-compose*.yml`. |
| RNF07 | **Acessibilidade — equivalência textual do mapa.** O mapa não pode ser a única forma de completar uma tarefa: toda ação do mapa tem equivalente em lista ou busca textual. | Frontend (*previsto*; ver RF04) | Cada ação de RF03 e RF07 tem equivalente verificado sem o mapa. |
| RNF08 | **Acessibilidade — movimento reduzido.** Respeitar `prefers-reduced-motion` e oferecer interruptor "Reduzir animações". | *Existe:* `frontend/src/design/movimento.ts`, `movimento.css`, `interruptor-movimento.ts` (testes `movimento.test.ts`, `movimento-css.test.ts`, `mapa-sem-animacao.test.ts`) | Testes passam; com o interruptor ligado, nenhuma transição ou deslocamento animado, inclusive no mapa. |
| RNF09 | **Parâmetros configuráveis e unidades explícitas.** Valores provisórios (penalidades, setores angulares, precisão mínima, raios, intervalos) ficam em `.env`, nunca espalhados no código; armazenamento em SRID 4326 e cálculo métrico em 31983; distância e ângulo com unidade no nome (`distancia_m`, `rumo_graus`). | `.env.example` (*existe*: `PENALIDADE_*` já declaradas, ainda não lidas por `backend/app/config.py`, que hoje só tem os parâmetros do escopo antigo e SRID_*; leitura prevista no M3/M4) | Nenhum número de calibração em código-fonte; revisão das queries espaciais quanto ao SRID. |
| RNF10 | **Plataforma web mobile, servida por HTTPS.** A geolocalização e a bússola só funcionam em HTTPS; a vibração não funciona no Safari/iOS. | Infra na AWS com URL fixa (plano B: túnel HTTPS; `docs/implantacao-aws.md`, `docs/implantacao.md`); `frontend/nginx.conf`. Web ou app nativo: **[DECIDIR COM A ORIENTADORA]** (pendência #2) | Protótipo aberto por HTTPS em um Android e um iPhone com localização liberada; limitação do iOS declarada no texto. |

## 3 Rastreabilidade resumida

| Componente | Requisitos |
|---|---|
| `db/migrations/004_grafo_campus.sql` (existe) | RF01, RF02, RF03, RF05, RF06 |
| `db/migrations/005_medicoes_gps.sql`, `/medicao.html` (existem) | RNF04, RNF10, subsídio a RF08 e RF12 |
| `frontend/src/design/` (existe) | RNF01, RNF02, RNF08 |
| `frontend/src/mapa/rumo.ts` (existe) | RF09, RNF05 |
| M3: `backend/app/rotas/`, `/pontos-interesse`, `/rotas` (previstos) | RF01, RF02, RF05, RF06, RNF03 |
| M4: `backend/app/orientacao/`, `/orientacoes` (previstos) | RF08, RF09, RF10, RF12, RNF03, RNF05 |
| M5: frontend de destino, rota, voz e vibração (previsto) | RF03, RF04, RF07, RF11, RNF01, RNF02, RNF07 |

## 4 Para a equipe decidir ao revisar

- Os enunciados e a numeração são propostas; só RNF01, RNF02 e RNF07 estão ligados a "acessibilidade" no CLAUDE.md §10.
- Metas numéricas de desempenho (RNF03) não existem em nenhum documento: a equipe precisa fixar.
- Os requisitos do escopo antigo (`POST /alertas`, `GET /barreiras`, validação) não entram nesta lista.
