# Navegação Acessível no Campus Mackenzie

[![CI/CD](https://github.com/rlbuff7/mackenzie-sem-barreiras/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/rlbuff7/mackenzie-sem-barreiras/actions/workflows/ci-cd.yml)

Repositório `mackenzie-sem-barreiras` (nome do escopo antigo; renomear é decisão pendente da equipe).

Navegação e orientação espacial acessível no campus da Universidade Presbiteriana
Mackenzie. TCC, FCI/Mackenzie. Prioridade: pessoas com deficiência visual.

## O que é

Um sistema web que ajuda a pessoa a chegar de um ponto a outro do campus
com rota acessível e orientação falada e por vibração. Cobre **só as áreas externas**
(decisão de 14/10/2026): sem beacons, Wi-Fi fingerprinting nem QR code.

**Princípio de segurança:** o sistema é apoio à orientação, **nunca substituto de bengala,
cão-guia ou técnicas de mobilidade**. Na dúvida, ele cala: silêncio é melhor que palpite.

O escopo mudou em 08/10/2026. Antes, o projeto era um mapa de crowdsourcing de barreiras
de acessibilidade. Contexto completo, requisitos, decisões e convenções:
[CLAUDE.md](CLAUDE.md).

## Estado atual (14/10/2026)

O escopo novo está no começo: o repositório ainda tem o código do escopo antigo e a
documentação está sendo atualizada. Ainda **não existem** as tabelas de grafo (`nos`,
`arestas`, `pontos_interesse`), o pgRouting, `app/orientacao/` nem as rotas novas.

**Reaproveitado do escopo antigo, continua em uso:**

- Docker Compose e PostGIS
- migrations e seeds com `db/banco.sh`
- backend FastAPI e sua estrutura
- frontend Leaflet com proxy same-origin no nginx
- CI/CD no GitHub Actions, com imagens no GHCR
- pilha de produção com `TOKEN_ADMIN` obrigatório e HTTPS via túnel (necessário para
  geolocalização e bússola do celular)

**Aposentado (fica no repositório e no histórico, mas não é mais desenvolvido):**

- a camada de validação de crowdsourcing, `backend/app/validacao/`
- as tabelas `alertas`, `barreiras`, `alertas_rejeitados` e `area_estudo`
- o gerador de dados sintéticos, a análise de sensibilidade e a figura do funil (a seção
  "Simulação" do README antigo saiu daqui; os scripts continuam em `backend/scripts/`)
- o protocolo de coleta colaborativa em campo

**Infra do protótipo (decidido em 14/10/2026):** servido pela AWS, com a conta e os
créditos do Rodrigo; o túnel Cloudflare fica como plano B (R41 em
[`docs/decisoes-de-implementacao.md`](docs/decisoes-de-implementacao.md)). Ainda não
implantado.

Pontos em aberto com a orientadora: [docs/decisoes-pendentes.md](docs/decisoes-pendentes.md).
Significado dos identificadores citados no código e nos commits (G1–G12, D1–D8,
R1–R41, "Task N"): [docs/decisoes-de-implementacao.md](docs/decisoes-de-implementacao.md).

## Estrutura

```
scripts/     scripts de nível de repositório (teste ponta a ponta, preparar-coleta)
db/          migrations e seeds SQL
backend/     API FastAPI (backend/app/validacao/ é do escopo antigo)
frontend/    mapa web (TypeScript + Leaflet), com Dockerfile próprio
docs/        decisões, implantação, CI/CD e docs/academico/; vários documentos são do escopo antigo
```

Árvore e convenções do escopo novo: [`CLAUDE.md`](CLAUDE.md).

## Onde clonar o projeto

Clone dentro do sistema de arquivos do WSL (por exemplo `~/projetos`), nunca sob
`/mnt/c` nem dentro do OneDrive: bind mounts em `/mnt/c` são lentos, o
`uvicorn --reload` (inotify) não enxerga as mudanças de arquivo ali, e o OneDrive pode
interferir em arquivos sendo gravados e no `.git`. O banco usa um volume nomeado do
Docker (não uma pasta do projeto) porque o Postgres exige permissões POSIX no diretório
de dados, que o NTFS/OneDrive não oferece (comentário do volume em `docker-compose.yml`).

## Rodando localmente

Pré-requisito: Docker com Compose v2. Nada é instalado direto na máquina.

```bash
cp .env.example .env               # primeira vez; troque a senha
docker compose up -d --build --wait   # sobe db + api + frontend (aguarde os três "healthy")
./db/banco.sh migrar               # cria as tabelas e carrega os seeds
./db/banco.sh testar               # confere tabelas, constraints e seeds
```

O `migrar` pode ser rodado quantas vezes quiser: só aplica as migrations novas
e atualiza os seeds. A API só responde depois do `migrar`. As rotas atuais ainda são
as do escopo antigo (contrato em [`docs/api.md`](docs/api.md), marcado como antigo); as
rotas novas (`/pontos-interesse`, `/rotas`, `/orientacoes`) ainda não existem.

> **Atenção:** o banco principal de desenvolvimento guarda a simulação do escopo antigo.
> Não rode `zerar-real` nele nem apague dados sem backup (`./db/banco.sh backup`).

URLs (portas padrão; ajustáveis por `*_PORTA_HOST` no `.env`):

| Serviço | URL |
|---|---|
| Frontend (mapa) | http://localhost:8081 |
| API | http://localhost:8000 |
| Banco (psql/cliente gráfico) | `localhost:5434`, usuário e senha do `.env` |

O frontend fala com a API pela MESMA origem (`http://localhost:8081/api/...`):
`frontend/nginx.conf` encaminha `/api/` para o serviço `api` dentro da rede do
compose (R19), então o navegador nunca faz uma requisição cross-origin — e
`CORS_ORIGENS` não precisa listar a porta do frontend. A porta padrão é 8081,
não 8080: 8080 costuma já estar ocupada por outro serviço na máquina de quem
desenvolve (Jenkins, Tomcat, etc.).

Conectar ao banco: `./db/banco.sh psql`, ou de um cliente gráfico (DBeaver,
pgAdmin) em `localhost:5434`, com usuário e senha do `.env`.

Parar sem perder dados: `docker compose down`.
Apagar o banco e recomeçar do zero: `docker compose down -v`, depois `up` e
`migrar` de novo.

## Testes

```bash
./db/banco.sh testar          # schema, constraints e seeds (SQL, em transação desfeita)
cd backend && uv run pytest   # API, no banco de teste (${POSTGRES_DB}_teste)
./scripts/ponta-a-ponta.sh    # contrato inteiro por HTTP, numa pilha isolada (msb-e2e)
```

`scripts/ponta-a-ponta.sh` sobe uma pilha Docker Compose **isolada**
(`COMPOSE_PROJECT_NAME=msb-e2e`, portas 55434/58000/58080, volume próprio), roda os
testes por HTTP e **sempre** derruba essa pilha no fim. Nunca toca a pilha principal.
Requer bash >= 4.2 e `python3` no PATH.

## Integração e entrega contínuas

Todo push e todo pull request para `main` rodam os testes no GitHub Actions. Todo push
em `main` publica as imagens Docker da API e do frontend no GHCR. Detalhes:
[`docs/ci-cd.md`](docs/ci-cd.md).

## Implantação

A pilha de produção (`docker-compose.prod.yml`, imagens do GHCR, `TOKEN_ADMIN`
obrigatório), o HTTPS para o celular (profile `tunel`) e backup/restauração:
[`docs/implantacao.md`](docs/implantacao.md). Os passos de coleta desse documento
são do escopo antigo.

## Backend

`docker compose up` já sobe a API. Para rodar fora do container (reload, testes),
com [`uv`](https://docs.astral.sh/uv/) instalado e o banco rodando:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
```

Os testes recriam `${POSTGRES_DB}_teste` do zero a cada execução e nunca tocam no
banco de desenvolvimento.

## Marcos

**TCC I (entrega conceitual)**

- [ ] **E1**: escopo atualizado (problema, público-alvo, objetivos)
- [ ] **E2**: requisitos RF/RNF revisados, com critério de verificação por item
- [ ] **E3**: diagrama de arquitetura e estudo das tecnologias de localização e áudio, com a medição de GPS
- [ ] **E4**: plano de mapeamento do campus
- [ ] **E5**: cronograma e divisão de responsabilidades
- [ ] **E6**: protótipo demonstrativo (mapa 2D, rota e uma orientação falada), se der tempo

O banner com o protótipo é no começo de novembro de 2026 (Projeto Parcial em novembro).
As entregas virão como `docs/requisitos.md`, `docs/arquitetura.md`,
`docs/mapeamento-campus.md`, `docs/medicao-gps.md` e `docs/protocolo-avaliacao.md`
(ainda não existem).

**Código (em paralelo; um marco por vez)**

- [ ] **M1**: migrations novas (`pontos_interesse`, `nos`, `arestas`, pgRouting)
- [ ] **M2**: recorte do campus digitalizado
- [ ] **M3**: `GET /pontos-interesse` e `POST /rotas`
- [ ] **M4**: `app/orientacao/` com testes e `POST /orientacoes`
- [ ] **M5**: frontend com seleção de destino, rota, voz e vibração
- [ ] **M6**: avaliação com usuários (depende do Comitê de Ética)

Os marcos M0 a M5.1 do escopo antigo foram concluídos e estão registrados no histórico
do Git. A coleta em campo (M6 antigo) nunca foi realizada.

**Cronograma oficial (agosto/2026 a maio/2027)**

- até novembro/2026: TCC I (banner e Projeto Parcial)
- dezembro/2026 a fevereiro/2027: desenvolvimento
- fevereiro a maio/2027: TCC II, com a avaliação com usuários em abril
- maio/2027: defesa

## Documentação

- [`CLAUDE.md`](CLAUDE.md): contexto permanente do projeto (escopo novo)
- [`docs/decisoes-pendentes.md`](docs/decisoes-pendentes.md): pendências com a orientadora
- [`docs/decisoes-de-implementacao.md`](docs/decisoes-de-implementacao.md): glossário (R1–R41)
- [`docs/implantacao.md`](docs/implantacao.md) e [`docs/ci-cd.md`](docs/ci-cd.md): produção e CI/CD
- Escopo antigo (com aviso no topo): [`docs/api.md`](docs/api.md),
  [`docs/coleta-em-campo.md`](docs/coleta-em-campo.md),
  [`docs/orientadora/pauta-reuniao.md`](docs/orientadora/pauta-reuniao.md),
  [`docs/texto-tcc/`](docs/texto-tcc/)
- [`docs/academico/`](docs/academico/): pôster e artigo do TCC I
