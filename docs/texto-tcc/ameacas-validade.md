# Ameaças à validade e limitações — rascunho de capítulo

> **RASCUNHO para a equipe revisar e adaptar.** Texto-base para a seção de limitações da
> monografia. Cada ameaça traz o efeito, o que o sistema já faz para reduzi-la e o que
> fica em aberto. Os fatos sobre o sistema vêm do repositório
> ([`decisoes-pendentes.md`](../decisoes-pendentes.md),
> [`coleta-em-campo.md`](../coleta-em-campo.md), docstrings de `backend/app/validacao/`);
> os números são todos de **SIMULAÇÃO** ([`resultados-simulacao.md`](resultados-simulacao.md)).
> Referências em [`referencias.md`](referencias.md).

## 1 Sessão não é pessoa (ataque Sybil)

A promoção a barreira `confirmada` exige `MIN_CONFIRMACOES` **sessões distintas**, e a
sessão é um UUID aleatório guardado no `localStorage` do navegador, gravado no servidor só
como `sha256` nos relatos aceitos (os reprovados no estágio 1 guardam o corpo recebido
inteiro, UUID cru incluso, em `alertas_rejeitados.payload`: D1, R27). A regra barra o
caso mais simples, uma pessoa relatando várias vezes do mesmo navegador, mas não
identifica pessoas: quem limpa os dados do navegador, usa uma janela anônima, outro
navegador ou outro aparelho ganha uma sessão nova. Uma pessoa com três navegadores
confirma sozinha uma barreira com o valor atual (3).

- **Por que não há defesa mais forte:** o sistema não pede cadastro e não grava IP, por
  decisão de privacidade (LGPD). Conta de usuário ou identificação do aparelho
  reduziriam o risco em troca de dados pessoais; nenhuma delas está no escopo. O nginx
  do frontend limita os envios por IP (30 por minuto, com rajada de 20), mas como
  proteção contra abuso por script, não contra o ataque Sybil: o IP fica só em memória,
  e atrás do túnel da coleta todos os voluntários chegam ao nginx com o mesmo endereço
  (o do container do túnel). O limite vira **coletivo**, um só balde para a equipe
  inteira, e não distingue pessoas.
- **Mitigação atual:** o protocolo de coleta orienta "uma barreira, um relato por sessão"
  e cada pessoa na própria sessão (`coleta-em-campo.md` §2); a coleta é organizada pela
  equipe, com roteiro e checklist (§2 e §5).
- **No texto:** declarar que `confirmacoes` conta sessões (aparelhos/navegadores), não
  pessoas, e que o método supõe voluntários de boa-fé.

## 2 O estágio 3 conta alertas, não sessões

