# Medição v2 — Plano de Implementação

> **Status em 03/11/2026: PARCIALMENTE ATENDIDO, por outro caminho.** Este plano (redesenho Preparar/Medir/Resultado em `frontend/medicao.html`) não foi executado como escrito. A medição de 26/10 foi feita com a tela existente e, depois dela, o mapa da medição ganhou as camadas "Falta mapear", "Já feito" (trajeto da equipe, caminhos da v0, pontos de controle), trajeto ao vivo, botões Centralizar e Ver o campus e legenda em lista (merges `medicao/falta-mapear`, `medicao/enquadrar`, `medicao/ja-mapeado`). Seguem pendentes o cartão inferior fixo de 64 px, a barra única e o Resultado enxuto. Decidir se vale executar antes de nova rodada de medição.

> **Para quem executar:** use `superpowers:executing-plans` (ou `subagent-driven-development`), tarefa por tarefa, marcando os passos. Teste primeiro quando houver lógica. Commits pequenos, em português.

**Objetivo:** redesenhar a tela `frontend/medicao.html` (Preparar, Medir, Resultado) conforme os boards `Medicao-v2-{preparar,medir,resultado}.dc.html`: uma barra única no topo, mapa maior, ação principal de 64 px num cartão inferior fixo, Resultado enxuto. É só apresentação: nenhum contrato muda.

**Arquitetura:** a página continua uma MPA com `pagina.ts` ligando o DOM a módulos puros (`fluxo.ts`, `fila.ts`, `fotos.ts`, `pontos-controle.ts`). A lógica nova (texto do chip de trajeto, status único do Resultado, "últimos pontos") vai para funções puras em `fluxo.ts` com teste em `node:test`. O resto é HTML + `medicao.css`. **Sem dependência nova.**

**Stack:** Vite 8, TypeScript 7, Leaflet 1.9, `node --experimental-strip-types --test` (Node 22: sem "parameter properties").

**Status:** PLANO. A proposta visual ainda **não** foi aprovada pelo Rodrigo para implementar. Nenhum código do app foi alterado.

---

## 1. O que NÃO muda

Estes itens são restrições. Se uma tarefa pedir mudar um deles, pare e pergunte.

**Contratos de envio**
- `POST /api/medicoes` (corpo, lote máx. 20 itens / 14000 bytes, 401/422/429/503 e recuo 5-10-30-60 s) e o envio de foto. `fila.ts` e `fila-fotos.ts` **não são tocados**.
- `condicao`: `ceu_aberto | entre_predios | coberto | entrada_predio`. Rótulos e `pontos-controle.ts` iguais.
- CSV exportado: mesmas colunas e ordem (`baixarCsv` em `pagina.ts`).

**Chaves de localStorage** (`pagina.ts:84-89`): `msb-medicao-fila`, `msb-medicao-registros` (antiga, só migração), `msb-medicao-aparelho`, `msb-medicao-codigo`, `msb-medicao-ponto-atual`, `msb-medicao-recomeco`. IndexedDB `msb-fotos`. Chave de tema/movimento de `src/design/` também.

**IDs usados por `pagina.ts` (via `el()`), testes e E2E**
- `el(id)` lança erro se o ID não existe. Por isso **nenhum ID some**: os que mudam de lugar no HTML continuam com o mesmo ID. IDs hoje no HTML: `botao-ajustes, painel-ajustes, botao-recomecar, confirmar-recomecar, texto-confirmar, botao-recomecar-sim, botao-recomecar-nao, titulo-ponto, titulo-medicao, progresso, faixa-trajeto, status-trajeto, anuncio-trajeto, botao-parar-trajeto, anuncio-etapa, etapa-{preparar,medir,resultado}, titulo-etapa-*, campo-{aparelho,codigo,ponto,condicao,observacao,foto}, botao-continuar, mapa-medicao, legenda-referencia, painel-precisao, precisao-valor, precisao-nivel, contagem-*, botao-registrar, botao-pular, botao-abrir-bussola, botao-trajeto, botao-exportar, barra-medir, barra-confirmar, cartao-*, fila-*, botao-proximo, lista-registros, lista-fotos, estado-foto, estado-envio` etc.
- IDs que **podem** ficar sem uso visual só se o código parar de chamá-los na mesma tarefa (ver T5, T6, T9).
- E2E (`backend/scripts/ponta_a_ponta.py:352-354`): `<title>Medição de GPS — Mackenzie</title>` e o texto `Registrar agora` na resposta de `GET /medicao.html`. Os dois ficam.
- Testes que leem HTML/CSS como texto: `etapas-html.test.ts`, `ajustes-html.test.ts`, `movimento-css.test.ts`, `mapa-sem-animacao.test.ts`, `contraste.test.ts`. Rodam em toda tarefa.

