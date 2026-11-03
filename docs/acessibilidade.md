# Acessibilidade do app (WCAG 2.2 AA, perfis e leitor de tela)

Criado em 03/11/2026, a partir da reunião com a orientadora de 27/10/2026. Registra metas,
perfis, comportamento com leitor de tela, ferramentas de teste, decisões datadas e o que
falta testar em aparelho.

> **Estado do código em 03/11/2026 (main, 051d0c9):** a tela de rota tem 3 opções de perfil
> (`frontend/index.html:116-121`), região `aria-live` (`#anuncio-rota`), foco no título do
> resultado (`frontend/src/inicio/rota-tela.ts:341`), seletor de voz e velocidade, e o teste
> de contraste `frontend/src/design/contraste.test.ts`. A divisão em **4 perfis** (cegueira e
> baixa visão separadas), os títulos por tela com anúncio de mudança de tela e o botão "Ativar
> voz" estão **em implementação** nos branches `a11y/perfis-leitor` e `rotas/perfis-quatro`
> (sem commits em relação à main na hora desta escrita). Onde esta página descreve o
> comportamento-alvo, está marcado **(alvo)**. Confira o código antes de citar no TCC.

## 1. Metas

| Meta | Critério WCAG 2.2 | Nível | Valor |
|---|---|---|---|
| Texto comum | 1.4.3 Contraste (mínimo) | AA | **4,5:1** (texto grande: 3:1) |
| Borda de controle, anel de foco, marcadores | 1.4.11 Contraste de não texto | AA | **3:1** |
| Tema de alto contraste (opcional) | 1.4.6 Contraste (melhorado) | AAA | 7:1 (texto grande: 4,5:1) |
| Áudio não toca sozinho | 1.4.2 Controle de áudio | A | só começa por ação do usuário |

Meta geral: **WCAG 2.2 nível AA no mínimo** (pedido da orientadora, 27/10/2026). Os limites
são rígidos, sem arredondar: 4,499:1 reprova.

## 2. Perfis (mantendo o padrão visual)

O padrão visual (tokens em `frontend/src/design/tokens.json`) é o mesmo para todos. O perfil
muda a **rota** e o **texto da interface**, não o visual.

| Perfil | Rota | Interface |
|---|---|---|
| **Cegueira** | Penaliza escada, travessia e trecho não conferido a pé (`PENALIDADE_PERFIL_VISUAL=2.0`); avisa piso tátil ausente e antecipa escada. **Regras PROVISÓRIAS.** | Instruções curva a curva com distância e tempo; foco e anúncios para leitor de tela; "Ouvir com a voz do app" opcional; aviso "Rota provisória: confira com a bengala". |
| **Baixa visão** | Mesmas regras provisórias da cegueira (separar só se a orientadora definir diferença). **PROVISÓRIO.** | Mesmo conteúdo textual, mais mapa visual com contraste alto e texto ampliável (zoom, sem rolagem horizontal); tema de alto contraste disponível. |
| **Cadeirante** ("Cadeirante (evita escadas)") | Escada e trecho `acessivel_cadeirante = false` são **excluídos** da rota (`backend/app/rotas/custo.py:24-28`); trecho sem classificação pesa como não verificado. | Mesma interface; sem instruções de bengala. |
| **Sem restrição** | Menor caminho, com custos normais. | Interface padrão. |

