# Plano: análise da medição de GPS no campus

> **Plano de 22/10/2026, escrito ANTES de haver dados.** Nenhum número aqui é resultado: são perguntas, métricas e critérios. Dado sintético nunca entra nesta análise. Marcações: **[REF?]** precisa de citação; **[CONFERIR]** depende de checar o app; **[DECIDIR]** precisa de decisão da equipe ou da orientadora.

**Objetivo:** transformar as medições de 22/10 (P01 a P10) em evidência para três decisões do sistema (raio de "chegou ao ponto", quando ficar em silêncio, quando pedir confirmação por referência física) e em texto para o E3.

**Entregas:** (1) script `analise_gps.py` e 4 tabelas/figuras em `docs/figuras/gps/`; (2) texto de resultados e ameaças para o E3; (3) uma linha por decisão, com o valor provisório que os dados sustentam.

**Prazos:** análise 26/10 (card "Análise da medição de GPS"), E3 27/10.

---

## 1. Perguntas de pesquisa e a decisão que cada uma alimenta

| # | Pergunta | Dado que responde | Decisão do sistema |
|---|---|---|---|
| P1 | Qual o erro típico e o pior caso de posição, por condição (céu aberto, entre prédios, entrada de prédio, coberto)? | `erro_m` por medição, agrupado por `condicao` | Raio de "chegou ao ponto" por condição; onde o sistema deve ser mais cauteloso |
| P2 | Os aparelhos (Android e iPhone) diferem? | `erro_m` por `aparelho`, mesmos pontos | Se o raio é um só ou depende do aparelho; limite da generalização |
| P3 | O celular "diz a verdade" sobre a própria precisão? | `erro_m` contra `precisao_m` (fração com erro <= precisão) | Se `precisao_m` pode ser usado como gatilho de silêncio, ou se só serve como sinal fraco |
| P4 | Quanto a posição oscila com a pessoa parada? | Dispersão entre as 3 repetições do mesmo ponto e aparelho | Janela de suavização e histerese ao decidir "chegou" (evitar anunciar e desanunciar) |
| P5 | Quanto a posição oscila andando, comparado a parado? | Trajeto (tipo `trajeto`, ~5 s) contra a mesma condição parada | Cadência de atualização da orientação enquanto a pessoa anda **[CONFERIR]** se haverá trajeto suficiente |
| P6 | A bússola é estável? | `bussola_oscilacao_graus`, `bussola_fonte` | Quando falar direção ("à sua direita") ou só distância; método 3 **[CONFERIR]** |

**Ligação com os métodos decididos (1, 2 e 3).** O que os dados dizem entra assim, sem inventar o método:

- **Raio de chegada (método 1):** o raio não pode ser menor que o erro típico da condição pior em que o ponto fica. Os dados dão o piso; o valor final é **[DECIDIR]** com a orientadora (pendência de precisão mínima).
- **Silêncio:** se P3 mostrar que o celular subestima o erro (erro > `precisao_m` com frequência), `precisao_m` sozinho não basta para calar o sistema. Princípio de segurança do CLAUDE.md: silêncio é melhor que palpite.
- **Confirmação por referência física (método 2):** onde o erro de P1 for comparável à distância entre marcos (ex.: P05 e P06, entradas próximas), a posição não distingue os dois, e a pessoa deve confirmar por um marco tátil ou sonoro.
- **Método 3:** a ser descrito no E3 com base em P6 e no que a equipe já decidiu **[CONFERIR com Rodrigo qual é o método 3 para não escrever errado]**.

Não há hipótese numérica prévia. Escrever limiares (por exemplo, "5 m") antes de ver os dados enviesaria a análise.

---

## 2. Métricas exatas e critérios mínimos

### 2.1 Unidade de análise e definição do erro

- Unidade: uma linha de `vw_erro_medicoes` (tipo `ponto`, com referência). **[CONFERIR]** em `frontend/src/medicao/pagina.ts` se cada "medição de 30 s" vira **uma** linha (posição final ou a de melhor precisão) ou várias. A resposta muda a definição de "repetição" abaixo.
- `erro_m` = distância em metros (SRID 31983) entre a posição medida e a referência do ponto. A referência é estimada por imagem de satélite, então **`erro_m` inclui a incerteza da referência**; chamar de "desvio em relação à referência estimada", nunca de "erro absoluto do GPS".

