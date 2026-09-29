# Decisões de implementação (glossário)

O código, os commits e os documentos citam identificadores curtos: **G1–G12**, **D1–D8**,
**R1–R37** e "Task N". Eles vêm do plano de implementação do TCC II e do registro de
decisões tomadas durante a execução dele, que ficaram fora do repositório (pasta
`.superpowers/`, não versionada: `plano-tcc2.md`, `globais.md` e o registro de
progresso). Este arquivo guarda o significado de cada um, uma linha por identificador,
para que as referências continuem rastreáveis sem esses arquivos.

Outros identificadores já têm definição no próprio repositório:

- **M0–M6, M5.1**: marcos de desenvolvimento ([`CLAUDE.md`](../CLAUDE.md) §8).
- **#1–#7**: pendências com a orientadora; **T1–T6**: pendências técnicas da equipe
  ([`decisoes-pendentes.md`](decisoes-pendentes.md)).
- **§N**: seção do `CLAUDE.md` ou do documento em que a referência aparece.

## "Task N"

O plano de implementação do TCC II dividiu o trabalho dos marcos M2 a M6 (mais o
M5.1) em **7 tarefas**, executadas entre 28 e 29/09/2026, cada uma revisada antes da
seguinte. Uma **Fase 2** (29/09/2026, branch `fase2`) acrescentou as **Tasks 8 a 11**,
para preparar a coleta real (M6) depois da revisão final da primeira fase: ajustes de
entrada e privacidade, a pilha de produção com HTTPS sem conta, backup e checklist da
coleta, melhorias pequenas e o material para a orientadora. As Tasks 8 a 10 rodaram em
sequência (tocam os mesmos arquivos); a 11, só de documentos, correu em paralelo num
worktree próprio. A Fase 2 terminou com uma revisão final e uma onda única de correções
(R37). "Task N" no código ou num commit aponta para uma delas:

| Task | Escopo | Marco |
|---|---|---|
| 1 | Fundação do backend: `config.py`, `db.py`, fixtures de teste, endpoints de referência | M2 |
| 2 | Entrada de alertas (estágios 1 e 2), `POST /alertas`, `GET /barreiras`, API em container | M2 |
| 3 | Pipeline de validação (estágios 3 e 4) e estatísticas do funil | M3 |
| 4 | Dados sintéticos, teste de eficácia, análise de sensibilidade e figura do funil | M3 |
| 5 | Frontend com mapa e envio de alerta (worktree e branch próprios, em paralelo) | M4 |
| 6 | Integração ponta a ponta (E2E) e protocolo da coleta em campo | M5, M6 |
| 7 | CI/CD no GitHub Actions | M5.1 |
| 8 | Ajustes antes da coleta: coordenadas e severidade estritas, limites de envio (413 e 429), `EXPOR_DOCS`, texto de privacidade exato (R27) | M6 |
| 9 | Implantação sem conta: pilha de produção com as imagens do GHCR, túnel HTTPS (R30), `backup`/`restaurar`, checklist `scripts/preparar-coleta.sh` e `docs/implantacao.md` | M6 |
| 10 | Melhorias pequenas: `/saude` com timeout curto, consulta de barreiras cancelável no mapa, lista permitida do `banco.sh` (R35), teste do frontend com `node:test` | M4, M5 |
| 11 | Material para a orientadora (`docs/orientadora/`) e rascunhos do texto do TCC (`docs/texto-tcc/`), em paralelo, num worktree próprio | texto do TCC |

`globais.md` (citado na migration 002) é o arquivo do plano que reunia as regras G, as
decisões D e o contrato da API para quem implementava cada tarefa. O contrato hoje é
[`api.md`](api.md); G e D estão abaixo.

## G: regras globais do plano (28/09/2026)

Valem para todas as tarefas. Onde uma regra repete o `CLAUDE.md`, o `CLAUDE.md` é a fonte.

