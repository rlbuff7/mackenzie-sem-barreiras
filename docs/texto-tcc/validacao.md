# Camada de validação — rascunho de capítulo

> **RASCUNHO para a equipe revisar e adaptar.** Texto-base para o capítulo que descreve
> a contribuição central do trabalho: a validação dos relatos voluntários. Os fatos sobre
> o sistema vêm das docstrings de `backend/app/validacao/`, das migrations e do
> `CLAUDE.md` §5–§6; os identificadores entre parênteses (D6, G6, T4…) estão em
> [`decisoes-de-implementacao.md`](../decisoes-de-implementacao.md) e
> [`decisoes-pendentes.md`](../decisoes-pendentes.md). Referências em
> [`referencias.md`](referencias.md). Os resultados numéricos (todos de **SIMULAÇÃO**)
> ficam em [`resultados-simulacao.md`](resultados-simulacao.md).

## 1 Por que validar

Dados geográficos voluntários têm qualidade variável: são produzidos por contribuintes
heterogêneos, com equipamentos e níveis de precisão diferentes e sem um responsável que
filtre o que entra (HAKLAY, 2010; SENARATNE et al., 2017). No mapeamento de
acessibilidade, um relato isolado pode ser um engano de posição, de tipo ou de
julgamento, e um mesmo voluntário pode repetir o relato várias vezes.

Goodchild e Li (2012) descrevem três abordagens para garantir a qualidade de VGI: a de
*crowd-sourcing*, em que a concordância de um grupo corrige os erros de um indivíduo; a
social, apoiada numa hierarquia de colaboradores de confiança que atuam como moderadores;
e a geográfica, que confronta a contribuição com regras sobre o que pode ocorrer num dado
lugar. O método deste trabalho é uma operacionalização da primeira: uma barreira só é
considerada confirmada quando relatos de **pessoas diferentes** coincidem no mesmo lugar
e no mesmo tipo. Os estágios 1 e 2 não avaliam conhecimento geográfico; são filtros de
forma e de escopo que impedem que dados malformados ou fora da área cheguem ao
agrupamento. A concordância entre contribuintes também aparece na literatura de
mapeamento de acessibilidade: no Project Sidewalk, ferramenta web em que voluntários e
trabalhadores pagos rotulam problemas de calçadas em imagens do Google Street View, os
autores investigam o efeito do voto da maioria sobre a acurácia dos rótulos (SAHA et al.,
2019).

## 2 O funil de quatro estágios

| Estágio | Quando roda | O que verifica | Destino do reprovado | Código |
|---|---|---|---|---|
| 1. Schema | na entrada, relato a relato | forma do relato: faixas, tipo ativo, severidade, campos | `alertas_rejeitados` (HTTP 422) | `schemas/`, `validacao/entrada.py` |
| 2. Geofence | na entrada, relato a relato | ponto dentro da área de estudo | `alertas`, `status = 'descartado'`, `motivo_descarte = 'fora_da_area'` (HTTP 201) | `validacao/geofence.py` |
| 3. Agrupamento | em lote | vizinhos do mesmo tipo a até `eps` metros (DBSCAN) | `status = 'ruido_isolado'`, reavaliado a cada execução | `validacao/clustering.py` |
| 4. Promoção | em lote | número de sessões distintas no cluster | barreira `pendente` (visível, aguardando confirmação) | `validacao/pipeline.py` |

Os estágios 1 e 2 dependem só do relato e rodam na chegada. Os estágios 3 e 4 dependem do
conjunto: um relato só se confirma na presença de outros.

## 3 Estágio 1: schema

O corpo de `POST /alertas` é validado por um modelo Pydantic: latitude em [−90, 90],
longitude em [−180, 180], tipo informado pelo código e existente e ativo na taxonomia
(D3), severidade de 1 a 3 ou ausente, descrição de até 500 caracteres, `sessao_id` no
formato UUID e nenhum campo além desses. Corpos que nem são JSON válido, ou que contêm
caracteres que o banco não grava, também são reprovados aqui. Em todos os casos, o corpo
recebido e os erros são gravados em `alertas_rejeitados`, e a resposta 422 traz as
mensagens em português. Nenhum corpo de requisição produz erro interno (HTTP 500) neste
estágio.

A tabela à parte existe porque um relato reprovado não cabe em `alertas`: uma latitude
fora da faixa ou um tipo inexistente violariam as restrições `geom NOT NULL` e a chave
estrangeira do tipo. Guardá-lo mesmo assim permite que o funil conte o estágio 1 (T1).

## 4 Estágio 2: geofence

O ponto é testado com `ST_Within` contra o polígono da tabela `area_estudo`. Pela
semântica de `ST_Within`, só o interior conta: um ponto exatamente sobre a borda é
considerado fora. Se não houver área cadastrada, a função responde "fora", por segurança:
é preferível descartar a aceitar sem geofence nenhum.