**Decisões já tomadas (respeitar)**
- Aviso "Ferramenta da equipe. Não é navegação…" **visível em todas as etapas** (faixa fina; é segurança). O board de Medir não o mostra: o plano acrescenta (T11).
- Linha do trajeto azul (token da marca); regra de cor da medição (azul; cor de estado só em erro; laranja só no foco); nada só por cor (ícone + texto).
- Alvos >= 44 px; ação principal 64 px.
- Movimento opt-in (`prefers-reduced-motion: no-preference` + interruptor). **Nunca** animar mapa, posição, rota, rumo, leituras ao vivo ou avisos de erro. Sem loop automático.
- Foco no `h2` da etapa ao trocar; um anúncio por troca (`irParaEtapa`).
- Sem Google Fonts/CDN; sem dependência nova.

---

## 2. Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `frontend/medicao.html` | alterar | Nova estrutura: faixa de segurança, barra única (Início, ponto, Mais), chip de trajeto, mapa, cartão inferior, Resultado novo. IDs preservados. |
| `frontend/src/medicao/medicao.css` | alterar | Layout flex da tela, barra, menu, cartão fixo, aviso de precisão, chip, Resultado. |
| `frontend/src/design/menu-mais.ts` | criar | Menu "Mais" genérico (botão `aria-expanded`, Esc, foco, clique fora, setas). Substitui o uso de `ajustes.ts` na medição (o arquivo antigo fica se o índice ainda o usa). |
| `frontend/src/design/menu-mais.test.ts` | criar | Teste de lógica pura (índice de foco, teclas) + teste de estrutura do HTML (`aria-*`). |
| `frontend/src/design/ajustes.ts` | alterar/manter | Verificar se `index.html` ainda usa; se sim, não mexer. |
| `frontend/src/medicao/fluxo.ts` (+ `fluxo.test.ts`) | alterar | Funções puras novas: `textoChipTrajeto`, `statusDoPonto` (status único do Resultado), `ultimosPontos`, `textoPontoTitulo`. |
| `frontend/src/medicao/pagina.ts` | alterar | Ligar menu, chip, cartão, Resultado; `desenharCabecalho`, `desenharConfirmacao`, `desenhar*Fotos`, `mostrarTrajeto`. Sem lógica nova (vai para `fluxo.ts`). Já tem 1386 linhas: não crescer, mover para `fluxo.ts`. |
| `frontend/src/medicao/etapas-html.test.ts` | alterar | Atualizar o que o HTML novo muda (ordem de IDs, aviso em todas as etapas). |
| `frontend/src/design/movimento-css.test.ts` | manter/alterar | Cobrir classes novas se tiverem transição. |
| `backend/scripts/ponta_a_ponta.py` | **não mexer** | Já confere só `<title>` e "Registrar agora". |
| `docs/medicao-gps.md` | alterar (T13) | Descrever a tela nova em poucas linhas. |

---

## 3. Tarefas

Cada tarefa: 30-90 min, termina com `npm run testar`, `npm run verificar` e `npm run build` verdes (comandos em `frontend/`) e um commit. Diretório do app: `frontend/`.

Ordem de dependência: T1 -> T2 -> T3 ... Tarefas T1-T4 são lógica/estrutura e podem ser mescladas em branch sem mudar a aparência (ver §5, estratégia). Aparência só muda a partir de T5.

### T1. Funções puras da v2 em `fluxo.ts` (45 min)
- **Arquivos:** `src/medicao/fluxo.ts`, `src/medicao/fluxo.test.ts`.
- **O que fazer (teste primeiro):**
  - `textoPontoTitulo(ponto, medicaoAtual, total)` -> `"P03 · 2 de 3"`.
  - `textoChipTrajeto(estado, quantidade)` -> `"Trajeto: 12 posições"` (singular em 1; texto sem número quando parado).
  - `statusDoPonto({ enviadas, total, naFila, recusadas })` -> um único status `{ icone, texto, tipo }` (ex.: `✓ 3 de 3 medições enviadas para a equipe`, `◆ 2 na fila`, `✕ recusada`). Um estado só, nunca dois cartões.
  - `ultimosPontos(registros, fila, n)` -> só linhas de **pontos** (agrupa as 3 medições por ponto: `P02 · 3 de 3 · 21 m · ◆ na fila`), nunca medições soltas.
