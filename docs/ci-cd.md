# CI/CD (M5.1)

Como o pipeline de integração e entrega contínuas funciona. Fonte:
[`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml). Contexto do projeto:
[`CLAUDE.md`](../CLAUDE.md); pendências formais: [`decisoes-pendentes.md`](decisoes-pendentes.md).

---

## 1. O que roda em cada push (CI)

Todo `push`, em **qualquer branch**, e todo `pull request` para `main` disparam quatro
jobs, na ordem em que dependem uns dos outros:

| Job | O que faz | Depende de |
|---|---|---|
| `banco-e-backend` | Sobe só o serviço `db` (PostGIS), aplica migrations e seeds (`./db/banco.sh migrar`), roda os testes de schema (`./db/banco.sh testar`) e a suíte do backend: `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest` (bate no PostGIS real, num banco de teste à parte — G8). | — |
| `frontend` | `npm ci`, checagem de tipos (`npm run verificar`, `tsc --noEmit`) e build de produção (`npm run build`). | — |
| `ponta-a-ponta` | `./scripts/ponta-a-ponta.sh`: sobe uma pilha Docker Compose **isolada** (`msb-e2e`), roda o contrato inteiro da API por HTTP e sempre derruba a pilha no fim. | `banco-e-backend`, `frontend` |
| `publicar-imagens` | Publica as imagens da API e do frontend no GHCR. | `ponta-a-ponta` |

`ponta-a-ponta` só roda se os dois primeiros passarem: é o job mais lento (builda
imagens Docker e sobe uma pilha completa), então não vale a pena rodá-lo se algo mais
básico já quebrou. Um `concurrency` por branch cancela a execução anterior quando chega
um push novo, para não gastar minutos de runner numa versão já ultrapassada — **exceto**
em `main` e em tag de versão (`v*`), onde a execução anterior nunca é cancelada, só fica
na fila atrás da nova (ver §2, "Por que a publicação nunca é cancelada").

**Um branch com pull request aberto para `main` roda a suíte duas vezes** — uma pelo
gatilho `push` (todo commit novo no branch) e outra pelo gatilho `pull_request` (o
merge simulado contra `main`). Isso é esperado, não duplicação por engano: são grupos de
`concurrency` diferentes (`refs/heads/<branch>` vs. `refs/pull/<n>/merge`), então as duas
execuções não se cancelam uma à outra, e cada uma cobre uma pergunta diferente ("o branch
sozinho passa?" vs. "o branch integrado a `main` passa?").

## 2. O que roda só em `main` (CD)

`publicar-imagens` só executa em `push` direto para `main` (merge) ou em uma tag de
versão (`v*`) — **nunca** em `pull_request`, nunca em branch de feature. Ele:

1. Autentica no `ghcr.io` com o `GITHUB_TOKEN` do próprio job (não precisa de nenhum
   secret extra).
2. Gera as tags de cada imagem (`docker/metadata-action`): o sha curto do commit
   sempre; `latest` só quando o push é em `main`; tags semver (`vX.Y.Z`, `vX.Y`) só
   quando o push é de uma tag `v*`.
3. Builda e publica (`docker/build-push-action`, com cache `type=gha`):
   - `ghcr.io/rlbuff7/mackenzie-sem-barreiras-api` (contexto `backend/`);
   - `ghcr.io/rlbuff7/mackenzie-sem-barreiras-frontend` (contexto `frontend/`).

Fora de `main`/tag, o job aparece **pulado** (skipped) na aba Actions — isso é o
esperado, não uma falha.

### Por que a publicação nunca é cancelada

O `concurrency` do workflow cancela a execução anterior do mesmo grupo (mesmo branch)
quando chega um push novo — mas só fora de `main`/tag. Em `main` e em tag `v*`,
`cancel-in-progress` é `false`: um push novo enfileira atrás do que já está rodando, em
vez de cancelá-lo. Sem essa exceção, um segundo push logo depois do primeiro poderia
cancelar o `publicar-imagens` bem no meio do envio ao GHCR, e a imagem daquele commit
nunca sairia publicada — um problema encontrado na revisão da Task 7 (rodada 1).

### `VITE_API_URL` da imagem publicada

A imagem do frontend publicada usa `VITE_API_URL=/api` por padrão (R19: mesma origem,
`frontend/nginx.conf` encaminha `/api/` para o serviço `api`). Isso pressupõe que, onde
quer que a imagem rode, exista um serviço alcançável como `api:8000` na mesma rede
(por exemplo, o próprio `docker-compose.yml` deste repo, ou uma pilha equivalente na
hospedagem escolhida). Para publicar com outra URL (ex.: API e frontend em domínios
separados), defina a variável de repositório `VITE_API_URL` em **Settings → Secrets and
variables → Actions → Variables** antes de rodar o workflow — não é preciso editar
`ci-cd.yml`.

### Implantação (deploy) — ainda não automatizada

O workflow tem um job `implantar`, mas **desativado** (`if: false`): a hospedagem com
HTTPS (necessária para a geolocalização do navegador — ver
[`coleta-em-campo.md` §4](coleta-em-campo.md)) ainda não foi escolhida (pendência
técnica em [`decisoes-pendentes.md`](decisoes-pendentes.md)). Passo a passo para
ativar, depois que a equipe escolher a hospedagem:

1. Confirmar que a hospedagem aceita um "deploy hook" HTTP (webhook que ela expõe e
   que, ao ser chamado, puxa a imagem mais recente do GHCR e reinicia o serviço) — é o
   formato mais comum em PaaS. Se a hospedagem escolhida usar outro mecanismo (CLI
   própria, API diferente), o passo do job precisa ser reescrito.
2. Criar o secret `DEPLOY_HOOK_URL` em **Settings → Secrets and variables → Actions →
   Secrets**, com a URL daquele deploy hook.
3. Remover a linha `if: false` do job `implantar` em `ci-cd.yml`.
4. Fazer um push em `main` para confirmar que o job novo passa.

## 3. Acompanhando as execuções

- Aba **Actions** do repositório no GitHub: lista todas as execuções, com o status de
  cada job.
- `gh run list` — últimas execuções, do terminal.
- `gh run watch` — acompanha a execução em andamento (usa o id de `gh run list` se
  houver mais de uma rodando).
- `gh run view --log-failed <id>` — só os logs dos passos que falharam, útil quando um
  job quebra.

## 4. Usando as imagens publicadas

```bash
docker pull ghcr.io/rlbuff7/mackenzie-sem-barreiras-api:latest
docker pull ghcr.io/rlbuff7/mackenzie-sem-barreiras-frontend:latest
```

Também existem tags pelo sha curto do commit (`ghcr.io/.../mackenzie-sem-barreiras-api:<sha>`)
e, a partir de uma tag `vX.Y.Z` no repositório, tags semver (`:vX.Y.Z`, `:vX.Y`).

### Visibilidade do pacote

Pacotes novos no GHCR nascem **privados** por padrão, mesmo em repositório público.
Para puxar a imagem sem autenticação (ex.: de outra máquina, ou na hospedagem
escolhida), ajuste a visibilidade depois da primeira publicação:
**github.com/rlbuff7/mackenzie-sem-barreiras → aba Packages** (ou
`github.com/users/rlbuff7/packages/container/mackenzie-sem-barreiras-api/settings`) →
**Change visibility → Public**. Repita para o pacote do frontend. Enquanto privado, um
`docker pull` sem login recebe "unauthorized" — não é um erro do workflow.

## 5. Validação local do workflow

O workflow é validado com o [actionlint](https://github.com/rhysd/actionlint), via
Docker (nenhuma instalação na máquina):

```bash
docker run --rm -v "$PWD":/repo --workdir /repo rhysd/actionlint:latest -color
```

`.github/actionlint.yaml` silencia só um aviso de estilo esperado: o actionlint sugere
remover `if: false` do job `implantar` (é uma condição sempre falsa, na visão do
linter) — mas esse `if: false` é exatamente o que a Seção 2 pede, um job pronto e
inofensivo até a hospedagem ser escolhida. Nenhuma outra regra é ignorada.

## 6. Runner e versões das actions (R20)

Todo job fixa `runs-on: ubuntu-24.04`, não `ubuntu-latest`. O motivo: o GitHub avisou
que `ubuntu-latest` passa a apontar para o Ubuntu 26 a partir de 19/10/2026, e o TCC II
não pode se dar ao luxo de um runner novo (com pacotes/versões diferentes) quebrar o CI
no meio da entrega. Fica fixo em `ubuntu-24.04` por enquanto; a equipe pode migrar para
`ubuntu-latest` (ou para a versão que suceder o 24.04) com calma, depois da entrega.

Todas as actions usadas (`actions/checkout`, `astral-sh/setup-uv`, `actions/setup-node`,
`docker/login-action`, `docker/setup-buildx-action`, `docker/metadata-action`,
`docker/build-push-action`) estão fixadas na primeira major de cada uma que já roda em
Node.js 24 (`runs.using: node24` no `action.yml` da action) — o GitHub vem avisando, nas
execuções, que o Node.js 20 (usado pelas majors anteriores) está sendo descontinuado
para rodar actions. Conferido em 29/09/2026 com `git ls-remote --tags` (para achar a
major mais recente de cada action) e lendo o `action.yml` de cada uma (para confirmar
`node24`); os detalhes de qual major ficou em qual estão no relatório da Task 7.