### 2.2 Métricas (todas em metros, salvo a fração)

| Métrica | Definição | Por quê |
|---|---|---|
| n | contagem de medições por célula | mostrar sempre; sem n a mediana não se interpreta |
| Mediana de `erro_m` | percentil 50 (interpolado, igual a `percentile_cont` do banco) | resistente a um outlier; é o "típico" |
| p90 de `erro_m` | percentil 90 interpolado | com n pequeno é instável: só reportar com n >= 10; abaixo disso, reportar o **máximo** |
| Máximo de `erro_m` | maior valor da célula | o pior caso observado, o que importa para segurança |
| Fração dentro da precisão | média de `(erro_m <= precisao_m)` | responde P3 (é o que a view já calcula) |
| Razão erro/precisão | mediana de `erro_m / precisao_m` (só `precisao_m > 0`) | complementa a fração: quanto o celular erra a escala, não só se acerta |
| Dispersão das repetições | para cada ponto x aparelho: maior distância entre duas das 3 posições medidas (metros, SRID 31983) | responde P4; não depende da referência, então **não inclui a incerteza do satélite** (vantagem para o texto) |
| Viés (sistemático) | distância entre o centroide das 3 posições e a referência | separa "erro que se repete" (viés, ou referência errada) de "erro que oscila" (ruído) |

Células de análise: condição, aparelho, condição x aparelho, ponto x aparelho. A célula ponto x aparelho tem no máximo 3 medições: **não** calcular p90 nela, só mediana, máximo e dispersão.

### 2.3 Critérios mínimos

- **Ponto x aparelho entra na análise** se tiver >= 2 medições válidas. Com 1, fica na tabela de cobertura, marcada "n = 1", e não entra em dispersão.
- **Condição x aparelho:** reportar mediana e máximo com n >= 3. Reportar p90 só com n >= 10. Abaixo de 3, mostrar os pontos individuais e dizer que não há estimativa.
- **Comparação entre aparelhos (P2):** só descritiva (lado a lado, mesmos pontos). Com 2 ou 3 aparelhos não há teste estatístico com sentido; **não** escrever "significativamente diferente" **[REF?]** para o princípio de não inferir com amostra mínima.
- **Ponto pulado ou com poucos dados:** não preencher, não interpolar, não "completar" com outro aparelho. Registrar em uma tabela de cobertura (ponto x aparelho, n) e dizer no texto qual ponto ficou sem dados e por quê (se a equipe souber: obra, chuva, sem sinal). Se uma **condição** perder todos os pontos de um aparelho, dizer que a conclusão vale só para o outro aparelho.
- **Medição inválida:** `precisao_m` ausente ou nula é impossível (a CHECK exige), mas `erro_m` absurdo (por exemplo, > 100 m) **não** se descarta sozinho: listar, conferir o `observacao` e o horário, e só então decidir em conjunto. Todo descarte vai numa tabela de exclusões com o motivo.
- **Repetir a coleta:** se um ponto de condição crítica (entre prédios, entrada) ficar abaixo do mínimo, repetir é decisão da equipe, depois da análise (o cronograma E5 já prevê isso).

---

## 3. Tabelas e gráficos propostos (no máximo 5)

Regras comuns, de acordo com a skill de gráficos do projeto: uma só escala por gráfico (nada de eixo duplo); cor nunca é o único código (marcador diferente por aparelho e legenda); no máximo 2 ou 3 séries; texto em tinta neutra, nunca na cor da série; rótulos e legendas em português; fundo claro e versão que imprime em preto e branco; mostrar cada medição quando n é pequeno (não esconder em caixa); legenda fixa em todas as figuras:

> *A referência de cada ponto é estimada por imagem de satélite; o desvio mostrado inclui a incerteza dessa referência e não é o erro absoluto do GPS. Dados reais de campo, 22/10/2026, [n] medições, [k] aparelhos.*