- **Pronto quando:** testes novos vermelhos e depois verdes; nada em `pagina.ts` mudou; `fluxo.ts` continua sem DOM.
- **Testes:** casos de 0, 1, 3 medições; fila com pendente/recusada/enviada; ponto pulado; ordem do mais recente.
- **Risco:** baixo. Texto do anúncio por voz (`anuncioDaEtapa`) não pode regredir: manter os testes antigos verdes.

### T2. Menu "Mais" (`menu-mais.ts`) (60 min)
- **Arquivos:** `src/design/menu-mais.ts`, `src/design/menu-mais.test.ts`.
- **Comportamento:** botão `Mais ▾` com `aria-haspopup="true"`, `aria-expanded`, `aria-controls`. Abre painel com itens (botões) Ajustes, Exportar CSV, Recomeçar do ponto 1…. Foco vai ao primeiro item ao abrir; setas cima/baixo e Home/End andam entre itens; **Esc fecha e devolve o foco ao botão**; Tab fora fecha; clique fora fecha. Sem animação.
- **Teste primeiro (puro):** `proximoIndice(atual, tecla, total)` com circulação; `deveFechar(evento)`. Teste de estrutura: o HTML tem `aria-expanded="false"` inicial e `aria-controls` apontando para um ID existente.
- **Pronto quando:** testes verdes; módulo não depende de `pagina.ts`; nenhum `localStorage`.
- **Risco:** médio (foco e teclado). Alternativa mais simples se complicar: lista de botões sem setas (Tab entre itens), mantendo Esc e `aria-expanded`.

### T3. Estrutura nova da barra superior no HTML (60 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `src/medicao/pagina.ts` (só ligação), `etapas-html.test.ts`.
- **O que fazer:** substituir `.medicao__topo` por **uma barra**: `← Início` | `<h1>` com `P03 · 2 de 3` | `Mais ▾`. Remover a linha de 3 botões e o `h1` de duas partes. `#botao-ajustes`, `#botao-recomecar`, `#botao-exportar` continuam existindo como itens do menu (mesmos IDs), então os `addEventListener` não quebram. Painel de ajustes e confirmação de recomeço aparecem logo abaixo da barra (como hoje), com `hidden`.
- **Confirmação de recomeço:** continua a mesma região `role="group"` com `Sim, recomeçar`/`Não, continuar`; ao fechar devolve o foco ao item/botão que abriu (regra existente em `fecharConfirmacao`).
- **Pronto quando:** barra com altura útil <= 56 px a 390 px; alvos >= 44 px; ordem de Tab = Início, ponto, Mais; E2E de HTML (`<title>`, "Registrar agora") ainda presente; testes verdes.
- **Risco:** médio. `desenharCabecalho` escreve em `titulo-ponto` e `titulo-medicao`: manter os dois IDs (spans dentro do h1) ou trocar os dois lados na mesma tarefa.

### T4. Select do ponto no título (45 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `pagina.ts` (`desenharOpcoesDePonto`, `definirPonto`), `pontos-controle.ts` só se faltar rótulo.
- **O que fazer:** em Medir, o `P03 · 2 de 3 ▾` do título é o próprio `<select>` (visualmente um título; rótulo acessível "Ponto de controle"). Em Preparar o select fica no formulário (como no board). Um único `<select>` com `id="campo-ponto"` vale para as duas etapas (mover o elemento entre contêineres ao trocar de etapa, sem recriar as opções), ou dois selects sincronizados, o que for mais simples. **Preferir um só.**
- **Regras:** troca de ponto mantém `preencherCondicaoDoPonto`; `nome_curto` (<= 24 car.) para o "· feito" não cortar a 390 px; sem segundo campo de ponto em Medir (decisão de 22/10).
- **Pronto quando:** trocar o ponto por teclado e por toque funciona; `msb-medicao-ponto-atual` é gravada igual; leitor de tela diz "Ponto de controle, P03 · Entrada do Prédio 31".
- **Risco:** médio (select estilizado como título perde affordance). Manter seta ▾ visível (nada só por cor).

