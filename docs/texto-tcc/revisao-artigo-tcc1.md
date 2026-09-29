# Revisão do artigo e do pôster do TCC I — o que corrigir

> **RASCUNHO para a equipe revisar e adaptar.** Lista objetiva de correções para
> `docs/academico/artigo-tcc1.doc` ("Acessibilidade Mackenzie") e
> `docs/academico/poster-tcc1.pdf` ("Mackenzie sem Barreiras"), com uma sugestão de texto
> para cada item. As sugestões supõem as recomendações da equipe em
> [`../orientadora/pauta-reuniao.md`](../orientadora/pauta-reuniao.md); se a orientadora
> decidir diferente, ajustar. Referências conferidas (exceto as marcadas [CONFERIR]) em
> [`referencias.md`](referencias.md).
> Lida a versão do `.doc` do repositório (texto extraído em 29/09/2026).

## 1 Hipótese e objetivo prometem roteamento

**Onde.** Artigo: resumo ("projetamos a validação de uma arquitetura de rotas
inclusivas"), 1.2 Hipótese ("permitindo o cálculo de rotas inclusivas"), 1.3 Objetivo
("consultas de proximidade e roteamento"), 1.4 Justificativa ("roteamento urbano de alta
precisão"). Pôster: Motivação ("construindo uma base para identificar rotas mais
acessíveis"), Metodologia ("identificar rotas acessíveis") e Resultados ("geração de rotas
mais acessíveis").

**Problema.** A metodologia não prevê grafo viário nem cálculo de rotas, e o sistema não
os implementa (pendência #1).

**Sugestão (se o escopo for só a base):**
> *Hipótese:* A implementação de uma infraestrutura de banco de dados espacial baseada em
> *Volunteered Geographic Information* (VGI), acoplada a rotinas de validação espacial no
> *backend*, permite consolidar um repositório confiável sobre microacessibilidade urbana,
> que mitiga as limitações de granularidade dos mapas autoritativos e pode servir de base
> para o cálculo de rotas inclusivas em trabalhos futuros.

> *Objetivo (trecho):* […] um banco de dados espacial capaz de indexar coordenadas
> geográficas para consultas espaciais por região […].

No resumo, trocar "projetamos a validação de uma arquitetura de rotas inclusivas" por
"apresentamos uma camada de validação que transforma relatos voluntários em uma base de
barreiras confirmadas". Na justificativa, trocar "roteamento urbano de alta precisão" por
"dados de acessibilidade urbana com granularidade de calçada".

## 2 IBGE: 14,4 × 18,6 milhões, com o ano errado

**Onde.** Pôster: "cerca de 14,4 milhões de cidadãos no Brasil (IBGE, 2022)", mas a
referência é a PNAD Contínua. Artigo: "No Brasil, dados censitários apontam para
aproximadamente 18,6 milhões de cidadãos nessa condição (IBGE, 2022)".

**Problema.** São duas pesquisas diferentes, e o IBGE diz que elas não são comparáveis.
18,6 milhões (8,9%) é da **PNAD Contínua 2022**, uma pesquisa amostral, publicada em 2023;
14,4 milhões (7,3%) é do **Censo Demográfico 2022**, publicado em 2025. O artigo chama o
dado amostral de "censitário", e nenhum dos dois foi publicado em 2022. Detalhes e fontes
em [`referencias.md`](referencias.md), seção "A divergência 14,4 × 18,6 milhões".

**Sugestão (artigo e pôster, mesmo número):**
> No Brasil, o Censo Demográfico 2022 identificou 14,4 milhões de pessoas com deficiência,
> 7,3% da população de 2 anos ou mais (IBGE, 2025).

Na lista de referências, trocar "IBGE. PNAD Contínua - Pessoas com Deficiência. Rio de
Janeiro: IBGE, 2022." pela referência do Censo (IBGE, 2025). Se o texto quiser citar
também a PNAD, acrescentar: "A PNAD Contínua 2022 estimou 18,6 milhões (IBGE, 2023), mas
com questionário diferente; o IBGE adverte que os resultados das duas pesquisas não são
comparáveis (IBGE, 2025, p. 29)."

## 3 OMS: dado de 2011 sem citação

**Onde.** Resumo: "Cerca de uma em cada sete pessoas hoje vive com alguma deficiência.
Mundialmente, isso representa mais de um bilhão de indivíduos, sendo 18,6 milhões deles
cidadãos brasileiros." Introdução: "Estima-se que um bilhão de pessoas no mundo vivam com
alguma deficiência."

**Problema.** "Mais de um bilhão" e cerca de 15% são do *World report on disability* de
2011, sem citação. A estimativa atual da OMS (2022) é de 1,3 bilhão, 16%, 1 em cada 6. O
resumo também soma, na mesma frase, o dado mundial da OMS e o brasileiro do IBGE, de
pesquisas e métodos diferentes.

**Sugestão (introdução):**
> Estima-se que 1,3 bilhão de pessoas, cerca de 16% da população mundial, vivam com
> alguma deficiência significativa (WORLD HEALTH ORGANIZATION, 2022). No Brasil, o Censo
> Demográfico 2022 identificou 14,4 milhões de pessoas com deficiência (IBGE, 2025).

**Sugestão (resumo, sem citação, como é usual em resumo):**
> Cerca de uma em cada seis pessoas no mundo vive com alguma deficiência significativa; no
> Brasil, são 14,4 milhões de pessoas.

## 4 Referencial teórico fora de escopo

**Onde.** Artigo, último parágrafo do Referencial Teórico: inteligência artificial
(COPPIN, 2010; RUSSELL; NORVIG, 2021), visão computacional (SZELISKI, 2021), câmera de
profundidade (INTEL CORPORATION, 2020), imagens de satélite na agricultura (SATO, 2020,
um *blog*), segmentação de lesões de pele (ARORA et al., 2021; HAMEED et al., 2019;
KARTHIK et al., 2022). A frase de fecho ("anomalias espaciais, sejam elas em tecido humano
ou no asfalto urbano") não tem apoio nas fontes.

**Problema.** Nada disso aparece na metodologia nem no sistema. Falta, por outro lado, a
literatura do que o sistema faz: qualidade de VGI, DBSCAN e indexação espacial.

**Sugestão.** Remover o bloco e as oito referências e substituir por:
> A qualidade de dados geográficos voluntários é um dos principais desafios da área:
> contribuintes heterogêneos, com equipamentos e precisão diferentes e sem um filtro
> editorial, produzem dados de qualidade variável (HAKLAY, 2010; SENARATNE et al., 2017).
> Goodchild e Li (2012) distinguem três abordagens de garantia de qualidade: a de
> *crowd-sourcing*, em que a concordância de um grupo corrige os erros individuais; a
> social, baseada em moderadores de confiança; e a geográfica, que confronta a
> contribuição com o conhecimento sobre o lugar. No mapeamento de acessibilidade, o Project
> Sidewalk coleta rótulos de problemas em calçadas por *crowdsourcing* e avalia o efeito do
> voto da maioria sobre a acurácia (SAHA et al., 2019). Este trabalho adota a abordagem de
> *crowd-sourcing*: relatos próximos do mesmo tipo são agrupados pelo algoritmo DBSCAN
> (ESTER et al., 1996), e o grupo só é confirmado quando reúne relatos de um número
> mínimo de sessões distintas.

## 5 Metodologia: DBSCAN sem citação, R-Tree, vizinho mais próximo, microsserviços

**Onde e sugestão.**
- Etapa 4 cita "density-based spatial clustering" sem fonte. Acrescentar "(ESTER et al.,
  1996)" e nomear o algoritmo: "agrupamento espacial por densidade (DBSCAN)".
- Etapa 2: "uso de R-Trees para a indexação espacial, permitindo buscas de Nearest
  Neighbor". O índice criado é GiST, e a consulta implementada é por retângulo (*bbox*),
  não por vizinho mais próximo. Sugestão:
  > […] índices espaciais GiST, que no PostGIS implementam a R-Tree (GUTTMAN, 1984;
  > HELLERSTEIN; NAUGHTON; PFEFFER, 1995) e permitem recuperar de forma eficiente as
  > barreiras contidas na região visível do mapa.
- Etapa 3 e objetivo: "microsserviços". O sistema é uma única API REST. Trocar por
  "API REST (Python/FastAPI)".
- Etapa 4 chama-se "Coleta e Análise Qualitativa", mas descreve análise estatística, e a
  abordagem declarada é quanti-qualitativa. Sugestão: "Coleta e validação dos dados".
- Hipótese: "rotinas estatísticas de validação" → "rotinas de validação espacial" (o
  método é geométrico e por regra de sessões, não estatístico).

## 6 Etapa 1 promete atributos quantitativos

**Onde.** "Os dados de entrada consistem em coordenadas (x,y) e atributos quantificáveis
(altura do degrau, ângulo da rampa)."

**Problema.** O sistema grava tipo e severidade (1 a 3), não medidas (pendência #6).

**Sugestão (se ficar fora do escopo):**
> Os dados de entrada consistem em coordenadas geográficas, tipo de barreira, severidade
> percebida (de 1 a 3) e uma descrição opcional. Atributos métricos, como a altura de
> degraus e a inclinação de rampas, ficam para trabalhos futuros.

## 7 Referências com dados errados ou incompletos

Encontrados na conferência de 29/09/2026 (fontes em [`referencias.md`](referencias.md)):

| Referência | No artigo | Correto |
|---|---|---|
| Zahabi et al. (2023) | três autores; p. 2821-2838 | quatro autores (ZAHABI; ZHENG; MAREDIA; SHAHINI), v. 39, n. 14, p. 2942-2964, DOI 10.1080/10447318.2022.2088883 |
| Kulakov, Zavyalova e Shabalina (2017b) | v. 53, p. 1-10, jul. 2017 | n. 4 (53), p. 201-224, 2017, DOI 10.15622/sp.53.10; artigo em russo |
| Ortiz e Tang (2024) | out. 2024 | o Crossref registra 10 maio 2024 (ICICSE, Pequim); **[CONFERIR]** o mês no IEEE Xplore |
| Miyata et al. (2021; 2025) | art. 419; art. 160 | páginas 1-6 e 1-8 e DOIs confirmados; o número do artigo **[CONFERIR]** na ACM DL |
| IBGE | "IBGE, 2022" | IBGE (2023) para a PNAD e IBGE (2025) para o Censo (item 2) |
| Todas | sem DOI | acrescentar o DOI de cada artigo (lista pronta em `referencias.md`) |

Também conferir se Miyata et al. (2025), uma comparação entre mapas de acessibilidade
colaborativos e oficiais, sustenta a frase do pôster sobre "filtragem por proximidade
geográfica […] reduzindo alertas falsos" **[CONFERIR]**; se não, citar Goodchild e Li
(2012) e Ester et al. (1996) ali.

## 8 Funil do pôster (Figura 2)

**Problema.** 250 → 205 → 120 → 120 é ilustrativo; a unidade muda de alertas para
barreiras no agrupamento sem aviso, e o funil não mostra ruído nem barreiras pendentes.

**Sugestão.** No documento final, usar a figura gerada pelo sistema
(`docs/figuras/funil-simulacao.png`), com um painel para alertas e outro para barreiras,
os parâmetros na legenda e o título "SIMULAÇÃO"; depois da coleta, a figura com os dados
reais. Legenda sugerida:
> Figura X — SIMULAÇÃO: funil de validação com dados sintéticos (cenário de controle). As
> proporções foram fixadas pelo gerador e não são taxas observadas. Fonte: autores.

## 9 Cronograma

**Problema.** A tabela vai de agosto a maio (A, S, O, N, D, J, F, M, A, M) e não
corresponde ao calendário real do TCC II. Hoje o desenvolvimento (M0–M5.1) está concluído,
e a coleta (M6) está preparada, mas não realizada.

**Sugestão.** Refazer a tabela com as datas reais do semestre **[EQUIPE: preencher]**, em
três blocos: concluído (fundamentação, arquitetura, desenvolvimento e testes, CI/CD),
coleta em campo (preparação, coleta, execução do pipeline e figura com dados reais) e
fechamento (calibração com a orientadora, redação, defesa). Tirar "chaves de APIs (Google
Maps)" da Fase 2: o protótipo usa Leaflet com OpenStreetMap.

## 10 Títulos, autores e forma

- **Títulos divergentes:** artigo "Acessibilidade Mackenzie"; pôster "Mackenzie sem
  Barreiras: Mapeamento Colaborativo da Acessibilidade Urbana no Entorno Universitário".
  Sugestão: adotar o do pôster nos dois (é o nome do repositório e do sistema).
- **Autores [EQUIPE]:** conferir com a equipe e a orientadora a lista de autores do TCC II.
- **Arquitetura do pôster (Figura 1):** "TypeScript + Google Maps API" → "TypeScript +
  Leaflet/OpenStreetMap".
- **Resumo** termina com ".." (ponto duplo).
- **Introdução:** "SIG tradicionais são estáticos e omitidos em dados de
  microacessibilidade" → "são estáticos e omissos quanto a dados de microacessibilidade".
- **Cabeçalho:** os e-mails aparecem fundidos num endereço só (números de matrícula
  separados por vírgula antes de `@mackenzista.com.br`) → um e-mail completo por autor.
- **Metadados do `.doc`:** os metadados do arquivo trazem título e autor de outro
  documento; limpe-os antes de circular. No Word: Arquivo → Informações → Propriedades
  (corrigir título e autores) e Verificar se há problemas → Inspecionar documento
  (remover dados pessoais ocultos).