O `minpoints` do DBSCAN conta **alertas** (pendência #7). Dois relatos da mesma sessão no
mesmo lugar já formam um cluster: o que seria ruído vira uma barreira `pendente`, visível
no mapa. Relatos repetidos de uma sessão também podem ligar, por encadeamento, dois
clusters reais. A regra das sessões distintas protege só a promoção: na SIMULAÇÃO, a
população `sessao_repetida` vira `pendente`, nunca `confirmada`.

- **Efeito:** o mapa pode mostrar barreiras pendentes sustentadas por uma única pessoa, e
  a contagem de barreiras pendentes fica inflada por repetição.
- **Mitigação atual:** o protocolo de coleta (um relato por barreira e sessão). Os alertas
  brutos ficam guardados, então uma deduplicação por sessão decidida depois pode ser
  aplicada reexecutando o pipeline sobre os mesmos dados.
- **Em aberto:** decisão metodológica com a orientadora (manter e declarar, ou deduplicar
  por sessão antes do DBSCAN).

## 3 Parâmetros provisórios

`eps` = 8 m, `minpoints` = 2 e `MIN_CONFIRMACOES` = 3 foram escolhidos para o protótipo,
não calibrados (pendência #4). A SIMULAÇÃO mostra que o acerto depende deles: abaixo de
cerca de 5 m os grupos verdadeiros se dividem; acima de cerca de 10,3 m barreiras vizinhas
a 15 m se fundem; e subir `min_confirmacoes` de 3 para 4 deixa 11 dos 20 aglomerados
verdadeiros pendentes, em vez de 9. Essa janela foi medida sob uma dispersão suposta de até
3 m; com 6 m ela já não comporta `eps` = 8 m.

- **Efeito:** qualquer número do funil real vale para os parâmetros com que foi produzido,
  e só para eles.
- **Mitigação atual:** os parâmetros ficam no `.env`, cada execução grava os valores que
  usou (tabela `execucoes_pipeline`), e a figura do funil os mostra. O procedimento de
  recalibração com o erro de GPS medido em campo está em `coleta-em-campo.md` §7.
- **No texto:** apresentar sempre o funil com os parâmetros, e a calibração como trabalho
  dependente da coleta.

## 4 Polígono provisório da área de estudo

A área é um círculo de 500 m em torno do centroide do campus no OpenStreetMap
(pendência #3), e não um recorte por ruas ou quarteirões. O geofence usa `ST_Within`, que
considera fora um ponto exatamente sobre a borda.

- **Efeito:** o número de descartes `fora_da_area` depende de um recorte arbitrário;
  calçadas do entorno imediato podem ficar dentro ou fora conforme a geometria do círculo.
  Um polígono novo só vale dali em diante: relatos já descartados não são reavaliados.
- **Mitigação atual:** os seeds ficam congelados durante a coleta (`coleta-em-campo.md`
  §5), para que todo o funil real seja julgado por um único polígono.

## 5 Simulação não é realidade

Os resultados quantitativos disponíveis são de dados sintéticos.

- O cenário de controle é bem separado **de propósito**: grupos a pelo menos 4 × `eps`
  uns dos outros. Os 100% de acerto conferem a implementação, e as "0 fusões" acontecem
  por construção; nenhum dos dois é evidência de robustez.
- As proporções do funil simulado (inválidos, fora da área, ruído, grupos) foram fixadas
  pelo gerador; não são taxas observadas.
- A dispersão sintética é limitada a um raio máximo em torno de cada grupo; o erro real de
  GPS em calçadas entre prédios não foi medido.
- A simulação não tem relatos falsos corroborados por sessões distintas, nem voluntários
  que escolhem o tipo errado, nem barreiras que deixam de existir. Por isso ela mostra o
  custo de `min_confirmacoes`, mas não o benefício.
- **No texto:** rotular "SIMULAÇÃO" em toda tabela e figura sintética e nunca apresentar
  esses números como resultado de coleta.

## 6 Viés dos voluntários e da cobertura

A qualidade da informação geográfica voluntária varia com quem contribui e onde
(HAKLAY, 2010; SENARATNE et al., 2017). Aqui, os voluntários serão do entorno do campus,
em rotas e horários que eles próprios escolhem.

- **Ausência no mapa não é ausência de barreira:** trechos pouco percorridos terão menos
  relatos, e uma barreira real com um só relato fica como ruído.
- **Tipos e severidade:** a escolha do tipo e a severidade (1 a 3) são julgamentos de quem
  relata; como o agrupamento é feito por tipo, relatos da mesma barreira com tipos
  diferentes não se somam.
- **Perfil de quem relata:** voluntários sem deficiência podem não perceber barreiras que
  afetam outros perfis; a literatura de navegação acessível registra preferências
  diferentes entre deficiências (GUPTA et al., 2020).
- **No texto:** descrever quem participou da coleta, quando e por onde, e tratar o
  resultado como amostra do entorno, não como inventário completo.

## 7 O que é "uma barreira" (encadeamento)

O DBSCAN liga vizinhos de vizinhos. Relatos a cada poucos metros ao longo de uma calçada
formam um único cluster, e uma calçada inteira irregular pode virar uma só barreira, com o
centroide no meio (T5). Na SIMULAÇÃO, barreiras distintas a 15 m se fundem a partir de
`eps` ≈ 10,3 m.

- **Efeito:** o número de barreiras não é o número de obstáculos físicos, e o centroide de
  um cluster longo pode cair num ponto sem barreira.
- **Em aberto:** como o texto declara a limitação e se vale alguma mitigação (por exemplo,
  limitar a extensão de um cluster), fora do escopo atual.

## 8 Tempo

O pipeline reagrupa todos os alertas não descartados da origem, sem janela de tempo: um
relato antigo conta tanto quanto um recente. Uma barreira consertada continua no mapa
enquanto os seus relatos existirem. Para uma coleta curta, o efeito é pequeno; para uso
contínuo, seria preciso expirar relatos ou registrar a remoção de barreiras.

## 9 Posição do relato

O ponto pode vir da geolocalização do aparelho, de um toque no mapa ou do centro do mapa.
Só a primeira mede a posição de fato; nas outras, o erro depende de quem relata. O
protocolo pede relatar no local da barreira, com a geolocalização ligada, e a
geolocalização do navegador exige HTTPS (`coleta-em-campo.md` §2 e §4).

## 10 Privacidade como limitação do dado publicado

`sessao_hash`, `criado_em` e a posição formam a trajetória de um aparelho durante a coleta.
É um dado pseudônimo, não anônimo: por isso o banco não deve ser publicado relato a relato,
e as estatísticas e a figura usam só contagens (`coleta-em-campo.md` §3). Isso limita a
reprodutibilidade externa: terceiros recebem os agregados, não os relatos.