### T5. Faixa de segurança fina e chip único de trajeto (45 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `pagina.ts` (`mostrarTrajeto`), `fluxo.ts` (usa T1), testes.
- **Faixa de segurança:** `<p role="note">` de uma linha, `Ferramenta da equipe, não é navegação.` + `Funciona sem sinal: os registros ficam na fila.` só em Preparar; em **todas** as etapas, no mínimo a primeira frase, fixa logo abaixo da barra, <= 28 px, texto >= 12 px com contraste AA (`contraste.test.ts`). Manter a frase completa "Não siga nenhuma direção mostrada aqui" no `aria-label`/`oculto-visualmente` para leitor de tela.
- **Chip de trajeto:** um chip só (`● Trajeto: 12 posições` + botão `Parar`), no lugar de `#faixa-trajeto`. Mantém `#status-trajeto` (texto, sem `aria-live`), `#anuncio-trajeto` (região separada) e `#botao-parar-trajeto`. A linha do trajeto no mapa continua azul; o chip usa ícone + texto.
- **Pronto quando:** aviso visível nas 3 etapas (teste em `etapas-html.test.ts` conferindo que o aviso está fora das `<section>` e sem `hidden`); chip some quando não há trajeto; `Parar` >= 44 px; o anúncio do trajeto continua só no marco certo (`deveAnunciarTrajeto`).
- **Risco:** baixo. Segurança: nunca esconder a faixa por falta de espaço (testar com teclado aberto, T8).

### T6. Mapa maior com layout flex (60 min)
- **Arquivos:** `medicao.css`, `medicao.html`, `pagina.ts` (`iniciarMapa`, `enquadrarMapa`, `aoEntrarEmMedir`).
- **O que fazer:** `.medicao__tela` vira coluna `display:flex; height:100dvh` (com `min-height:0` nos filhos); o mapa recebe `flex:1 1 auto; min-height:240px`. Barra e cartão inferior têm altura natural. Depois de qualquer mudança de altura (entrar em Medir, abrir/fechar menu, chip aparecer, teclado do celular) chamar `mapa.invalidateSize({ animate: false })` e `enquadrarMapa()` (já sem animação) via `ResizeObserver` no contêiner do mapa (com `requestAnimationFrame` para juntar chamadas).
- **Pronto quando:** a 390x844 o mapa ocupa >= 45% da altura; `mapa-sem-animacao.test.ts` verde (nenhuma opção de animação nova); sem tile cinza depois de rotacionar o aparelho.
- **Risco:** **alto** (mapa em flex, `100dvh` no Safari iOS, teclado). Mitigação: fallback `100vh` antes de `100dvh`; `min-height` no mapa; verificar em celular real.

### T7. Cartão inferior fixo e ação principal de 64 px (75 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `pagina.ts` (`barra-medir`, `barra-confirmar`).
- **O que fazer:** juntar `#barra-medir` e o conteúdo do cartão em **um** cartão fixo no fim: linha "Condição: Entrada de prédio · Editar", botão `Registrar agora` (`#botao-registrar`, 64 px de altura, largura total), e a linha de secundárias `Foto | Bússola | Pular ponto` (`#campo-foto` (rótulo), `#botao-abrir-bussola`, `#botao-pular`), cada uma >= 44 px. Contagem (`18 s`, `Fique parado. Registra sozinho.`) fica acima do botão, com `#botao-contagem` mantendo o comportamento atual.
- **Teclado do celular aberto:** o cartão usa `position: sticky; bottom: 0` dentro do flex (não `fixed`) para o Visual Viewport não o empurrar para cima do campo; o campo de observação rola para a vista (`scrollIntoView({block:'nearest'})` sem animação) e o cartão nunca cobre o campo em foco; `scroll-padding-bottom` igual à altura do cartão. Respeitar `env(safe-area-inset-bottom)`.
- **Pronto quando:** `Registrar agora` presente no HTML (E2E); alvo 64 px medido; Tab chega ao botão antes das secundárias; com o teclado aberto o campo em edição fica visível (print/celular); `etapas-html.test.ts` atualizado.
- **Risco:** **alto** (teclado do iOS/Android). Mitigação: se `sticky` falhar, o cartão deixa de ser fixo quando algum campo tem foco (classe `medicao--digitando` via `focusin/focusout`).