O relato fora da área não é um erro do voluntário: ele é aceito (HTTP 201), gravado com
`status = 'descartado'` e `motivo_descarte = 'fora_da_area'` e contado no funil (D4).
`descartado` é um estado final; nenhum estágio posterior o reconsidera.

A área atual é **provisória** (pendência #3): um círculo de 500 m em torno do centroide do
campus Higienópolis no OpenStreetMap, calculado em `geography` para que o raio seja de
fato em metros.

## 5 O problema da unidade (SRID)

Os pontos são armazenados em SRID 4326 (WGS 84), o sistema usado pelo GPS e pelo
navegador, cuja unidade é o **grau**. Funções de distância do PostGIS sobre `geometry`
interpretam os parâmetros na unidade do SRID: em particular, o `eps` de
`ST_ClusterDBSCAN` é medido nas mesmas unidades das geometrias (POSTGIS PROJECT,
[2026a]). Com `eps = 8` em 4326, o raio seria de 8 graus, e o agrupamento juntaria a
cidade inteira sem produzir erro algum.

A regra adotada (G6) é armazenar em 4326 e calcular em metros reprojetando para o SRID
31983 (SIRGAS 2000 / UTM zona 23S, projeção transversa de Mercator com meridiano central
em −45° e unidade em metro, que cobre São Paulo) (EPSG.IO, [2026]), com
`ST_Transform(geom, 31983)`. O cast para `geography` também mede em metros, mas
`ST_ClusterDBSCAN` não aceita `geography`, então no agrupamento a reprojeção é o único
caminho. O centroide de cada barreira também é calculado em 31983 e só então convertido
de volta para 4326. No código, toda variável de distância termina em `_metros`, e os dois
SRIDs são parâmetros do `.env`, não literais.

## 6 Estágio 3: agrupamento espacial (DBSCAN)

O agrupamento usa o DBSCAN (ESTER et al., 1996), um algoritmo baseado em densidade que
encontra clusters de forma arbitrária e separa os pontos que não pertencem a nenhum
deles como ruído. Com dois parâmetros, o raio `eps` e o mínimo de pontos `minpoints`:

- **ponto-núcleo** é o alerta que tem pelo menos `minpoints` alertas, contando ele mesmo,
  a até `eps` de distância (é assim que o PostGIS define a contagem);
- um **cluster** é formado por núcleos ligados entre si por vizinhança e pelos alertas ao
  alcance deles (pontos de borda);
- o alerta que não é núcleo nem está ao alcance de um núcleo é **ruído**.

O DBSCAN foi escolhido porque não exige fixar o número de barreiras de antemão e porque o
ruído é um resultado explícito: o relato sem ninguém que o corrobore.

A implementação usa `ST_ClusterDBSCAN`, executada dentro do banco como função de janela:

```sql
ST_ClusterDBSCAN(ST_Transform(geom, :srid_calculo), eps := :eps_metros,
                 minpoints := :min_pontos)
    OVER (PARTITION BY tipo_id ORDER BY id)
```

Três escolhas merecem registro:

1. **Partição por tipo.** Um degrau e um obstáculo a um metro um do outro são duas
   barreiras, não duas confirmações da mesma. Cada tipo é agrupado separadamente.
2. **Ordem explícita.** O DBSCAN percorre os pontos em ordem, e dois detalhes dependem
   dela: a numeração dos clusters e o destino de um ponto de borda ao alcance de núcleos
   de dois clusters. A documentação do PostGIS diz que esse ponto é atribuído
   arbitrariamente e recomenda um `ORDER BY` na janela para torná-lo determinístico
   (POSTGIS PROJECT, [2026a]). Com `ORDER BY id`, o resultado é reproduzível; isso foi
   verificado no PostGIS 3.4.3 do projeto e está coberto por teste. Com `minpoints = 2`,
   o valor provisório, não há pontos de borda (todo alerta com um vizinho já é núcleo), e
   a ordem só afeta a numeração.
3. **Só alertas não descartados.** Entram os alertas `bruto`, `ruido_isolado` e
   `agrupado` da origem pedida; `descartado` nunca volta ao agrupamento, e as origens real
   e simulação nunca se misturam.

Os parâmetros atuais, `eps = 8 m` e `minpoints = 2`, são **provisórios** (pendência #4).

**Efeito de encadeamento (T5).** O DBSCAN liga vizinhos de vizinhos. Relatos a cada
7 m ao longo de uma calçada, com `eps = 8 m`, formam um único cluster de comprimento
arbitrário, embora os extremos estejam longe um do outro; uma calçada inteira irregular
pode virar uma só barreira, com o centroide no meio. O efeito é aceito como propriedade
do algoritmo, foi medido na simulação e é discutido em
[`resultados-simulacao.md`](resultados-simulacao.md) e
[`ameacas-validade.md`](ameacas-validade.md).

**O estágio 3 conta alertas, não sessões (pendência #7).** O `minpoints` conta alertas:
dois relatos da mesma sessão no mesmo lugar já formam um cluster. A defesa contra a
pessoa sozinha fica no estágio 4.

## 7 Estágio 4: promoção por sessões distintas

Cada cluster, identificado pelo par (tipo, número do cluster), vira uma barreira com:

- geometria: o centroide dos alertas do cluster (calculado em 31983);
- `confirmacoes`: o número de **sessões distintas** entre os alertas
  (`COUNT(DISTINCT sessao_hash)`), e não o número de alertas;
- `status`: `confirmada` se `confirmacoes ≥ MIN_CONFIRMACOES`, senão `pendente`.

O valor provisório é `MIN_CONFIRMACOES = 3` (pendência #4). Contar sessões e não alertas
é a defesa contra o ataque Sybil mais simples: cinco relatos da mesma pessoa no mesmo
lugar são uma pessoa só, e uma pessoa sozinha não confirma uma barreira. A sessão é um
UUID aleatório gerado no navegador e guardado no `localStorage`; o servidor grava só o
seu `sha256`, nunca o UUID cru nem o endereço IP (D1). A limitação é conhecida: quem limpa
o navegador ou usa outro aparelho vira uma sessão nova (ver
[`ameacas-validade.md`](ameacas-validade.md)).

`pendente` não é descarte: a barreira existe, aparece no mapa com o seu status e aguarda
confirmação de outras pessoas. `sessao_hash` é `NOT NULL` no esquema justamente porque
`COUNT(DISTINCT …)` ignora valores nulos em silêncio.

## 8 Execução em lote: reconstrução completa

Os estágios 3 e 4 rodam em `executar_pipeline`, chamada por `POST /validacao/executar`
(protegida por token de administrador, D7) e pelos scripts de simulação, sempre para
**uma origem por vez** e numa única transação (D6):

1. valida a origem e os parâmetros (`eps_metros > 0`, `min_pontos ≥ 1`,
   `min_confirmacoes ≥ 1`) antes de qualquer SQL, para que um valor inválido nunca apague
   barreiras;
2. obtém um *advisory lock* de transação, que faz uma segunda execução simultânea esperar
   a primeira;
3. volta os alertas `agrupado` e `ruido_isolado` da origem a `bruto` e apaga as barreiras
   da origem;
4. roda o DBSCAN sobre todos os alertas não descartados;
5. cria uma barreira por cluster e marca os seus alertas como `agrupado`; o ruído vira
   `ruido_isolado`;
6. grava, na mesma transação, os parâmetros usados e o instante da execução em
   `execucoes_pipeline`.

Recalcular tudo, em vez de atualizar só o que mudou, decorre do próprio DBSCAN: o rótulo
de um alerta depende de todos os outros, e um alerta novo pode transformar ruído em
cluster, juntar-se a uma barreira existente ou unir dois clusters. A reconstrução dá
sempre o mesmo resultado que uma primeira execução sobre os mesmos dados. Com isso, o
ruído é reavaliado a cada execução (T4), um alerta novo perto de uma barreira entra no
cluster dela, e duas execuções seguidas produzem o mesmo resumo. O custo aceito é que os
identificadores das barreiras mudam a cada execução. Como o pipeline nunca apaga
alertas, mudar os parâmetros é só reexecutar o pipeline sobre os mesmos dados.

## 9 Estatísticas do funil

`GET /validacao/estatisticas` devolve as contagens de uma origem com as **unidades
separadas**: o bloco de alertas conta alertas (recebidos, reprovados no schema,
descartados por motivo, aguardando o pipeline, ruído, agrupados) e o bloco de barreiras
conta barreiras (total, pendentes, confirmadas). A separação corrige o funil do pôster do
TCC I, em que a unidade mudava de alertas para barreiras no estágio de agrupamento sem
aviso. Todo alerta recebido está em exatamente um estágio, então `recebidos` é a soma dos
demais. As contagens saem de uma única consulta, para que uma execução do pipeline no
meio não produza um funil misturado, e trazem os parâmetros da **última execução**, lidos
de `execucoes_pipeline`, e não a configuração atual (R14, R15). Cada resposta traz um
rótulo de origem, "SIMULAÇÃO — dados sintéticos" ou "Dados reais de campo" (G10).

## 10 Como a implementação foi verificada

Cada função de `validacao/` tem teste automatizado, executado contra um PostGIS real num
banco de teste separado, sem simulação do banco (G8). Entre eles, um teste fixa o
encadeamento (três alertas a 7 m formam um cluster com `eps = 8 m`) e outro fixa o destino
determinístico de um ponto de borda disputado. A avaliação com dados sintéticos, que
confere cada estágio contra um destino conhecido de antemão, está em
[`resultados-simulacao.md`](resultados-simulacao.md).
