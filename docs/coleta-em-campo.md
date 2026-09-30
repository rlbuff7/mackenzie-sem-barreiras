# Protocolo de coleta em campo (M6)

Preparação para a coleta REAL de dados (`origem='real'`), no entorno do campus
Higienópolis do Mackenzie. Este documento não é código: é o roteiro operacional do dia
de coleta e o que precisa estar decidido antes dele. Contexto do projeto: [`CLAUDE.md`](../CLAUDE.md);
pendências formais: [`decisoes-pendentes.md`](decisoes-pendentes.md).

Convenção usada abaixo: cada item traz uma marca —

- **[ORIENTADORA]** — depende de decisão da orientadora (`decisoes-pendentes.md` #1–#4, #6 e #7; a #5 já está decidida).
  Enquanto pendente, a coleta usa o valor provisório já no `.env`/nos seeds.
- **[EQUIPE]** — depende só de decisão interna dos integrantes (ex.: hospedagem, HTTPS).
  Nada aqui exige a orientadora. O HTTPS já tem uma opção pronta, sem conta (Quick Tunnel
  em container, §4); a hospedagem com conta segue a critério da equipe.

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
- **Os logs deste projeto não guardam IP no uso normal.** O nginx do frontend usa um
  formato de log próprio, sem o endereço do cliente e sem nenhum header que o carregue:
  só hora, método, caminho sem a query string, status e tempos (`frontend/nginx.conf`).
  O log de erro do nginx fica no nível `crit`: as mensagens de erro dele trazem o IP do
  cliente, e nesse nível o uso normal (limite de envios, corpo grande demais, conexão
  fechada pelo cliente) não gera registro; só um erro grave e raro (por exemplo, falta
  de descritores de arquivo) ainda poderia gravar um IP. O nginx usa o IP só em memória,
  para o limite de envios (a zona do `limit_req`, que não vai para disco), e não o
  repassa à API: no proxy `/api/` ele zera os headers que carregam o IP do voluntário
  (`X-Forwarded-For`, `X-Real-IP` e, atrás da Cloudflare, `CF-Connecting-IP` e
  `True-Client-IP`), então o log da API (uvicorn) registra só o endereço interno do
  nginx na rede do compose. Atrás do Quick Tunnel, o endereço que o próprio nginx
  enxerga é o do container do túnel, não o do voluntário. Isso vale para os containers
  deste repositório: o túnel ou a hospedagem escolhidos (§4) têm os próprios logs, fora
  do nosso controle. Conferir a política do serviço escolhido e citá-la no texto de
  consentimento.
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

**Texto sugerido para o consentimento** (revisar com a orientadora antes da coleta). A
frase da Cloudflare vale para o Quick Tunnel (§4); numa hospedagem própria, troque-a
pelo intermediário escolhido.

> Este mapa faz parte de um TCC da FCI/Mackenzie sobre barreiras de acessibilidade.
> Cada relato que você envia grava o ponto no mapa, o tipo da barreira, a severidade e
> a descrição (se você preencher) e a hora do envio. Não pedimos nome nem contato e não
> gravamos o endereço IP do seu aparelho. O navegador recebe um código aleatório que
> junta os seus relatos, para contarmos confirmações de pessoas diferentes; com ele dá
> para ver o caminho dos seus relatos, mas não quem você é. O mapa de fundo vem do
> OpenStreetMap, que recebe o IP do seu aparelho para enviar as imagens. O acesso ao mapa
> passa pela Cloudflare (o endereço termina em trycloudflare.com), que faz a conexão
> segura chegar até nós: ela recebe o IP do seu aparelho e o conteúdo de cada relato
> antes de nós. Não escreva dados pessoais na descrição. Os dados servem ao TCC e não
> serão publicados relato a relato com esse código.

## 4. Requisito técnico: HTTPS para geolocalização [EQUIPE]

Navegadores modernos só liberam `navigator.geolocation` (usada pelo botão "Usar minha
localização" do frontend, `frontend/src/mapa.ts`) em **contexto seguro**: HTTPS, ou
`localhost` puro. Com a pilha servida por HTTP simples, o botão de localização
automática falha no celular — só resta o botão "Usar o centro do mapa" e tocar
manualmente, o que derrota o propósito de captar o ponto certo em campo.

**Ganho prático do proxy same-origin (R19):** desde que `frontend/nginx.conf` passou a
encaminhar `/api/` para o serviço `api` pela mesma origem, só o **frontend** precisa
ficar acessível por HTTPS na internet — a API não precisa mais de uma URL pública
própria nem de CORS liberado para o domínio da coleta; o navegador do voluntário só
fala com o container do frontend, que fala com a API por dentro da rede do compose. Ou
seja, expor **um único endpoint HTTPS** (o frontend), não dois.

**Consequência: toda a API fica pública junto com o mapa.** A porta da API nunca é
exposta, mas qualquer rota dela responde por `/api/` na URL da coleta, inclusive
`/api/validacao/executar` (que apaga e recria as barreiras reais, D6) e a documentação
interativa em `/api/docs`. Na **pilha de produção** (`docker-compose.prod.yml`) as duas
proteções já vêm travadas: `TOKEN_ADMIN` é obrigatório (o compose recusa subir sem ele;
com ele vazio, a execução do pipeline ficaria aberta a quem tivesse a URL, D7) e
`EXPOR_DOCS` é fixo em `false` (`/docs`, `/redoc` e `/openapi.json` respondem 404 e o
esquema da API não fica público). Numa hospedagem própria, repita as duas coisas antes
de publicar.

**Opção pronta, sem conta: Quick Tunnel em container (R30).** O
`docker-compose.prod.yml` traz o serviço `tunel` (profile `tunel`, imagem
`cloudflare/cloudflared` com versão fixa), que expõe só o frontend da pilha de produção
numa URL `https://<aleatório>.trycloudflare.com`. É um container: nada é instalado na
máquina de quem hospeda. Ele não volta sozinho depois de reiniciar (`restart: "no"`), e a
URL muda a cada subida. Como subir, testar, reabrir e derrubar:
[`implantacao.md`](implantacao.md) §5, §8 e §10.

**Hospedagem com conta: a critério da equipe.** Se a equipe quiser uma URL fixa, ou não
depender da máquina de ninguém durante a coleta, as alternativas abaixo seguem abertas
(`decisoes-pendentes.md` T6). Nenhuma está implementada:

| Opção | Situação | Vantagens | Desvantagens |
|---|---|---|---|
| **Quick Tunnel** (`cloudflared` em container, profile `tunel`) | **Pronta** (R30): `docker-compose.prod.yml` e `implantacao.md` | Sem conta nem domínio; nada instalado na máquina; sobe e derruba no dia; um endpoint só (o frontend). | URL muda a cada subida; depende da máquina e da internet de quem hospeda durante toda a coleta; serviço gratuito, sem garantia de disponibilidade; a Cloudflare termina o TLS e vê o IP e o conteúdo do relato (§3). |
| **Túnel nomeado da Cloudflare** | Não implementado: exige conta e um domínio | URL fixa, reutilizável em coletas futuras. | Conta e domínio para manter; o mesmo intermediário (Cloudflare) da opção pronta. |
| **Hospedagem com HTTPS de fábrica** (PaaS) | Não implementada: exige conta | URL estável; não depende do notebook de ninguém durante a coleta; sem CORS para configurar (mesma origem). | Expõe também o banco (ou um banco gerenciado); `TOKEN_ADMIN` e `EXPOR_DOCS=false` definidos ANTES de publicar; dependendo do provedor, custo ou limite de uso; o job `implantar` do CI (hoje `if: false`) teria de ser ativado (`docs/ci-cd.md`). |

Qualquer que seja a escolha, ela não muda o contrato da API nem o pipeline — só onde
`frontend`/`api` ficam acessíveis. Registrar a decisão final em
`decisoes-pendentes.md` (T6) quando ela acontecer.

## 5. Checklist do dia

O passo a passo operacional (comandos, na ordem) está em
[`implantacao.md`](implantacao.md): §2–§7 no primeiro dia, §8 nos dias seguintes. Tudo
roda na **pilha de produção** (`docker-compose.prod.yml`, `./db/banco.sh --prod`), nunca
na de desenvolvimento.

Antes de ir a campo:

- [ ] **[EQUIPE]** Testar o HTTPS: com o Quick Tunnel (§4), validar o botão de
      geolocalização num celular de verdade, não só no navegador do notebook
      ([`implantacao.md`](implantacao.md) §6). Hospedagem com conta só se a equipe decidir.
- [ ] **Pilha de produção no ar** ([`implantacao.md`](implantacao.md) §2–§4): imagens do
      GHCR, `TOKEN_ADMIN` gravado no `.env` da máquina de produção (obrigatório; um valor
      longo e aleatório, `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`),
      `EXPOR_DOCS` fixo em `false`, `./db/banco.sh --prod migrar` aplicado (tabelas,
      seeds e, principalmente, o polígono da área de estudo atual) e
      `./scripts/preparar-coleta.sh` sem falhas (ele confere token, docs, saúde,
      migrations e o funil real).
- [ ] `EXPOR_DOCS=false ./scripts/ponta-a-ponta.sh` verde na máquina de produção (o
      prefixo vale só para esse comando, e o E2E lê o `TOKEN_ADMIN` do `.env`,
      [`implantacao.md`](implantacao.md) §2). Não use `export TOKEN_ADMIN=...`: um `up`
      da produção feito depois, no mesmo terminal, recriaria a API com o token do shell
      (pilha isolada: prova que a cadeia inteira responde por HTTP,
      que a execução sem o header é recusada com 401, que `/docs`, `/redoc` e
      `/openapi.json` respondem 404, e confere o `preparar-coleta.sh` e o `zerar-real`
      com relatos reais).
- [ ] Cada integrante com o celular carregado e a URL de coleta salva/testada.
- [ ] Combinar quem faz o quê em campo. A divisão geral está decidida
      (`decisoes-pendentes.md` #5, 29/09/2026: código = rlbuff7; infra = Victor (VSWH);
      dados reais = Maurício); falta só combinar os papéis de cada pessoa no dia.
- [ ] **Só antes da PRIMEIRA abertura: zerar os dados reais de teste.** Todo POST na
      pilha de coleta grava `origem='real'`: o relato de teste pelo celular, os testes
      manuais no mapa e até um corpo inválido (que vira uma linha em
      `alertas_rejeitados`). O passo a passo é o de
      [`implantacao.md`](implantacao.md) §7: `./db/banco.sh --prod backup`,
      `./db/banco.sh --prod zerar-real` sem o argumento (mostra as contagens e quantos
      relatos reais há, de que data a que data) e, se forem só os testes de agora há
      pouco, `--sim-apagar-dados-reais` (apaga as linhas `origem='real'` das quatro
      tabelas numa transação e nunca toca a simulação). É SÓ para este momento, uma vez:
      depois de aberta a coleta, essas linhas são os dados do TCC. Reabrir a coleta num
      dia seguinte, ou depois de o túnel cair, é o [`implantacao.md`](implantacao.md) §8
      (`./scripts/preparar-coleta.sh --reabrir`), sem apagar nada.
- [ ] `alertas.recebidos = 0` em `estatisticas?origem=real` logo antes da PRIMEIRA
      abertura (o item 4 do `preparar-coleta.sh` confere). Nos dias seguintes,
      `recebidos` só pode crescer.
- [ ] **Congelar os seeds (tipos e polígono) até o fim da coleta.** `./db/banco.sh
      --prod migrar` reaplica `db/seeds/` a cada execução. Se o polígono mudasse no meio,
      o funil real misturaria relatos julgados por dois geofences diferentes (e uma troca
      de taxonomia mudaria os tipos aceitos). Não edite `db/seeds/` nem rode `migrar`
      com seeds alterados enquanto a coleta estiver aberta.
- [ ] Registrar a versão em vigor: o `preparar-coleta.sh` grava o commit, o hash dos
      seeds e as imagens em execução (ID e RepoDigest do GHCR) em
      `backend/scripts/saida/coleta-prod[-reabrir]-<data-hora>.txt`, um arquivo por execução.
      Guarde esses registros com os backups: é o que permite ao texto citar exatamente
      que código, polígono e parâmetros produziram o funil real.

Durante a coleta:

- [ ] **Não testar na pilha de coleta.** Depois de aberta, todo envio nela é um relato
      real. Para testar algo, use `./scripts/ponta-a-ponta.sh`, que sobe uma pilha
      isolada e a apaga no fim.
- [ ] Túnel caiu ou a URL mudou? [`implantacao.md`](implantacao.md) §8 (reabrir), nunca
      `zerar-real`.
- [ ] Reportar sempre no local (§2).
- [ ] Anotar (fora do sistema, num papel/app qualquer da equipe) observações que não
      cabem no formulário — por exemplo, comparar o GPS do celular com a posição real,
      para alimentar a calibração do §7.

Depois da coleta (mesmo dia ou no seguinte, com a pilha de produção ainda de pé):

- [ ] Backup antes de mexer em qualquer coisa: `./db/banco.sh --prod backup`.
- [ ] Rodar o pipeline sobre os dados reais, na API de PRODUÇÃO, com `X-Token-Admin`
      (D7): §6, passo 1.
- [ ] Conferir o funil: §6, passo 2.
- [ ] Gerar a figura, lendo o banco de PRODUÇÃO: §6, passo 3.
- [ ] Backup de novo, depois do último `executar` ([`implantacao.md`](implantacao.md) §9).

## 6. Rodando o pipeline e a figura com dados reais

Depois que os relatos de campo estiverem no banco (via `POST /alertas`, sempre
`origem='real'` — nunca inserção manual). Tudo contra a **pilha de produção**: API em
`localhost:${API_PORTA_PROD:-8010}` e banco em `localhost:${POSTGRES_PORTA_PROD:-5435}`
(as duas só em `127.0.0.1`). A pilha de desenvolvimento (8000/5434) não tem os dados da
coleta. Se o `.env` mudou `API_PORTA_PROD` ou `POSTGRES_PORTA_PROD`, use as portas de lá.

```bash
# A partir da raiz do checkout da máquina de produção. O token é lido do .env
# (implantacao.md §2), sem aparecer na tela nem no histórico.

# 1. Roda os estágios 3 e 4 (agrupamento + promoção) sobre origem=real.
curl -fsS -X POST "http://localhost:${API_PORTA_PROD:-8010}/validacao/executar?origem=real" \
  -H "X-Token-Admin: $(sed -n 's/^TOKEN_ADMIN=//p' .env | tail -n 1)"

# 2. Confere o funil.
curl -fsS "http://localhost:${API_PORTA_PROD:-8010}/validacao/estatisticas?origem=real"

# 3. Gera a figura (a partir de backend/, com o grupo opcional de matplotlib), lendo o
#    banco de PRODUÇÃO: a porta vale só para este comando.
cd backend
uv sync --group analise
POSTGRES_PORTA=${POSTGRES_PORTA_PROD:-5435} uv run python -m scripts.gerar_figura_funil --origem real
```

O script imprime `Lendo as estatísticas de origem=real do banco localhost:5435/<banco>`:
confira a porta da produção (5435, não 5434). O rodapé da figura registra o mesmo
("Dados de localhost:5435/<banco>"). A figura sai em `docs/figuras/funil-real.svg`/`.png`
— sem o rótulo "SIMULAÇÃO", porque agora é dado real de verdade
(`ROTULOS_POR_ORIGEM["real"] = "Dados reais de campo"`, `app/validacao/estatisticas.py`).
Nada aqui toca `origem='simulacao'`: as duas origens nunca se misturam (G10), então a
figura da simulação continua disponível para comparação.

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
| 5 | Divisão de responsabilidades | **Decidida em 29/09/2026:** código = rlbuff7; infra = Victor (VSWH); dados reais = Maurício. Não depende mais da orientadora; combinar só os papéis do dia (checklist §5). |
| 6 | Atributos quantitativos (altura do degrau, ângulo da rampa) | Não coletados nesta rodada — só `tipo` + `severidade` (1–3). Se entrar no escopo depois, é uma migration nova, não uma reinterpretação dos dados já coletados. |
| 7 | Estágio 3 contar alertas, não sessões | A coleta roda com a regra atual. A boa prática "uma barreira, um relato por sessão" (§2) reduz o efeito; os dados brutos ficam guardados, então uma deduplicação decidida depois pode ser aplicada reexecutando o pipeline. |

Nenhum destes bloqueia tecnicamente a coleta: todos têm um valor provisório já
implementado e configurável. Eles bloqueiam a **defesa** do trabalho, que precisa
justificar cada valor perante a orientadora.