### T8. Aviso de precisão em largura total (30 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `pagina.ts` (`desenharPrecisao`), `fluxo.ts` se o texto mudar.
- **O que fazer:** `#painel-precisao` vira faixa de largura total acima do formulário (Preparar) e sobre o mapa/abaixo do chip (Medir), com ícone + texto (`▲ Precisão média: 25 m` + frase de ajuda). Estados: boa, média, ruim, sem sinal, cada um com ícone e texto diferentes. Atualização sem animação, `precisao-valor`/`precisao-nivel` preservados. Sem `aria-live` assertivo (não falar a cada fix; anunciar só mudança de nível, como hoje).
- **Pronto quando:** nenhum estado depende só de cor; contraste AA nos temas claro, escuro e alto contraste (`contraste.test.ts`).
- **Risco:** baixo.

### T9. Condição e observação recolhidas (45 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `pagina.ts` (`campo-condicao`, `campo-observacao`, `preencherCondicaoDoPonto`).
- **O que fazer:** em Medir, mostrar só `Condição: Entrada de prédio  Editar`. `Editar` abre (botão `aria-expanded`) um bloco com `<select id="campo-condicao">` e `<textarea id="campo-observacao">` (rótulos visíveis); fechado por padrão; mostra `Observação: …` resumida quando preenchida. A observação do plano do ponto (`#ponto-observacao`) fica numa linha curta recolhível.
- **Pronto quando:** pré-preenchimento pelo ponto e "mesma ponto mantém a correção" continuam (testes de `pontos-controle` + `fluxo`); o valor do select recolhido é o enviado; foco volta ao `Editar` ao fechar.
- **Risco:** médio (campo escondido não pode ser enviado vazio por engano: ler sempre `.value`, nunca do texto resumido).

### T10. Resultado novo (60 min)
- **Arquivos:** `medicao.html`, `medicao.css`, `pagina.ts` (`desenharConfirmacao`, `desenharFotos`, lista), `fluxo.ts` (T1).
- **O que fazer (conforme board):**
  1. **Status único** no topo: `✓ P03 completo / 3 de 3 medições enviadas para a equipe` (substitui `#cartao-*` e `#cartao-fila`; manter `#cartao-estado/#cartao-titulo/#cartao-detalhe` e remover `#cartao-fila/#fila-*` **só se** `pagina.ts` deixar de os usar na mesma tarefa). Erros de envio (401, 422) continuam com `#botao-corrigir-codigo`.
  2. **Linha das medições** (`Medição 1  8 m  ✓ enviado`).
  3. **Linha da foto** (`✓ Foto enviada · Foto do ponto, sem localização embutida`), com estados pendente/recusada em texto + ícone, `#lista-fotos` e `#estado-foto` preservados.
  4. **Últimos pontos**: só pontos (T1 `ultimosPontos`), **recolhidos** (`<button aria-expanded>` `Últimos pontos 3 ▸`), sem as medições soltas.
  5. `Próximo ponto: P04` (`#botao-proximo`, 64 px).
- **Pronto quando:** foco no `h2` ao entrar; um anúncio só; CSV/lista de registros completa continua acessível pelo menu "Exportar CSV"; `#lista-registros` ainda existe (pode ficar dentro do recolhido).
- **Risco:** médio. Perder o histórico completo na tela não pode apagar dado: só mudar a visão.

### T11. Aviso de segurança, revisão de composição e temas (45 min)
- **Arquivos:** `medicao.css`, `medicao.html`.
- **O que fazer:** conferir a faixa fina de segurança (T5) nas 3 etapas e nos 4 temas; conferir a regra de cor (azul, `--pendente`, `--perigo`, laranja só foco); tema de alto contraste; `contraste.test.ts` estendido às cores novas.
- **Pronto quando:** `npm run testar` verde, incluindo contraste das combinações novas.
- **Risco:** baixo.

### T12. Revisão com skills e prints a 390 px (90 min)
- **Skills** (em `/home/odrigo_lucas/projetos/mackenzie-sem-barreiras/.claude/skills/`): `review-animations` (nada animado em mapa/leituras; transições só no opt-in e <= 300 ms), `web-design-guidelines` e `accessibility` (foco, rótulos, teclado, alvos, contraste, `aria-expanded`). Corrigir só o que for achado real, em commits separados.
- **Prints a 390 px** (método da memória do agente: `<style>html{width:390px}</style>` na cópia do `dist`, print a 500 px e corte com PIL; posição simulada injetada no `<head>`): Preparar, Medir (com chip de trajeto, aviso de precisão média, condição aberta), Resultado (status ok, fila, foto recusada), menu "Mais" aberto, confirmação de recomeço. Comparar com os boards. Prints ficam fora do Git (ou em `docs/figuras/` só se o Rodrigo quiser).
- **Pronto quando:** checklist das 3 skills sem pendência alta; prints conferidos; nada vai para produção sem teste em celular real (ver §5).
- **Risco:** médio. O Chrome do Windows aqui reporta `prefers-reduced-motion: reduce`: a parte animada só é conferida por teste de estrutura.

