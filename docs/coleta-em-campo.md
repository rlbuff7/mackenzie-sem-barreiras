# Protocolo de coleta em campo (M6)

Preparação para a coleta REAL de dados (`origem='real'`), no entorno do campus
Higienópolis do Mackenzie. Este documento não é código: é o roteiro operacional do dia
de coleta e o que precisa estar decidido antes dele. Contexto do projeto: [`CLAUDE.md`](../CLAUDE.md);
pendências formais: [`decisoes-pendentes.md`](decisoes-pendentes.md).

Convenção usada abaixo: cada item traz uma marca —

- **[ORIENTADORA]** — depende de decisão da orientadora (`decisoes-pendentes.md` #1–#7).
  Enquanto pendente, a coleta usa o valor provisório já no `.env`/nos seeds.
- **[EQUIPE]** — depende só de decisão interna dos integrantes (ex.: hospedagem, HTTPS).
  Nada aqui exige a orientadora, mas também nada está decidido ainda.

---

## 1. Objetivo e área

Coletar relatos reais de barreiras de acessibilidade física no entorno do campus, pelo
mesmo formulário e mesmo pipeline já usados na simulação (M2–M5), agora com
`origem='real'`. A área de coleta é a **[ORIENTADORA] #3 — polígono provisório**: um
círculo de 500 m em torno do centroide do campus (`db/seeds/002_area_estudo.sql`),
~0,78 km². Um relato fora desse círculo é aceito pela API mas **descartado**
(`motivo_descarte='fora_da_area'`) — não é erro do voluntário, é o geofence funcionando;
vale avisar o grupo para não estranhar se isso acontecer.

## 2. Roteiro para os voluntários

1. **Abrir o mapa** na URL combinada com a equipe (ver §4 — depende de onde o frontend
   estiver publicado nesse momento).
2. **Ir até o local da barreira** e reportar de lá, com a geolocalização do celular
   ligada. Não reportar "de memória" depois, em casa: o ponto capturado pelo GPS é o
   dado espacial que sustenta todo o pipeline (geofence e clustering).
3. **Escolher o tipo mais específico**, entre os da taxonomia ativa
   (`GET /tipos-barreira`; hoje, **[ORIENTADORA] #2 — taxonomia provisória**):

   | Tipo | O que é |
   |---|---|
   | Calçada irregular | Piso quebrado, desnivelado, com buracos ou raízes expostas. |
   | Ausência de rampa | Travessia ou desnível sem rampa de acesso ou rebaixamento de guia. |
   | Degrau | Degrau isolado ou escada sem alternativa acessível. |
   | Obstáculo | Objeto que bloqueia a faixa livre: poste, lixeira, mesa, veículo, entulho. |

4. **Severidade é opcional** (1 leve, 2 moderada, 3 grave) — preencher quando o
   voluntário tiver segurança para julgar; não preencher está longe de ser um erro.
5. **Descrição é opcional**, até 500 caracteres. Frase curta e objetiva ("degrau de
   ~20 cm sem rampa ao lado") ajuda mais do que uma frase longa.
6. **Não fotografar e não escrever nenhum dado pessoal na descrição** (nome, contato,
   placa de veículo, rosto identificável) — ver §3.

### Boas práticas (evitar poluir o funil)

- **Uma barreira, um relato por sessão.** Se o grupo já reportou aquele degrau
  específico nesta sessão, não reportar de novo — isso não vira uma "segunda
  confirmação" (o pipeline conta *sessões distintas*: D1 / estágio 4), só infla `recebidos` sem
  ajudar a promoção.
- **Sessões diferentes SIM ajudam.** O valor de uma barreira ser vista por pessoas
  diferentes é exatamente o que a promoção mede (`MIN_CONFIRMACOES` sessões distintas,
  hoje **[ORIENTADORA] #4** = 3). Se o grupo tem várias pessoas, é melhor cada uma abrir
  o mapa na própria sessão do que dividir uma sessão só entre todos.
- **Relatar no exato ponto da barreira**, não num ponto aproximado a alguns metros —
  o `DBSCAN_EPS_METROS` (**[ORIENTADORA] #4**, hoje 8 m) é um valor de PROTÓTIPO, não
  calibrado: a simulação só mostra em que faixa de eps o pipeline funciona sob erros de
  posição supostos (`decisoes-pendentes.md` #4). O erro de GPS real é justamente o que a
  calibração de campo (§7) vai medir.

## 3. Ética e LGPD

O que o sistema grava, o que ele não grava e o que passa por terceiros. É isto que o
voluntário precisa saber para consentir (texto sugerido no fim da seção).

**O que fica no banco, por relato:** o ponto (latitude e longitude, do GPS ou do toque
no mapa), o tipo, a severidade e a descrição (as duas opcionais), a hora do envio
(`criado_em`) e o `sessao_hash`. Isso vale para os relatos **aceitos** (tabela
`alertas`). Os relatos **reprovados no estágio 1** (formato inválido, campo extra, tipo
inexistente) têm outro destino, a tabela `alertas_rejeitados`, que guarda o **corpo
recebido inteiro** em `payload`: o `sessao_id` em UUID cru (não o hash), a descrição e
qualquer campo extra que o cliente tenha mandado, mais a lista de erros
(`db/migrations/`, `app/validacao/entrada.py`, `docs/api.md`). Para o voluntário, isso
não muda nada que o identifique: o UUID é aleatório e só existe no aparelho dele, sem
ligação com nome, contato ou IP. Mas o cuidado com o banco vale em dobro: o
`alertas_rejeitados` também não deve ser publicado cru.

- **Nenhum dado de identificação direta.** Não há campo de nome, e-mail, telefone ou
  documento no formulário. A descrição é texto livre: por isso o roteiro pede para não
  escrever dado pessoal nela (§2).
- **Sem fotos.** O contrato da API não tem campo de imagem; não é para inventar um
  campo de imagem "por fora" no dia da coleta.
- **O banco não guarda IP.** Nenhuma tabela tem coluna de IP e nenhum código grava o
  endereço de quem reporta (`app/validacao/entrada.py`).
- **Os logs deste projeto não guardam IP.** O nginx do frontend usa um formato de log
  próprio, sem o endereço do cliente e sem `X-Forwarded-For`: só hora, método, caminho
  sem a query string, status e tempos (`frontend/nginx.conf`). O log de erro do nginx
  fica no nível `crit`, porque as mensagens de erro dele trazem o IP. O nginx também não
  repassa o IP à API, então o log da API (uvicorn) registra só o endereço interno do
  nginx na rede do compose. Isso vale para os containers deste repositório: o túnel ou a
  hospedagem escolhidos (§4) têm os próprios logs, fora do nosso controle. Conferir a
  política do serviço escolhido e citá-la no texto de consentimento.
- **Com o Quick Tunnel (§4), a Cloudflare vê o tráfego.** O túnel `trycloudflare.com`
  termina o TLS na Cloudflare: os relatos (ponto, tipo, severidade, descrição e o
  `sessao_id` no corpo) passam em claro por um terceiro antes de chegar ao nosso nginx,
  e o IP do voluntário é visto por ela (os nossos logs continuam sem IP). É o mesmo tipo
  de exposição dos tiles do OpenStreetMap, mas aqui inclui o conteúdo do relato.
  Para o voluntário: não escrever dado pessoal na descrição, e o texto de consentimento
  deve citar a Cloudflare como intermediária. Uma hospedagem própria com HTTPS (§4)
  também tem esse intermediário, só que escolhido por nós.
- **A sessão é um pseudônimo do aparelho, não anonimato.** O navegador gera um UUID
  aleatório e o guarda no `localStorage` (D1); nos relatos aceitos o servidor grava só
  `sha256(uuid)`, nunca o UUID cru (a exceção são os reprovados no estágio 1, que
  guardam o corpo recebido, UUID cru incluso, em `alertas_rejeitados.payload`). O
  hash não diz quem é a pessoa, mas é o MESMO em todos os relatos daquele navegador: `sessao_hash` + `criado_em` + `geom` formam a **trajetória** do
  aparelho durante a coleta (onde esteve, em que ordem, a que horas). É dado
  pseudônimo: quem souber por outro meio por onde alguém andou pode reconhecer a
  trajetória dessa pessoa. Por isso o banco, ou qualquer exportação com `sessao_hash`
  e `criado_em`, não deve ser publicado cru; as estatísticas e a figura do funil só
  usam contagens. Quem limpa o navegador (ou usa outro aparelho) vira uma "sessão nova"
  — limitação conhecida e aceita (T3), não um bug.
- **Os tiles do mapa vêm do OpenStreetMap, um terceiro.** Para desenhar o mapa, o
  navegador do voluntário baixa as imagens de `tile.openstreetmap.org`, que recebe o IP
  do aparelho e a região do mapa pedida. Sem isso não há mapa; a política de
  privacidade é a da OpenStreetMap Foundation
  (<https://osmfoundation.org/wiki/Privacy_Policy>). Nenhum outro terceiro: a fonte é
  servida pelo próprio frontend.
- **A geolocalização é o dado central** (mapear onde estão as barreiras). O navegador
  só a pede quando o voluntário toca em "Usar minha localização", e o ponto só sai do
  aparelho quando ele envia o relato.

**Texto sugerido para o consentimento** (revisar com a orientadora antes da coleta):

> Este mapa faz parte de um TCC da FCI/Mackenzie sobre barreiras de acessibilidade.
> Cada relato que você envia grava o ponto no mapa, o tipo da barreira, a severidade e
> a descrição (se você preencher) e a hora do envio. Não pedimos nome nem contato e não
> gravamos o endereço IP do seu aparelho. O navegador recebe um código aleatório que
> junta os seus relatos, para contarmos confirmações de pessoas diferentes; com ele dá
> para ver o caminho dos seus relatos, mas não quem você é. O mapa de fundo vem do
> OpenStreetMap, que recebe o IP do seu aparelho para enviar as imagens. Não escreva
> dados pessoais na descrição. Os dados servem ao TCC e não serão publicados relato a
> relato com esse código.

## 4. Requisito técnico: HTTPS para geolocalização [EQUIPE]

Navegadores modernos só liberam `navigator.geolocation` (usada pelo botão "Usar minha
localização" do frontend, `frontend/src/mapa.ts`) em **contexto seguro**: HTTPS, ou
`localhost` puro. Em produção com `docker compose up` simples (HTTP), o botão de
localização automática falha no celular — só resta o botão "Usar o centro do mapa" e
tocar manualmente, o que derrota o propósito de captar o ponto certo em campo.

**Ganho prático do proxy same-origin (R19):** desde que `frontend/nginx.conf` passou a
encaminhar `/api/` para o serviço `api` pela mesma origem, só o **frontend** precisa
ficar acessível por HTTPS na internet — a API não precisa mais de uma URL pública
própria nem de CORS liberado para o domínio da coleta; o navegador do voluntário só
fala com o container do frontend, que fala com a API por dentro da rede do compose. Ou
seja, expor **um único endpoint HTTPS** (o frontend), não dois.

**Consequência: toda a API fica pública junto com o mapa.** A porta da API nunca é
exposta, mas qualquer rota dela responde por `/api/` na URL da coleta, inclusive
`/api/validacao/executar` (que apaga e recria as barreiras reais, D6) e a documentação
interativa em `/api/docs`. **Defina `TOKEN_ADMIN` no `.env` ANTES de expor o
frontend**, em qualquer das opções abaixo; com ele vazio, a execução do pipeline fica
aberta a quem tiver a URL (D7). **Defina também `EXPOR_DOCS=false`**: a documentação
interativa (`/docs`, `/redoc`, `/openapi.json`) deixa de existir (404) e o esquema da
API não fica público.

**Isto ainda não está decidido — decidir com a equipe antes do dia da coleta.** Duas
famílias de opção, sem escolher nenhuma aqui:

| Opção | Como funciona | Vantagens | Desvantagens |
|---|---|---|---|
| **Túnel (ex.: `cloudflared`)** | Um túnel expõe o container `frontend` local (rodando no notebook de alguém, via `docker compose up`) numa URL HTTPS pública temporária; a porta da API fica só na rede interna do compose, mas as rotas dela respondem por `/api/` na mesma URL: `TOKEN_ADMIN` definido ANTES de abrir o túnel. | Sem precisar publicar a imagem em lugar nenhum; sobe e derruba no dia; usa a mesma stack já testada neste M5; só um túnel (um endpoint), não dois. | URL muda a cada sessão (a não ser que se configure um domínio fixo); depende da internet/notebook de quem hospeda o túnel durante toda a coleta; exige instalar a ferramenta do túnel no notebook de quem hospeda: uma exceção à regra "nada é instalado direto na máquina" do resto do projeto, restrita a esse notebook e ao dia da coleta. |
| **Hospedagem gratuita** (ex.: um provedor de PaaS/estático com HTTPS incluso) | Sobe as duas imagens (`frontend` e `api`) para um serviço externo com HTTPS de fábrica; só o `frontend` precisa de URL pública, a `api` só precisa ser alcançável pelo `frontend` na rede interna do provedor. | URL estável, reutilizável em coletas futuras; não depende do notebook de ninguém durante a coleta; sem CORS para configurar (mesma origem). | Ainda expõe o banco (ou um banco gerenciado), e `TOKEN_ADMIN` precisa estar definido ANTES de publicar (pelo proxy, `/api/validacao/executar` e `/api/docs` ficam públicos); dependendo do provedor, custo ou limite de uso; mais um passo de configuração para manter. |

Qualquer que seja a escolha, ela não muda o contrato da API nem o pipeline — só onde
`frontend`/`api` ficam acessíveis. Registrar a decisão final em
`decisoes-pendentes.md` quando ela acontecer.

## 5. Checklist do dia

Antes de ir a campo:

- [ ] **[EQUIPE]** Decidir e testar a opção de HTTPS (§4) — validar o botão de
      geolocalização num celular de verdade, não só no navegador do notebook.
- [ ] **Definir `TOKEN_ADMIN` no `.env` ANTES de expor o frontend** (túnel ou
      hospedagem, §4): pelo proxy, `/api/validacao/executar` e `/api/docs` ficam
      públicos junto com o mapa. Um valor longo e aleatório, por exemplo
      `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`, e depois
      `docker compose up -d` para a API recarregar o `.env`.
- [ ] **Definir `EXPOR_DOCS=false` no `.env` ANTES de expor o frontend**, junto com o
      `TOKEN_ADMIN` (mesmo `docker compose up -d`). Conferir: `/api/docs` responde 404.
- [ ] Confirmar que a stack sobe do zero: `docker compose up -d --build --wait`
      (`docker compose ps` — os três serviços `healthy`).
- [ ] `./db/banco.sh migrar` já aplicado (tabelas, seeds e, principalmente, o polígono
      da área de estudo atual).
- [ ] `./scripts/ponta-a-ponta.sh` verde com o `TOKEN_ADMIN` definido (prova que a
      cadeia inteira responde por HTTP antes de sair a campo e que a execução sem o
      header é recusada com 401). Com `EXPOR_DOCS=false` no ambiente, ele também
      confere que `/docs`, `/redoc` e `/openapi.json` respondem 404.
- [ ] Cada integrante com o celular carregado e a URL de coleta salva/testada.
- [ ] Combinar quem faz o quê em campo (ver **[ORIENTADORA] #5**, ainda em aberto —
      na falta de uma divisão formal, combinar informalmente para o dia).
- [ ] **Zerar os dados reais de teste.** Todo POST na pilha principal grava
      `origem='real'`: os testes manuais no mapa, o `curl` do README e até um corpo
      inválido (que vira uma linha em `alertas_rejeitados`). Se houve testes, rode
      `./db/banco.sh zerar-real --sim-apagar-dados-reais`. Sem o argumento, ele só
      mostra quanto seria apagado; com ele, apaga as linhas `origem='real'` das quatro
      tabelas numa transação e nunca toca a simulação. É SÓ para este momento: depois
      de aberta a coleta, essas linhas são os dados do TCC.
- [ ] Conferir `GET /validacao/estatisticas?origem=real` com `alertas.recebidos = 0`
      logo antes de abrir a coleta.
- [ ] **Congelar os seeds (tipos e polígono) até o fim da coleta.** `./db/banco.sh
      migrar` reaplica `db/seeds/` a cada execução. Se o polígono mudasse no meio, o
      funil real misturaria relatos julgados por dois geofences diferentes (e uma troca
      de taxonomia mudaria os tipos aceitos). Não edite `db/seeds/` nem rode `migrar`
      com seeds alterados enquanto a coleta estiver aberta.
- [ ] Registrar a versão em vigor: o commit da pilha de coleta
      (`git rev-parse --short HEAD`), anotado com a data. É o que permite ao texto citar
      exatamente que código, polígono e parâmetros produziram o funil real.

Durante a coleta:

- [ ] **Não testar na pilha de coleta.** Depois de aberta, todo envio nela é um relato
      real. Para testar algo, use `./scripts/ponta-a-ponta.sh`, que sobe uma pilha
      isolada e a apaga no fim.
- [ ] Reportar sempre no local (§2).
- [ ] Anotar (fora do sistema, num papel/app qualquer da equipe) observações que não
      cabem no formulário — por exemplo, comparar o GPS do celular com a posição real,
      para alimentar a calibração do §7.

Depois da coleta (mesmo dia ou no seguinte, com a stack ainda de pé):

- [ ] Rodar o pipeline sobre os dados reais: `POST /validacao/executar?origem=real`
      (com `X-Token-Admin` se `TOKEN_ADMIN` estiver configurado, D7).
- [ ] Conferir o funil: `GET /validacao/estatisticas?origem=real`.
- [ ] Gerar a figura (§6).

## 6. Rodando o pipeline e a figura com dados reais

Depois que os relatos de campo estiverem no banco (via `POST /alertas`, sempre
`origem='real'` — nunca inserção manual):

```bash
# 1. Roda os estágios 3 e 4 (agrupamento + promoção) sobre origem=real.
curl -X POST "http://localhost:8000/validacao/executar?origem=real" \
  -H "X-Token-Admin: <token, se TOKEN_ADMIN estiver configurado>"

# 2. Confere o funil.
curl "http://localhost:8000/validacao/estatisticas?origem=real"

# 3. Gera a figura (a partir de backend/, com o grupo opcional de matplotlib).
cd backend
uv sync --group analise
uv run python -m scripts.gerar_figura_funil --origem real
```

A figura sai em `docs/figuras/funil-real.svg`/`.png` — sem o rótulo "SIMULAÇÃO", porque
agora é dado real de verdade (`ROTULOS_POR_ORIGEM["real"] = "Dados reais de campo"`,
`app/validacao/estatisticas.py`). Nada aqui toca `origem='simulacao'`: as duas origens
nunca se misturam (G10), então a figura da simulação continua disponível para
comparação.

## 7. Calibração com dados reais

A análise de sensibilidade (`backend/scripts/analisar_sensibilidade.py`) usa só dados
sintéticos: além do CONTROLE, mede o encadeamento com sequências de barreiras vizinhas
(T5) e o efeito de `min_confirmacoes` com aglomerados de 2 a 5 sessões (ver
`decisoes-pendentes.md` #4 e T5). Nenhum desses números vem de campo. Depois da primeira
coleta real, o
procedimento para revisitar `DBSCAN_EPS_METROS`/`MIN_CONFIRMACOES`
(**[ORIENTADORA] #4**) é:

1. **Medir o erro de GPS real**, comparando a posição capturada pelo celular com a
   posição verdadeira de algumas barreiras conhecidas (anotado no checklist do §5). É
   esse número — não mais o sintético — que deve orientar o novo `eps`.
2. **Rodar a grade de novo com o eps medido incluído**, para ver onde ele cai em
   relação à janela útil já documentada (o intervalo entre "funde grupos verdadeiros"
   e "separa barreiras vizinhas"):

   ```bash
   cd backend
   uv run python -m scripts.analisar_sensibilidade --dispersao-metros <erro_de_gps_metros>
   ```

   `--dispersao-metros` é o raio máximo de dispersão sintética em torno de cada grupo —
   usar o erro de GPS medido no lugar do padrão (3 m) aproxima o cenário de controle da
   realidade observada em campo. A análise **não toca o banco** (roda numa transação
   desfeita, R18): pode ser repetida quantas vezes for preciso sem afetar os dados reais
   coletados.
3. **Levar o resultado (CSV em `backend/scripts/saida/`) para a orientadora**, junto
   com o funil real (§6), antes de mudar `DBSCAN_EPS_METROS`/`MIN_CONFIRMACOES` no
   `.env` de produção — é uma decisão de calibração, não uma correção de bug.
4. Registrar a decisão final em `decisoes-pendentes.md` (#4), com a data e o raciocínio,
   do mesmo jeito que a rodada sintética de 29/09/2026 já está registrada lá.

## 8. O que depende só da orientadora

Resumo — detalhe completo em [`decisoes-pendentes.md`](decisoes-pendentes.md):

| # | Pendência | Efeito na coleta se não decidida a tempo |
|---|---|---|
| 1 | Escopo de roteamento | Não afeta a coleta em si (nenhum dado de rota é pedido ao voluntário); afeta só o que o texto final promete. |
| 2 | Taxonomia final de tipos | A coleta usa os 4 tipos provisórios do pôster (§2). Trocar a taxonomia depois da coleta não invalida os dados: `tipo_id` é FK estável, e um tipo aposentado marca `ativo=false` sem apagar histórico. |
| 3 | Polígono exato da área | A coleta usa o círculo provisório de 500 m (§1). Um polígono novo só entra em vigor dali para frente — relatos já aceitos/descartados pelo geofence antigo não são reavaliados automaticamente. |
| 4 | Calibração do DBSCAN/promoção | A coleta usa os valores provisórios do `.env` (eps 8 m, `min_confirmacoes` 3). Ver §7 para o procedimento de recalibração depois. |
| 5 | Divisão de responsabilidades | Sem decisão formal, combinar informalmente entre os integrantes presentes no dia (checklist §5). |
| 6 | Atributos quantitativos (altura do degrau, ângulo da rampa) | Não coletados nesta rodada — só `tipo` + `severidade` (1–3). Se entrar no escopo depois, é uma migration nova, não uma reinterpretação dos dados já coletados. |
| 7 | Estágio 3 contar alertas, não sessões | A coleta roda com a regra atual. A boa prática "uma barreira, um relato por sessão" (§2) reduz o efeito; os dados brutos ficam guardados, então uma deduplicação decidida depois pode ser aplicada reexecutando o pipeline. |

Nenhum destes bloqueia tecnicamente a coleta: todos têm um valor provisório já
implementado e configurável. Eles bloqueiam a **defesa** do trabalho, que precisa
justificar cada valor perante a orientadora.