| Id | Regra | Por quê |
|---|---|---|
| G1 | Trabalhar só no checkout do repositório no WSL, nunca na cópia antiga no OneDrive. | A cópia em `/mnt/c/.../OneDrive` estava desatualizada e o Postgres exige permissões POSIX no diretório de dados, que o NTFS/OneDrive (`/mnt/c`) não oferece (comentário do volume em `docker-compose.yml`); além disso `/mnt/c` é lento e o OneDrive interfere nos arquivos (README, seção "Onde clonar o projeto"). |
| G2 | Git: branch `tcc2`, sem push/merge/rebase pelos implementadores, commits pequenos em português (`<escopo>: <resumo>`), caminhos explícitos, trailer de coautoria. | Histórico legível e revisável tarefa a tarefa. |
| G3 | Stack: Python 3.12 via `uv`, FastAPI, Pydantic v2, psycopg 3 sem ORM (SQL com parâmetros), frontend TypeScript + Vite + Leaflet sem framework; nada instalado no sistema. | Mantém a stack do `CLAUDE.md` §2 e evita dependências ocultas. |
| G4 | Banco: serviço `db` do compose em `127.0.0.1:5434`, `.env` nunca versionado, operações por `./db/banco.sh`, migrations imutáveis. | Reprodutibilidade e `CLAUDE.md` §10. |
| G5 | Nomes, comentários, docstrings e mensagens em português; termos técnicos consagrados em inglês. | Convenção do `CLAUDE.md` §10, estendida às mensagens da API. |
| G6 | SRID: armazenar em 4326; toda conta métrica com `ST_Transform(geom, 31983)` ou `::geography`; variável de distância termina em `_metros`. | Evita o erro silencioso de eps em graus (`CLAUDE.md` §5). |
| G7 | Parâmetros do DBSCAN, da promoção e os SRIDs só em `config.py` (lidos do `.env`), nunca literais no código de `app/`. | Valores provisórios, a calibrar (`CLAUDE.md` §6, §11). |
| G8 | Toda função de `app/validacao/` tem teste; testes no PostGIS real, num banco `_teste` separado, sem mock de banco; pytest e ruff sem avisos. | O núcleo do TCC precisa de evidência, não de suposição. |
| G9 | Estados de alerta e barreira da migration 001; `confirmacoes` conta sessões distintas; reprovado no estágio 1 vai para `alertas_rejeitados`. | Uma só definição do ciclo de vida, a do schema. |
| G10 | Honestidade acadêmica: dado sintético tem `origem='simulacao'` e o rótulo "SIMULAÇÃO" em toda saída; as origens nunca se misturam. | `CLAUDE.md` §9: número sintético nunca pode passar por coleta real. |
| G11 | Escopo: sem roteamento/pgRouting; a solução mais simples que resolve; nenhum arquivo fora da estrutura pedida. | `CLAUDE.md` §11 e §13. |
| G12 | Portas: API 8000, frontend em container 8081, Vite dev 5173; na pilha de containers o frontend fala com a API pela mesma origem. | A 8080 colidia com o Jenkins da máquina do usuário (ver R19). |

## D: decisões do orquestrador que estendem a spec (28/09/2026)

| Id | Decisão | Por quê |
|---|---|---|
| D1 | `sessao_id` é um UUID gerado no navegador (`localStorage`); o servidor grava só `sha256(uuid)` nos relatos aceitos e nunca guarda IP; relatos reprovados no estágio 1 guardam o corpo recebido inteiro (UUID cru, descrição e campos extras) em `alertas_rejeitados.payload` (R27). | Resolve T3: identifica relatos do mesmo aparelho sem dado de identificação; o UUID é aleatório e só existe no aparelho. |
| D2 | Coluna `origem` (`real`\|`simulacao`) em `alertas`, `alertas_rejeitados` e `barreiras` (migration 002); pela HTTP é sempre `real`. | G10: separar simulação de coleta real no próprio dado. |
| D3 | O tipo é enviado pelo `codigo` (ex.: `"degrau"`), não pelo id; tipo inexistente ou inativo reprova no estágio 1. | Contrato estável mesmo se os ids da taxonomia mudarem. |
| D4 | Alerta válido fora da área: HTTP 201 com `status="descartado"` e `motivo_descarte="fora_da_area"`; reprovado no schema: HTTP 422. | O alerta fora da área foi registrado e conta no funil (estágio 2). |
| D5 | Endpoints de apoio ao frontend: `GET /saude`, `GET /tipos-barreira`, `GET /area-estudo`, em GeoJSON quando geográficos. | O mapa precisa da taxonomia e do polígono. |
| D6 | O pipeline reconstrói a origem inteira a cada execução, numa transação com `pg_advisory_xact_lock`; os ids das barreiras mudam a cada execução. | Resolve T4: o ruído é reavaliado e o resultado não depende da ordem das execuções. |
| D7 | `POST /validacao/executar` exige `X-Token-Admin` igual ao `TOKEN_ADMIN` do `.env` quando ele não está vazio. | Executar apaga e recria as barreiras da origem; não é ação de visitante. |
| D8 | Cinco populações sintéticas: as três do `CLAUDE.md` §9 mais `sessao_repetida` e `invalidos`. | Provar também os estágios 4 (sessões distintas) e 1 (schema). |