### T13. Documentação e fechamento (30 min)
- **Arquivos:** `docs/medicao-gps.md`, memória do agente (por quem executar).
- **Pronto quando:** `docs/medicao-gps.md` descreve a tela nova em <= 15 linhas; `npm run testar`, `verificar`, `build` verdes; lista de commits no relatório final.

---

## 4. Verificação padrão (toda tarefa)

```bash
cd frontend && npm run testar && npm run verificar && npm run build
```
- Em worktree sem `node_modules`, usar symlink para o do repositório principal (ignorado pelo Git).
- Nunca Docker. Nunca push/merge.
- O que **não** dá para provar sem celular real: teclado aberto, `100dvh` no iOS, vibração, bússola, GPS. Marcar no relatório como "não verificado em aparelho".

---

## 5. Estratégia de entrega sem atrapalhar a coleta em campo

1. **Branch própria** `frontend/medicao-v2` (worktree própria), a partir da `main`. Nada na `main` até aprovação.
2. **Tarefas T1-T2 são seguras** (lógica pura e módulo ainda sem uso): podem ir à `main` antes, sem mudar a tela, se o Rodrigo quiser reduzir o PR final.
3. **Merge só fora do horário de coleta.** O deploy é automático ~5 min após o CI na `main`, então um merge no meio da coleta troca a tela na mão de quem mede. O Rodrigo escolhe a janela (ex.: noite anterior ou após a rodada) e avisa a equipe.
4. **Antes do merge:** (a) teste em pelo menos 1 Android e 1 iPhone reais, (b) chave `msb-medicao-fila` com itens pendentes continua enviando depois de abrir a tela nova (teste manual: deixar itens na fila, atualizar a página), (c) E2E (`ponta_a_ponta.py`) verde no CI.
5. **Reversão:** `git revert` do merge e novo deploy (~5 min); como nada muda nos contratos nem nas chaves, voltar à v1 não perde dado.
6. Uma tela que já está em campo muda o hábito da equipe: mandar 2 linhas no grupo ("o menu Ajustes/Exportar/Recomeçar agora fica em Mais").

---

## 6. Estimativa e corte (MVP da v2)

| Tarefa | min |
|---|---|
| T1 puras | 45 |
| T2 menu Mais | 60 |
| T3 barra única | 60 |
| T4 select no título | 45 |
| T5 faixa + chip | 45 |
| T6 mapa flex | 60 |
| T7 cartão 64 px | 75 |
| T8 precisão | 30 |
| T9 recolhidos | 45 |
| T10 Resultado | 60 |
| T11 temas/contraste | 45 |
| T12 revisão + prints | 90 |
| T13 docs | 30 |
| **Total** | **690 min = cerca de 11,5 h** (com folga de 20% para ajustes de celular: **~14 h**, dois a três dias de trabalho) |

**MVP (cerca de 7 h), o que mais melhora a coleta:** T1, T5, T6, T7, T8, T12 (parcial: só a revisão de acessibilidade e prints de Medir). Entrega: mapa maior, ação de 64 px fixa, aviso de precisão claro, chip único, segurança sempre visível.

**Cortar primeiro (nesta ordem):** T9 (recolher condição/observação), T4 (select no título: manter o campo de ponto como está), T10 itens 4 (recolher "últimos pontos"), T2/T3 (menu Mais: manter Ajustes/Recomeçar como hoje), T11/T13 (ajustes finos e doc). Nunca cortar: T5 (faixa de segurança), revisão de acessibilidade, teste em celular real.

---

## 7. Perguntas abertas para o Rodrigo

1. **Aprova a proposta visual para implementar?** (Hoje é só planejamento.) E aprova o MVP de ~7 h ou a v2 completa de ~14 h?
2. **Janela de merge:** quais dias/horários a equipe não está em campo, para o deploy da tela nova?
3. **Aviso de segurança:** a frase curta ("Ferramenta da equipe, não é navegação.") em toda etapa basta, com a versão completa só no leitor de tela e em Preparar? Ou prefere a frase completa visível sempre?
4. **Histórico na tela:** pode sair da tela "Resultado" a lista de medições soltas (ficando só em "Últimos pontos" recolhido e no CSV)? Ou a equipe usa essa lista em campo para conferir?
