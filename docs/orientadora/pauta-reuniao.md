# Pauta da reunião com a orientadora

> Rascunho da equipe (29/09/2026). Profa. Dra. Ana Graziela de Almeida Valiengo.
> Objetivo: fechar as decisões que a defesa precisa justificar e que o código deixou
> **provisórias e configuráveis**. Fonte de cada item: [`decisoes-pendentes.md`](../decisoes-pendentes.md).
> Todo número abaixo marcado **SIMULAÇÃO** vem de dados sintéticos, não de coleta real.

## Situação em uma frase

O software está pronto até o M5.1 (entrada, pipeline de validação em 4 estágios,
estatísticas do funil, mapa, testes ponta a ponta e CI/CD). A coleta em campo (M6) está
preparada ([`coleta-em-campo.md`](../coleta-em-campo.md)), mas não foi feita: até agora
só há dados de **SIMULAÇÃO** ([figura do funil](../figuras/funil-simulacao.png)).

## Ordem sugerida

| # | Assunto | Por que agora | Tempo |
|---|---|---|---|
| 1 | Roteamento | muda hipótese e objetivo do texto | 10 min |
| 7 | Estágio 3 conta alertas | decisão de método no núcleo do TCC | 10 min |
| 4 | Calibração (eps, min_confirmacoes) | define o que se mede na coleta | 10 min |
| 2 | Taxonomia | precisa estar fechada **antes** da coleta | 5 min |
| 3 | Polígono da área | precisa estar fechado **antes** da coleta | 5 min |
| 6 | Atributos quantitativos | muda a Etapa 1 da metodologia | 5 min |
| — | Informes (#5, texto, consentimento, cronograma) | só registrar | 5 min |

---

## #1 Escopo de roteamento

**Contexto.** O pôster fala em "identificar rotas mais acessíveis" e a hipótese do artigo
diz "permitindo o cálculo de rotas inclusivas"; o objetivo cita "consultas de proximidade
e roteamento". A metodologia, porém, não tem grafo viário, custo de trajeto nem
pgRouting, e nada disso foi implementado (regra G11 do plano). Hoje o sistema entrega a
**base validada** de barreiras, consultável por bbox.

**Opções.**
- (a) Escopo = a base de dados confiável que viabiliza rotas; roteamento vira trabalho
  futuro.
- (b) Implementar roteamento (pgRouting sobre a malha viária do OpenStreetMap, com custo
  pelas barreiras).
- (c) Meio-termo sem grafo: consultar as barreiras próximas de um trajeto dado,
  sem calcular a rota.

**Recomendação da equipe:** (a). O prazo do TCC II já está ocupado pela coleta (M6) e a
contribuição do trabalho é a validação, não o roteamento.

**O que muda.**
- (a) Código: nada. Texto: reescrever hipótese, objetivo, resumo e o "rotas mais
  acessíveis" do pôster (sugestões em [`revisao-artigo-tcc1.md`](../texto-tcc/revisao-artigo-tcc1.md), item 1).
- (b) Migration nova (extensão pgRouting), importação e manutenção da malha viária,
  função de custo, endpoint novo, testes e um marco a mais no cronograma.
- (c) Um endpoint novo com consulta espacial; o texto ainda precisa tirar "cálculo de
  rotas" da hipótese.

**Evidência.** Metodologia do artigo (Etapas 1–4, sem grafo); o contrato da API não tem
rota de trajeto ([`api.md`](../api.md)).

## #7 O estágio 3 conta alertas, não sessões

**Contexto.** O `minpoints` do DBSCAN conta **alertas**. Uma sessão que relata duas
vezes no mesmo lugar já forma um cluster, e o que seria ruído vira uma barreira
`pendente`, visível no mapa. Relatos repetidos também podem ligar dois clusters reais.
A regra das sessões distintas (anti-Sybil) protege só a **promoção** (estágio 4): uma
pessoa sozinha nunca passa de `pendente`.

**Opções.**
- (a) Manter e discutir no texto como limitação, apoiada no protocolo de coleta "uma
  barreira, um relato por sessão" (`coleta-em-campo.md` §2).
- (b) Deduplicar por sessão antes do DBSCAN (um ponto por sessão e tipo numa vizinhança,
  ou `minpoints` contado em sessões distintas).

**Recomendação da equipe:** (a) para a entrega, com a limitação declarada em
[`ameacas-validade.md`](../texto-tcc/ameacas-validade.md); (b) como trabalho futuro. Os
alertas brutos ficam guardados, então (b) pode ser aplicada depois sobre os mesmos dados
reais, reexecutando o pipeline.

**O que muda.**
- (a) Código: nada. Texto: um parágrafo na validação e nas ameaças à validade.
- (b) `app/validacao/clustering.py` e `pipeline.py`, testes novos, nova rodada da análise
  de sensibilidade e da figura; muda o núcleo do método, então a seção de validação do
  texto é reescrita.

**Evidência (SIMULAÇÃO).** A população `sessao_repetida` (uma sessão, vários relatos no
mesmo lugar) vira uma barreira `pendente`, e não ruído, com `eps` = 8 m e qualquer
`min_confirmacoes` ≥ 2 (`decisoes-pendentes.md` #4 e #7). Ou seja: a promoção barra a
pessoa sozinha, mas o mapa mostra a barreira dela como pendente.

## #4 Calibração de `eps` e `min_confirmacoes`

**Contexto.** Valores provisórios no `.env`: `eps` = 8 m, `minpoints` = 2,
`MIN_CONFIRMACOES` = 3. Foram escolhidos para o protótipo. A análise de sensibilidade
(SIMULAÇÃO) mostra em que faixa o pipeline funciona sob erros de posição **supostos**;
o erro real de GPS só a coleta mede. Trocar os valores é só `.env` + reexecutar o
pipeline (reconstrução completa, D6).

**Evidência (SIMULAÇÃO, semente 42, dispersão de até 3 m, `minpoints` = 2).**
Controle com 20 aglomerados de 2 a 5 sessões, 5 sessões repetidas e 40 ruídos; `eps` = 8 m:

| min_confirmacoes | confirmadas obtidas / esperadas | pendentes obtidas / esperadas | aglomerados (barreiras reais) que ficam pendentes |
|---|---|---|---|
| 2 | 20 / 20 | 5 / 5 | 0 de 20 |
| 3 (atual) | 11 / 11 | 14 / 14 | 9 de 20 |
| 4 | 9 / 9 | 16 / 16 | 11 de 20 |

- O pipeline aplica a regra exatamente; o que `min_confirmacoes` decide é **quantas
  barreiras reais ficam pendentes**. A simulação não tem relatos falsos de sessões
  distintas no mesmo lugar, então mostra só o **custo** de subir o valor, não o benefício.
- `eps`: o controle acerta 100% de 8 a 20 m, mas isso vale **por construção da população
  de controle** (grupos bem separados de propósito): confere que a implementação faz o que
  o método diz, não é evidência de robustez. Abaixo de 5 m (o maior salto dentro de um
  grupo) os grupos se dividem.
- Encadeamento (T5, população `sequencia`: barreiras distintas a 15 m em linha): com
  `eps` = 8 m, 20 de 20 separadas; com 12 m, 9 barreiras (6 fusões); com 20 m, 5
  (cada sequência de 45 m vira uma barreira). Janela útil medida: cerca de [5; 10,3) m.
  Com dispersão de 6 m, `eps` = 8 m já separa só 11 de 20.

**Opções.**
- (a) Coletar com os provisórios, medir o erro de GPS em campo e recalibrar pelo
  procedimento de `coleta-em-campo.md` §7.
- (b) Baixar `min_confirmacoes` para 2 já na coleta (menos barreiras reais pendentes,
  menos proteção contra relatos falsos coincidentes).
- (c) Subir para 4 (mais proteção suposta, mais barreiras reais pendentes).

**Recomendação da equipe:** (a). Pedimos à orientadora o critério para a decisão final
(por exemplo: aceitar mais pendentes ou mais risco de falsa confirmação?).

**O que muda.** Código: nada (só `.env`). Texto: o valor final e a justificativa entram
na metodologia; a figura do funil mostra os parâmetros da execução que a produziu
(tabela `execucoes_pipeline`). Detalhe em
[`resultados-simulacao.md`](../texto-tcc/resultados-simulacao.md).

## #2 Taxonomia de tipos de barreira

**Contexto.** Hoje valem os 4 tipos do pôster: calçada irregular, ausência de rampa,
degrau e obstáculo (`db/seeds/001_tipos_barreira.sql`). A taxonomia é tabela, não
`ENUM`: mudar não exige migration, e o formulário lê `GET /tipos-barreira`.

**Opções.** (a) Manter os 4; (b) acrescentar ou subdividir tipos, com a lista definida
pela orientadora; (c) alinhar a uma taxonomia publicada, por exemplo a do Project Sidewalk
(SAHA et al., 2019) **[CONFERIR os rótulos no artigo]**.

**Recomendação da equipe:** (a), salvo pedido da orientadora. Menos tipos também
concentram os relatos: o DBSCAN agrupa cada tipo separadamente, então, se dois
voluntários escolhem tipos diferentes para a mesma barreira, os relatos não se somam.

**O que muda.** Seed 001 (upsert; tipo aposentado vira `ativo = false`, sem apagar
histórico). O frontend e o gerador sintético leem os tipos ativos. **Tem de estar fechada
antes da coleta:** os seeds ficam congelados enquanto ela estiver aberta
(`coleta-em-campo.md` §5).

## #3 Polígono da área de estudo

**Contexto.** Provisório: círculo de 500 m em torno do centroide do campus Higienópolis no
OpenStreetMap (−23.54719, −46.65246), cerca de 0,78 km² (`db/seeds/002_area_estudo.sql`).
É contra ele que o geofence (estágio 2) descarta `fora_da_area`.

**Opções.** (a) Manter o círculo; (b) polígono pelas ruas/quarteirões que a orientadora
definir; (c) outro raio.

**Recomendação da equipe:** decidir o recorte com a orientadora; a equipe desenha o
polígono no OSM e traz para validação.

**O que muda.** Seed 002 (upsert). O gerador sintético assume o círculo de 500 m (grupos a
até 400 m do centro, "fora da área" entre 700 e 1500 m): com um polígono muito diferente,
rever essas distâncias e regerar a simulação e a figura. Relatos já julgados não são
reavaliados por um polígono novo. **Fechar antes da coleta.**

## #6 Atributos quantitativos (altura do degrau, inclinação da rampa)

**Contexto.** A Etapa 1 do artigo promete "atributos quantificáveis (altura do degrau,
ângulo da rampa)". O sistema grava só `tipo` e `severidade` (1–3), além da descrição livre.

**Opções.** (a) Tirar do escopo e corrigir a Etapa 1; (b) coluna numérica opcional, com o
instrumento de medição definido pela equipe.

**Recomendação da equipe:** (a), como trabalho futuro. Medir exige instrumento e
protocolo que a coleta não prevê.

**O que muda.** (a) Só texto. (b) Migration nova (004), campo opcional no formulário e no
contrato da API, testes; o pipeline não muda.

---

## Informes (sem decisão)

- **#5 decidido em 29/09/2026:** código = rlbuff7; infra = Victor (VSWH); dados reais =
  Maurício.
- **Texto do TCC:** rascunhos em [`docs/texto-tcc/`](../texto-tcc/) (arquitetura,
  validação, resultados da simulação, ameaças à validade, referências conferidas, exceto
  as marcadas [CONFERIR], e a revisão do artigo/pôster do TCC I). Pedimos leitura crítica.
- **Correções no material do TCC I** ([`revisao-artigo-tcc1.md`](../texto-tcc/revisao-artigo-tcc1.md)):
  IBGE 14,4 × 18,6 milhões (pesquisas diferentes, não comparáveis), OMS 2011 × 2022,
  referencial fora de escopo, cronograma.
- Conferir com a equipe e a orientadora a lista de autores do TCC II.
- **Perguntas rápidas:**
  - O texto de consentimento dos voluntários (`coleta-em-campo.md` §3) está bom? A coleta
    precisa de algum trâmite de ética na universidade?
  - Qual é a data-limite para a coleta em campo, dado o calendário real do TCC II?
  - Hospedagem com HTTPS para a coleta (T6) é decisão da equipe; só informamos.