## R: decisões tomadas durante a execução do plano

| Id | Decisão | Por quê | Quando |
|---|---|---|---|
| R1 | Tasks 1–4 e 6 no próprio checkout, branch `tcc2`, sem worktree. | O compose (nome do projeto, bind mount) e o `.env` estão ligados ao checkout. | 28/09, antes da Task 1 |
| R2 | Task 5 (frontend) em paralelo com as Tasks 3–4, num worktree com branch `tcc2-frontend`. | Caminhos disjuntos (só `frontend/`) e pedido do usuário por agentes em paralelo. | 28/09, antes da Task 1 |
| R3 | O plano estende a spec com D1–D8. | Cada uma resolve uma pendência técnica (T3, T4) ou uma exigência de honestidade (G10). | 28/09, antes da Task 1 |
| R4 | `pythonpath = ["."]` no pytest e rotas lendo a config por `Depends(obter_configuracoes)`. | Sem isso os testes não importam `scripts` nem trocam a config (token). | 28/09, antes da Task 1 |
| R5 | `parametros.eps_metros` sai como float (`8.0`). | A config é float; o JSON do contrato era ilustrativo. | 28/09, antes da Task 1 (sobre a Task 3) |
| R6 | No fim, merge de `tcc2` em `main` e push sem perguntar; depois da revisão final, só depois das correções dela. | O usuário pediu para seguir até o fim; a revisão final pediu as correções antes. | 28/09, antes da Task 1; ajustada em 29/09 |
| R7 | O `CLAUDE.md` §7 traz a tabela resumida e aponta `docs/api.md` como o contrato detalhado. | Interpretação do item 9 da Task 2. | 28/09, antes da Task 1 (sobre a Task 2) |
| R8 | "Faz commit no fim" (Task 4) = o script confirma a transação do banco. | Scripts são pontos de entrada; as funções de `app/validacao/` nunca fazem commit. | 28/09, antes da Task 1 (sobre a Task 4) |
| R9 | O trailer de coautoria dos commits usa o nome real do modelo. | Atribuição correta de autoria. | 28/09, Task 1 |
| R10 | A alternativa acessível aos marcadores do mapa é uma lista focável e sincronizada das barreiras visíveis. | Leitor de tela lê lista melhor que marcadores, sem uma fila enorme de Tab. | 28/09, Task 5 |
| R11 | O CD publica as imagens no GHCR (push no `main` e tags `v*`); a implantação fica pronta, mas desativada (`if: false`). | A hospedagem com HTTPS ainda não foi escolhida (T6). | 28/09, Task 7 |
| R12 | O push de verificação do CI é feito pelo orquestrador; falha no GitHub vira rodada de correção. | G2 proíbe push aos implementadores. | 28/09, Task 7 |
| R13 | `executar_pipeline` recebe também `srid_armazenamento`. | Evita o literal 4326 no código (G7). | 28/09, Task 3 |
| R14 | Migration 003 `execucoes_pipeline`: as estatísticas mostram os parâmetros e o horário da ÚLTIMA execução, não a config atual. | Honestidade do resultado (G10): a figura nunca leva parâmetros que não produziram os números. | 28/09, Task 3 |
| R15 | Estatísticas num único snapshot, validação dos parâmetros antes do lock e `rotulo` na resposta de `/executar`. | Tocam o mesmo código e protegem a análise de sensibilidade. | 28/09, Task 3 |
| R16 | As 5 populações seguem como CONTROLE; a sensibilidade ganha a população `sequencia` (encadeamento, T5) e aglomerados com 2 a 5 sessões (efeito de `min_confirmacoes`, #4). | O 100% do controle valida a implementação, não a robustez. | 29/09, Task 4 |
| R17 | Ajustes de honestidade nas saídas da sensibilidade e da figura (minpoints real no CSV, sufixo `_metros`, rótulos "relatos"). | Mesmos arquivos, mesma preocupação com a saída. | 29/09, Task 4 |
| R18 | A análise de sensibilidade não grava nada: roda numa transação desfeita no fim. | O banco principal mantém a simulação canônica que a figura mostra. | 29/09, Task 4 |
| R19 | Na pilha de containers, frontend e API na mesma origem (nginx encaminha `/api/`); frontend na porta 8081. | Com o frontend na 8081 o CORS barrava o mapa; e a coleta precisa de um só endpoint HTTPS. | 29/09, Task 6 |
| R20 | Actions nas majors que rodam em Node 24; runner fixo em `ubuntu-24.04`. | O `ubuntu-latest` muda para o Ubuntu 26 perto da entrega. | 29/09, Task 7 |
| R21 | A rodada de correção da Task 7 junta concurrency, R20, `timeout-minutes` e a nota do PR duplo. | Um único ciclo de revisão para o mesmo arquivo. | 29/09, Task 7 |
| R22 | Uma única onda de correções depois da revisão final (6 importantes e 16 menores). | Um só ciclo, com os adiados listados. | 29/09, revisão final |
| R23 | `./db/banco.sh zerar-real --sim-apagar-dados-reais` apaga só `origem='real'`, só antes da coleta. | Melhor que DELETEs manuais no dia; a confirmação literal evita acidente. | 29/09, revisão final |
| R24 | Sem Google Fonts: fonte hospedada no próprio frontend. | Privacidade (IP do voluntário) e coleta sem depender de internet boa. | 29/09, revisão final |
| R25 | Este glossário. | Tornar rastreáveis as cerca de 140 referências a G, D, R e Task. | 29/09, revisão final |
| R26 | O minpoints do estágio 3 contar alertas, não sessões, vira pendência para a orientadora, sem implementação. | Mudança metodológica do núcleo do TCC não é decisão do orquestrador. | 29/09, revisão final |
| R27 | O texto de privacidade diz que relatos reprovados no estágio 1 guardam o corpo recebido inteiro (com o `sessao_id` cru) em `alertas_rejeitados.payload`. | Precisão: a frase "nunca o UUID cru" só valia para os relatos aceitos. | 29/09, Task 8 |
| R28 | A divisão de responsabilidades (pendência #5) foi decidida pelo usuário: código = rlbuff7, infra = Victor, dados reais = Maurício. | Dá um dono a cada frente da coleta e a cada cartão do quadro da equipe. | 29/09, antes da Task 8 |
| R29 | O quadro de tarefas (Kanban) da equipe é uma página compartilhada, com cartões que todos editam, fora do repositório; o repositório guarda o plano técnico. | A equipe precisa mover cartões sem fazer commit. | 29/09, antes da Task 8 |
| R30 | HTTPS sem conta pelo Quick Tunnel do `cloudflared`, em container (profile `tunel` do `docker-compose.prod.yml`), preparado e documentado, sem exposição duradoura. | A geolocalização do celular exige HTTPS, e a hospedagem com conta ainda não foi escolhida (T6). | 29/09, Task 9 |
| R31 | A fonte da G1 é o comentário do volume no `docker-compose.yml` mais a seção "Onde clonar o projeto" do README; os menores da revisão entram na mesma rodada. | A G1 citava arquivos sem o conteúdo; a nota também orienta quem cuida da infra. | 29/09, Task 8 |
| R32 | `restaurar` valida o dump antes de tudo, restaura num banco temporário e só então troca os nomes; `--teste` no `banco.sh`; túnel com `restart: "no"`; o roteiro da primeira abertura em ordem: checklist, túnel, teste no celular, `zerar-real`, checklist de novo, abertura. | Nenhum caminho pode deixar o banco da coleta vazio ou pela metade, nem abrir uma URL pública sem ninguém decidir. | 29/09, Task 9 |
| R33 | A autoria do TCC é decisão da equipe e da orientadora: nenhuma tarefa do plano altera listas de autores. | Não é decisão técnica. | 29/09, Task 11 |
| R34 | O teste `db/tests/banco_sh_seguranca.sh` roda no job `banco-e-backend` do CI. | Uma regressão na restauração seria silenciosa. | 29/09, Task 9 |
| R35 | O `banco.sh` preserva do shell só uma lista permitida (projeto e arquivo do compose, portas, `BANCO_ALVO`, `BACKUP_DIR`, `IMAGEM_TAG`); `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD` vêm sempre do `.env`, com aviso se o shell tiver outro valor. | Um `POSTGRES_DB` esquecido no shell faria backup ou restauração agir noutro banco em silêncio. | 29/09, Task 10 |
| R36 | A discussão de autoria e os dados pessoais de terceiros (números de matrícula e um nome vindo dos metadados de um arquivo) saem do repositório, que é público; no lugar, uma linha neutra para conferir a lista de autores com a equipe e a orientadora. | Privacidade e R33: o repositório público não é lugar dessa discussão. | 29/09, revisão final da Fase 2 |
| R37 | Uma única onda de correções depois da revisão final da Fase 2 (1 crítico, 8 importantes e 10 menores), com os adiados listados. | Um só ciclo, como na R22; o crítico (reabrir a coleta sem apagar dados reais) protege os dados do TCC. | 29/09, revisão final da Fase 2 |