| # | Tipo | Conteúdo exato | Por que esse tipo |
|---|---|---|---|
| **T1** | Tabela | Cobertura: linhas P01 a P10 (com condição), colunas por aparelho, célula = n de medições válidas (0 a 3, mais o n de trajeto); linha final com o total. Células abaixo do mínimo em destaque **com texto** ("n = 1"), não só cor | Mostra de saída o que a amostra permite afirmar e o que não |
| **F1** | Gráfico de pontos em faixas (strip plot) horizontal | Eixo x: desvio em relação à referência (m), começando em zero. Uma faixa por condição (4 faixas, ordem por mediana). Cada medição é um ponto (leve jitter vertical), **marcador por aparelho**. Traço vertical longo = mediana da condição; traço curto = máximo | Com 3 por ponto e ~10 pontos, o n é pequeno: mostrar todos os dados é mais honesto que boxplot, e o leitor vê a sobreposição entre condições (P1 e P2) |
| **F2** | Dispersão (scatter) com diagonal | Eixo x: `precisao_m` informada pelo celular (m). Eixo y: desvio medido (m). Mesma escala nos dois eixos (quadrado). Reta y = x tracejada rotulada "erro igual à precisão informada". Pontos acima = celular **subestimou** o erro. Marcador por aparelho. Anotar no canto a fração dentro da precisão por aparelho | É a forma direta de P3: o leitor vê quantos pontos caem acima da diagonal e quão longe |
| **T2** | Tabela | Por ponto x aparelho: condição, n, mediana, máximo, dispersão das repetições (m), fração dentro da precisão. Ordenada por ponto. Sem p90 (n <= 3). Uma segunda tabela-resumo por condição: n, mediana, p90 (só se n >= 10), máximo | Número exato para citar no texto; o leitor consulta, não "lê" |
| **F3** | Pequenos múltiplos (um painel por ponto, 10 painéis, mesma escala em metros) | Em cada painel: posições medidas (marcador por aparelho) em torno da referência (cruz no centro), eixos em metros leste/norte relativos à referência (SRID 31983), círculo de 5 m de referência de escala (apenas régua, não limiar). Ordem por condição | Mostra viés (nuvem deslocada) e oscilação (nuvem espalhada) ao mesmo tempo, algo que a mediana esconde; ajuda a decidir referência física |

Opcional se houver trajeto suficiente (**só se sobrar tempo; não conta entre os 5**): T3 "parado x andando": mediana da oscilação nas duas situações, por condição. **[CONFERIR]** quantos trajetos existirão; com poucos, descrever em texto, sem figura.

Cores: usar a paleta categórica validada da skill de dataviz (2 aparelhos bastam; uma terceira série é "Outros"). Rodar o validador de paleta (`validate_palette.js`) no momento de gerar F1 a F3; **[CONFERIR]** que o script do projeto de funil (`backend/scripts/gerar_figura_funil.py`) usa o mesmo estilo, para as figuras do E3 parecerem do mesmo conjunto.

---

## 4. Pipeline reprodutível

### 4.1 De onde vêm os dados

| Origem | Uso | Cuidado |
|---|---|---|
| **A. `GET /api/medicoes/analise`** (header `X-Token-Admin`) | Só confere totais por ponto x aparelho e por condição; devolve agregados, **sem** medições individuais | Não serve para F1 a F3, que precisam de cada medição |
| **B. CSV do app** ("Exportar CSV", um por aparelho, colunas em `CABECALHO_CSV`) | **Fonte principal** para F1 a F3 e T1/T2: tem latitude, longitude e `precisao_m` por linha | O CSV **não** traz a referência: o script lê as coordenadas de `db/seeds/003_pontos_controle.sql` (as mesmas da view) |
| **C. Consulta somente leitura ao banco** (`vw_erro_medicoes`) | Verificação cruzada: o erro calculado no Python deve bater com o da view (tolerância de 0,1 m) | Banco de produção: só o Rodrigo ou o agente de infra executa, com o túnel; este agente não acessa |

Plano: **B como fonte, A e C como conferência.** Se os CSV dos aparelhos divergirem do banco (medição que ficou na fila do celular e não subiu), a diferença vira nota no texto.

### 4.2 Script proposto

Arquivo: `backend/scripts/analisar_medicao_gps.py` (mesmo lugar dos outros scripts de análise).

