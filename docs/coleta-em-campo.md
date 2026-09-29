# Protocolo de coleta em campo (M6)

Preparação para a coleta REAL de dados (`origem='real'`), no entorno do campus
Higienópolis do Mackenzie. Este documento não é código: é o roteiro operacional do dia
de coleta e o que precisa estar decidido antes dele. Contexto do projeto: [`CLAUDE.md`](../CLAUDE.md);
pendências formais: [`decisoes-pendentes.md`](decisoes-pendentes.md).

Convenção usada abaixo: cada item traz uma marca —

- **[ORIENTADORA]** — depende de decisão da orientadora (`decisoes-pendentes.md` #1–#6).
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
  confirmação" (o pipeline conta *sessões distintas*, D1/D4), só infla `recebidos` sem
  ajudar a promoção.
- **Sessões diferentes SIM ajudam.** O valor de uma barreira ser vista por pessoas
  diferentes é exatamente o que a promoção mede (`MIN_CONFIRMACOES` sessões distintas,
  hoje **[ORIENTADORA] #4** = 3). Se o grupo tem várias pessoas, é melhor cada uma abrir
  o mapa na própria sessão do que dividir uma sessão só entre todos.
- **Relatar no exato ponto da barreira**, não num ponto aproximado a alguns metros —
  o `DBSCAN_EPS_METROS` provisório (**[ORIENTADORA] #4**, hoje 8 m) foi calibrado com
  dados sintéticos; erro de GPS maior que isso é justamente o que a calibração de campo
  (§6) vai medir.

## 3. Ética e LGPD

- **Nenhum dado pessoal é coletado.** Não há campo de nome, e-mail, telefone ou
  qualquer identificador de pessoa no formulário (`docs/api.md`, `POST /alertas`).
- **Sem fotos.** O contrato da API não tem campo de imagem; não é para inventar um
  campo de imagem "por fora" no dia da coleta.
- **Sem IP.** O servidor nunca grava o endereço IP de quem reporta (T3,
  `app/validacao/entrada.py::calcular_sessao_hash`).
- **Sessão é um UUID aleatório**, gerado no navegador e guardado só em `localStorage`
  do próprio aparelho (D1); o servidor grava apenas `sha256(uuid)`, nunca o UUID cru.
  Quem limpa o navegador (ou usa outro aparelho) vira uma "sessão nova" — é uma
  limitação conhecida e aceita (T3), não um bug.
- **Geolocalização é o único dado sensível de fato**, e é o dado central do projeto
  (mapear onde estão as barreiras). Ela não é vinculável a uma pessoa depois do envio:
  não existe tabela ou campo que ligue um `alerta` a um indivíduo identificado.

## 4. Requisito técnico: HTTPS para geolocalização [EQUIPE]

Navegadores modernos só liberam `navigator.geolocation` (usada pelo botão "Usar minha
localização" do frontend, `frontend/src/mapa.ts`) em **contexto seguro**: HTTPS, ou
`localhost` puro. Em produção com `docker compose up` simples (HTTP), o botão de
localização automática falha no celular — só resta o botão "Usar o centro do mapa" e
tocar manualmente, o que derrota o propósito de captar o ponto certo em campo.

**Isto ainda não está decidido — decidir com a equipe antes do dia da coleta.** Duas
famílias de opção, sem escolher nenhuma aqui:

| Opção | Como funciona | Vantagens | Desvantagens |
|---|---|---|---|
| **Túnel (ex.: `cloudflared`)** | Um túnel expõe o `frontend`/`api` locais (rodando no notebook de alguém, via `docker compose up`) numa URL HTTPS pública temporária. | Sem precisar publicar a imagem em lugar nenhum; sobe e derruba no dia; usa a mesma stack já testada neste M5. | URL muda a cada sessão (a não ser que se configure um domínio fixo); depende da internet/notebook de quem hospeda o túnel durante toda a coleta; exige instalar a ferramenta do túnel (fora do escopo de "nada é instalado direto na máquina" do resto do projeto — table isolada, não persistente). |
| **Hospedagem gratuita** (ex.: um provedor de PaaS/estático com HTTPS incluso) | Sobe as imagens (ou o build do frontend + a API) para um serviço externo com HTTPS de fábrica. | URL estável, reutilizável em coletas futuras; não depende do notebook de ninguém durante a coleta. | Precisa expor a API (e o banco, ou um banco gerenciado) na internet — implica revisar CORS, `TOKEN_ADMIN` (hoje provisório) e, dependendo do provedor, custo ou limite de uso; mais um passo de configuração para manter. |

Qualquer que seja a escolha, ela não muda o contrato da API nem o pipeline — só onde
`frontend`/`api` ficam acessíveis. Registrar a decisão final em
`decisoes-pendentes.md` quando ela acontecer.

## 5. Checklist do dia

Antes de ir a campo:

- [ ] **[EQUIPE]** Decidir e testar a opção de HTTPS (§4) — validar o botão de
      geolocalização num celular de verdade, não só no navegador do notebook.
- [ ] Confirmar que a stack sobe do zero: `docker compose up -d --build --wait`
      (`docker compose ps` — os três serviços `healthy`).
- [ ] `./db/banco.sh migrar` já aplicado (tabelas, seeds e, principalmente, o polígono
      da área de estudo atual).
- [ ] `./scripts/ponta-a-ponta.sh` verde (prova que a cadeia inteira responde por HTTP
      antes de sair a campo).
- [ ] Cada integrante com o celular carregado e a URL de coleta salva/testada.
- [ ] Combinar quem faz o quê em campo (ver **[ORIENTADORA] #5**, ainda em aberto —
      na falta de uma divisão formal, combinar informalmente para o dia).

Durante a coleta:

- [ ] Reportar sempre no local (§2).
- [ ] Anotar (fora do sistema, num papel/app qualquer da equipe) observações que não
      cabem no formulário — por exemplo, comparar o GPS do celular com a posição real,
      para alimentar a calibração do §6.

Depois da coleta (mesmo dia ou no seguinte, com a stack ainda de pé):

- [ ] Rodar o pipeline sobre os dados reais: `POST /validacao/executar?origem=real`
      (com `X-Token-Admin` se `TOKEN_ADMIN` estiver configurado, D7).
- [ ] Conferir o funil: `GET /validacao/estatisticas?origem=real`.
- [ ] Gerar a figura (§7).

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

A análise de sensibilidade (`backend/scripts/analisar_sensibilidade.py`) hoje só mede
CONTROLE sintético (ver `decisoes-pendentes.md` #4). Depois da primeira coleta real, o
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

Nenhum destes bloqueia tecnicamente a coleta: todos têm um valor provisório já
implementado e configurável. Eles bloqueiam a **defesa** do trabalho, que precisa
justificar cada valor perante a orientadora.