Pontos a validar com a orientadora: se cegueira e baixa visão têm regras de rota distintas;
critério de "acessível" por perfil e quem valida (pendência #6).

## 3. Leitor de tela (TalkBack e VoiceOver)

- **Mudança de tela (alvo):** cada tela tem um `h1`/`h2` único e `tabindex="-1"`; ao trocar de
  tela o foco vai para esse título e o leitor o lê. Já é assim na medição
  (`frontend/src/medicao/pagina.ts:505-520`) e no resultado da rota
  (`frontend/src/inicio/rota-tela.ts:341`).
- **Onde o usuário está:** o título diz a tela (ex.: "Escolher destino", resultado "De X para
  Y"); o `document.title` acompanha **(alvo)**.
- **Região aria-live:** `#anuncio-rota` (`role="status"`, `aria-live="polite"`, `aria-atomic`)
  recebe um resumo curto quando a rota aparece (`frontend/src/rotas/resumo.ts`). O texto só é
  reescrito se mudou, para não repetir anúncio.
- **Botão "Ativar voz" (alvo):** a voz do app (Web Speech) só começa por toque do usuário.
  Hoje é "Ouvir com a voz do app". **Não há áudio automático** porque (1) navegadores móveis
  bloqueiam fala/áudio sem gesto do usuário e (2) o WCAG 1.4.2 pede que som iniciado
  sozinho tenha controle; além disso, voz do app sobreposta à do leitor de tela atrapalha.
- **Leitura pelo leitor de tela da pessoa (decisão 27/10):** a leitura das instruções é feita
  pelo leitor de tela do aparelho, com a voz e a velocidade que a pessoa já usa. A voz do app
  é opcional e escolhível (voz e velocidade em `frontend/index.html:69-83`).
- **Simulação de caminhada:** "Simular caminhada" é demonstração; a posição é imaginária e a
  tela deve dizer isso.

## 4. Ferramentas e roteiro de testes

Acesso às fontes: 03/11/2026.

| Ferramenta | O que faz | Custo | Plataforma | Quando usar neste projeto |
|---|---|---|---|---|
| [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/) | Razão de contraste entre duas cores (hex), AA/AAA para texto, texto grande e objetos gráficos; API JSON, conta-gotas | gratuito (a página não cita preço) | web | Checar um par novo de cores antes de pôr em `tokens.json` |
| [Colour Contrast Analyser](https://vispero.com/color-contrast-checker/) (TPGi/Vispero) v3.5.5 | Conta-gotas sobre qualquer coisa na tela (inclusive mapa e tiles), WCAG 2.0/2.1/2.2, simulador de daltonismo, copia resultado para relatório | gratuito | Windows e Mac | Medir cores **renderizadas** (marcador sobre tile OSM, anel de foco) e simular daltonismo |
| [axe-core](https://github.com/dequelabs/axe-core) (MPL-2.0) | Motor de testes automáticos, regras WCAG 2.0/2.1/2.2; "em média 57% dos problemas WCAG"; itens incertos vêm como "incomplete" | gratuito | JS (npm), roda em testes/CI | **CI**: `axe.run()` sobre as páginas no teste de frontend |
| [axe DevTools](https://www.deque.com/axe/devtools/) (Deque) | Extensão Chrome sobre o axe-core, com testes guiados | extensão gratuita; recursos guiados/IA por teste ou plano pago (preço não informado na página) | Chrome | Revisão pontual de uma tela |
| [Lighthouse](https://developer.chrome.com/docs/lighthouse/accessibility/scoring) | Auditoria no Chrome; nota de acessibilidade ponderada, baseada no axe; "auditorias manuais não entram na nota" | gratuito | Chrome DevTools, CLI | Conferência rápida; **nota 100 não prova acessibilidade** |
| [WAVE](https://wave.webaim.org/) (WebAIM) | Extensão que marca erros e alertas na própria página; serve para páginas locais ou dinâmicas | extensão gratuita (API paga, preço não informado) | Chrome, Firefox, Edge | Revisão visual de estrutura, rótulos, ordem de títulos |
| [Accessibility Scanner](https://support.google.com/accessibility/android/answer/6376570) (Android) | Varre telas e sugere: rótulos, tamanho de alvo de toque, itens clicáveis, contraste; "não substitui teste manual" | gratuito | Android 9+ (Google Play) | **No celular real** que for usar o protótipo (alvos >= 44 px, contraste na tela renderizada) |
| Accessibility Inspector (Xcode) | Mostra rótulo, valor, traços de cada elemento e roda auditoria (rótulo, contraste, alvo pequeno); liga o VoiceOver | gratuito com o Xcode | macOS, para iOS (simulador ou aparelho) | Se houver um Mac emprestado; a página oficial da Apple não carregou na pesquisa, descrição **a confirmar** em [developer.apple.com](https://developer.apple.com/documentation/accessibility/accessibility-inspector) |
| Definição W3C | [1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [1.4.6](https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced.html), [1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html), [1.4.2](https://www.w3.org/WAI/WCAG22/Understanding/audio-control.html) | gratuito | web | Texto de referência para o TCC |

**Fórmula (W3C, WCAG 2.2, glossário):** `L = 0,2126·R + 0,7152·G + 0,0722·B`, com cada canal
linearizado (`c = v/255`; se `c <= 0,03928` vale `c/12,92`, senão `((c+0,055)/1,055)^2,4`), e
razão `(L1 + 0,05) / (L2 + 0,05)` com L1 a maior luminância. Fonte:
<https://www.w3.org/TR/WCAG22/#dfn-relative-luminance> (a busca automática não trouxe o
trecho do glossário; a fórmula acima é a do WCAG e é a que o teste do projeto usa. A
revisão atual do WCAG escreve o limiar como 0,04045; a diferença não muda nenhuma razão na
prática, **conferir no glossário ao citar**).

**O que o projeto já cobre:** `frontend/src/design/contraste.test.ts` implementa a fórmula
do W3C e testa, nos **3 temas** (claro, escuro, alto contraste): 17 pares de texto (mínimo 4,5:1;
7:1 no alto contraste) e 15 pares de não texto (borda de controle, anel de foco, marcadores
do mapa sobre o tile OSM, rota, barra de progresso; mínimo 3:1). **Não cobre:** cor
renderizada de fato no aparelho, estados novos fora da lista, texto sobre imagem de mapa
real, tamanho de alvo, rótulos, ordem de foco, leitor de tela.

**Roteiro mínimo recomendado:**
1. **CI (automático):** manter `contraste.test.ts` (sempre que criar cor nova, incluir o par
   na lista); acrescentar axe-core sobre `index.html` e `medicao.html` (por exemplo com
   jsdom ou Playwright), falhando em violações AA. Lighthouse só como conferência.
2. **Revisão de desenho (por mudança):** WebAIM ou Colour Contrast Analyser para cada par
   novo; CCA com o simulador de daltonismo uma vez por tema.
3. **Manual em aparelho (antes de teste com usuários e antes do TCC II):** Android com
   TalkBack + Accessibility Scanner; iPhone com VoiceOver (+ Accessibility Inspector se
   houver Mac). Roteiro de cada perfil: escolher destino, traçar rota, ouvir as
   instruções, usar "Ativar voz", trocar de tela e conferir o anúncio; repetir com tela a
   200% de zoom e com tema de alto contraste.
4. **Registro:** anotar aparelho, versão do sistema, leitor, resultado e data em
   `docs/diario-de-campo.md`.

## 5. Registro de decisões

| Data | Quem | Decisão |
|---|---|---|
| 27/10/2026 | Orientadora (reunião) | Seguir WCAG, no mínimo AA, contraste 4,5:1 para texto comum. |
| 27/10/2026 | Orientadora | Pesquisar ferramentas de teste de contraste (feito, seção 4). |
| 27/10/2026 | Orientadora | Perfis: cegueira, baixa visão, cadeirante e sem restrição, mantendo o padrão visual. |
| 27/10/2026 | Orientadora | Compatibilidade com TalkBack e VoiceOver: anunciar mudança de tela e onde o usuário está. |
| 27/10/2026 | Orientadora | Documentar todas as decisões e alterações (este arquivo). |
| 27/10/2026 | Rodrigo | Instruções curva a curva na v0, com aviso de rota provisória ("Confira com a bengala"). Limiares provisórios em `decisoes-pendentes.md`. |
| 27/10/2026 | Rodrigo | A leitura é feita pelo **leitor de tela da pessoa**; a voz do app é opcional (tirado "(leitura em voz automática)" do perfil, commit 1e9dea0). |
| 27/10/2026 | Rodrigo | **Simulação de caminhada** com voz e vibração, para demonstração sem estar no campus. |
| 27/10/2026 | Rodrigo | **Voz do app escolhível** (voz e velocidade). |
| 27/10/2026 | Rodrigo | Rótulo do perfil: **"Cadeirante (evita escadas)"**; escada excluída da rota. |
| 03/11/2026 | Documentação | Sem áudio automático: bloqueio do navegador e WCAG 1.4.2 (seção 3). |
| 03/11/2026 | Rodrigo | Tela "Orientação ao vivo": estado em texto grande com palavra e símbolo (✓ Na rota, ✕ Você saiu da rota, ◆ Sem GPS confiável, ★ Você chegou); prioridade perigo/alta em região `aria-live` assertive dedicada (`#alerta-orientacao`), o resto na polite; aviso de segurança permanente; botão Parar sempre visível. Detalhes em `docs/planos/m4-orientacao-ao-vivo.md` §7c. |

## 6. O que ainda falta testar em aparelho real

- TalkBack (Android) e VoiceOver (iOS) em todas as telas: anúncio de mudança de tela, foco no
  título, leitura da região `aria-live` sem repetição.
- Funcionamento de "Ativar voz" e da fala da simulação em Safari/iOS e Chrome/Android.
- Contraste do marcador, da rota e do anel de foco **sobre o tile real** sob sol (celular ao ar livre).
- Alvos de toque (>= 44 px) e zoom de 200% sem rolagem horizontal.
- Vibração (o iOS não suporta `navigator.vibrate()`, pendência #2).
- Teste com pessoas cegas e de baixa visão só depois do CEP (pendência #8).
- Orientação ao vivo (GPS, bússola, Wake Lock, vibração, voz + aria-live juntos) no campus, com TalkBack e VoiceOver.
- axe-core no CI ainda não existe.