- **Dependências:** só a biblioteca padrão (`csv`, `statistics`, `math`, `json`, `argparse`) para tabelas e métricas; `matplotlib` já existe no grupo opcional `analise` do `pyproject.toml` (`uv sync --group analise`) para as figuras. Nada novo no `pyproject.toml`.
- **Distância em metros:** converter lat/lon (graus, SRID 4326) em plano métrico sem biblioteca nova. Com a extensão do campus (~500 m), aproximação equirretangular é suficiente: `dx = (lon - lon0) * cos(lat0) * 111320`, `dy = (lat - lat0) * 110574` (aproximação em metros por grau; documentar no código). **[CONFERIR]** que difere da distância em 31983 (ST_Transform) por menos de 0,1 m nesse alcance; a conferência com a origem C faz isso. A decisão fica documentada no glossário se a aproximação for mantida.
- **Passos:**
  1. Ler os CSV da pasta de entrada (argumento `--entrada`), juntar, manter `tipo = ponto` (e guardar `trajeto` à parte).
  2. **Filtros:** descartar `aparelho` que começa com "Teste" (sem diferenciar maiúsculas) e linhas sem `ponto`, `latitude` ou `precisao_m`; contar e listar cada descarte com motivo (tabela de exclusões).
  3. Juntar com a referência do ponto (lida do seed) e calcular `erro_m`, viés, dispersão.
  4. Calcular as métricas da seção 2 com o critério mínimo, marcando "insuficiente" em vez de calcular.
  5. Gravar `resumo.json` (para o texto), T1 e T2 em CSV e em Markdown, e F1 a F3 em SVG e PNG.
  6. Rodar a conferência contra o JSON da origem A (`--conferir-api arquivo.json`) e falhar com mensagem clara se os totais não baterem.
- **Testes:** `backend/tests/test_analisar_medicao_gps.py` com **dados fabricados mínimos escritos no teste, rotulados como fixture de teste e nunca gravados em `docs/`**. Casos: mediana e percentil iguais aos de `percentile_cont`; filtro "Teste"; célula abaixo do mínimo vira "insuficiente"; dispersão de 3 pontos conhecidos (triângulo 3-4-5).
- **Alternativa (planilha):** se o script não ficar pronto até 24/10, a planilha com as mesmas colunas e fórmulas (`MEDIANA`, `PERCENTIL.INC`, distância pela aproximação acima) serve para a mediana, o máximo e T1/T2; as figuras F1 a F3 pedem o script.

### 4.3 Onde ficam os arquivos e o que **não** pode entrar

| Arquivo | Onde | Vai para o Git? |
|---|---|---|
| CSV brutos exportados | `dados-campo/gps/` (pasta no `.gitignore`; só na máquina de quem analisa) | **Não** |
| Resumo agregado (`resumo.json`, T1, T2 em CSV) | `docs/dados/gps/` | Sim, depois da revisão abaixo |
| Figuras F1 a F3 (SVG e PNG) | `docs/figuras/gps/` | Sim |
| Script e teste | `backend/scripts/`, `backend/tests/` | Sim |

**Revisão antes de commitar dado:** (a) nenhum `user_agent`, `observacao` livre ou horário exato que identifique uma pessoa; (b) nenhuma coordenada que não seja de ponto de controle (os 10 pontos são públicos do campus; coordenadas de casa ou de trajeto até o campus **não** entram, e o trajeto de ida e volta de quem mediu só entra agregado); (c) nome do aparelho em modelo ("Galaxy A54"), nunca nome de pessoa; (d) linhas "Teste*" fora; (e) **[DECIDIR]** se o repositório público recebe medições individuais (3 por ponto) ou só os agregados, a decisão é da equipe, e o padrão é só agregados.

---

## 5. Ameaças à validade e como escrever no E3

Escrever como seção própria ("Limitações da medição"), em voz direta, sem pedir desculpa e sem esconder. Modelo de cada item:

| Ameaça | O que acontece | Como dizer no E3 |
|---|---|---|
| **Referência por satélite** | A "verdade" é estimada em imagem; erro de georreferenciação da imagem (de alguns metros **[REF?]**) soma-se ao do GPS | "O desvio medido é a distância até uma referência estimada, não o erro absoluto do GPS. Medidas menores que a incerteza da referência não são interpretáveis." Dispersão das repetições (que não usa a referência) vai ao lado para compensar |
| **Poucos aparelhos** | Um Android e um iPhone (ou os que a equipe tiver); chips e antenas diferem **[REF?]** | "Resultados descrevem estes aparelhos, não a população de celulares." Sem generalizar, sem teste estatístico |
| **Um dia, um horário** | Constelação de satélites, ionosfera e clima variam **[REF?]** | "Medição única em 22/10/2026, [horário], [clima observado]. Não captura variação diária." Indicar como repetição futura |
| **Pessoas paradas e posição do corpo** | O corpo, o segurar o aparelho e a multidão atenuam o sinal **[REF?]** | Registrar como o aparelho foi segurado (mão, bolso) **[CONFERIR]** se o protocolo da equipe padronizou; se não, dizer que não houve padronização |
| **Multipath entre prédios e junto às entradas** | Reflexos fazem a posição "pular" **[REF?]**; é o caso em que `precisao_m` mais engana | Mostrar F2 por condição e dizer que o pior caso observado é o que o sistema deve respeitar |
| **Amostra pequena por célula** | 3 repetições por ponto; mediana e p90 instáveis | Citar o n em toda tabela; não usar p90 com n < 10; não apresentar intervalo de confiança |
| **Reativo ao pesquisador** | Quem mede conhece a referência e fica no lugar exato do marco | Dizer que a posição da equipe é mais regular do que a de uma pessoa cega em uso real |
| **Trajeto sem referência** | Andando, não há "verdade" ponto a ponto | Descrever só oscilação (suavidade), não erro |
| **Ponto 11 e 12** | Aceitos pelo app, sem referência | Fora da análise; dizer que não existem |

Nunca escrever que os dados "provam" a precisão do sistema; escrever "indicam" e dizer a condição. Valor de precisão do estado da arte vem de **[REF?]** (documentação de GNSS em celulares), não de memória.

---

## 6. Cronograma

| Quando | O que | Quem |
|---|---|---|
| **22/10 (hoje)** | Medição em campo. Ao fim: cada aparelho exporta o CSV e o envia ao Maurício (canal da equipe, nunca em repositório público). Conferir `GET /medicoes/resumo` para ver se subiu tudo | Equipe; Maurício confere |
| **23/10** | Receber CSV; conferir cobertura (T1) e anotar pontos pulados. **[DECIDIR]** se algo precisa ser repetido antes de 26/10. Rodrigo responde as perguntas **[CONFERIR]** (30 s: 1 linha ou várias; método 3) | Maurício; Rodrigo |
| **23 a 24/10** | Script, testes e T1/T2 (agente de backend, a pedido do orquestrador); rodar sobre os CSV reais assim que chegarem, nunca sobre sintético no texto | Agente `backend-api` (código); Rodrigo revisa |
| **25/10** | Figuras F1 a F3; conferência contra a API/banco (origem A e C, só leitura, feita pelo Rodrigo ou pelo agente de infra) | Agente `backend-api`; Rodrigo (conferência) |
| **26/10** | **Análise da medição de GPS entregue:** `resumo.json`, tabelas e figuras; Maurício lê os números e escreve as 3 conclusões e as decisões provisórias (raio, silêncio, referência) | **Maurício** (dono do card); Rodrigo revisa |
| **26/10 à noite** | Texto de resultados e ameaças (seção 5) no rascunho do E3, com [REF?] marcados | Agente `documentacao-tcc`, a partir dos números do Maurício |
| **27/10** | E3 entregue; revisão do Maurício e do Rodrigo; marcações [REF?] viram citações ou ficam abertas e declaradas | Equipe; Rodrigo fecha |
| **~27/10** | Reunião com a orientadora: levar T2, F1, F2 e as 3 decisões provisórias para validar | Rodrigo, Maurício |

**Risco de prazo:** o script depende do CSV chegar até 23/10. Plano B: planilha para T1/T2 em 26/10 e figuras F1 a F3 no E3 de 27/10 só se prontas; senão, descrever em texto e entregar figuras na versão seguinte, dizendo isso no texto.

---

## 7. Pendências para decidir ou conferir

1. **[CONFERIR]** o que o app grava numa "medição de 30 s": 1 linha (posição final ou melhor) ou várias. Define "repetição" e a dispersão.
2. **[CONFERIR]** qual é o método 3 de confirmação, para o E3 não descrever errado.
3. **[DECIDIR]** se o repositório público recebe medições individuais ou só agregados (padrão deste plano: só agregados).
4. **[DECIDIR]** se repetir pontos com n abaixo do mínimo antes de 26/10.
5. **[DECIDIR COM A ORIENTADORA]** o raio de "chegou ao ponto" e a precisão mínima para orientar (pendência de precisão mínima).
6. **[CONFERIR]** que a aproximação métrica do script difere da `ST_Transform` em menos de 0,1 m no campus; se não, usar a distância do banco.
7. Registrar no `.gitignore` a pasta `dados-campo/` antes da primeira exportação.
