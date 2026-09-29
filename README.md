# Mackenzie sem Barreiras

[![CI/CD](https://github.com/rlbuff7/mackenzie-sem-barreiras/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/rlbuff7/mackenzie-sem-barreiras/actions/workflows/ci-cd.yml)

Mapeamento colaborativo de acessibilidade urbana no entorno da Universidade
Presbiteriana Mackenzie. TCC, FCI/Mackenzie.

Voluntários reportam barreiras físicas num mapa web. O sistema filtra, agrupa e
valida os reports antes de persistir em banco espacial (PostgreSQL + PostGIS).

Contexto completo do projeto, decisões e convenções: [CLAUDE.md](CLAUDE.md).
Pontos em aberto: [docs/decisoes-pendentes.md](docs/decisoes-pendentes.md).
Significado dos identificadores citados no código e nos commits (G1–G12, D1–D8,
R1–R27, "Task N"): [docs/decisoes-de-implementacao.md](docs/decisoes-de-implementacao.md).

## Estrutura

```
scripts/     scripts de nível de repositório (M5: teste ponta a ponta)
db/          migrations e seeds SQL
backend/     API FastAPI e camada de validação (backend/app/validacao/)
frontend/    mapa web (TypeScript + Leaflet), com Dockerfile próprio (M5)
docs/        contrato da API, decisões pendentes, protocolo de coleta e docs/academico/
```

Árvore completa e comentada: [`CLAUDE.md` §3](CLAUDE.md).

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
e atualiza os seeds. A API só responde depois do `migrar` (precisa das tabelas
e da taxonomia). Contrato completo em [`docs/api.md`](docs/api.md); rápido:

```bash
curl localhost:8000/tipos-barreira
sessao_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
curl -X POST localhost:8000/alertas -H 'Content-Type: application/json' -d \
  '{"latitude": -23.5472, "longitude": -46.6525, "tipo": "degrau", "sessao_id": "'"$sessao_id"'"}'
```

> **Atenção: todo POST na pilha principal grava dado REAL** (`origem='real'`): este
> `curl`, um envio pelo mapa em http://localhost:8081 e até um corpo inválido (que vira
> uma linha em `alertas_rejeitados`). Esses dados entram no funil da coleta em campo.
> Para testar sem sujar nada, use `./scripts/ponta-a-ponta.sh` (pilha isolada). Antes
> de abrir a coleta, limpe o que os testes deixaram com
> `./db/banco.sh zerar-real --sim-apagar-dados-reais` (sem o argumento, só mostra o
> que seria apagado); ver [`docs/coleta-em-campo.md`](docs/coleta-em-campo.md) §5.

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
cd backend && uv run pytest   # API e validacao/, no banco de teste (${POSTGRES_DB}_teste)
./scripts/ponta-a-ponta.sh    # M5: contrato inteiro por HTTP, numa pilha isolada (msb-e2e)
```

`scripts/ponta-a-ponta.sh` sobe uma pilha Docker Compose **isolada**
(`COMPOSE_PROJECT_NAME=msb-e2e`, portas 55434/58000/58080, volume próprio), aplica
migrations/seeds nela, roda `backend/scripts/ponta_a_ponta.py` (saúde, taxonomia,
entrada de alertas, pipeline em lote, consulta de barreiras, estatísticas, o
proxy `/api/` do frontend — R19 — e o próprio frontend) e **sempre** derruba
essa pilha no fim (`down -v`, mesmo em falha ou Ctrl-C) — nunca toca a pilha
principal nem o banco dela.

## Integração e entrega contínuas

Todo push (qualquer branch) e todo pull request para `main` rodam esses mesmos
testes automaticamente no GitHub Actions — banco, backend, frontend e ponta a
ponta. Todo push em `main` publica as imagens Docker da API e do frontend,
prontas para implantar. Detalhes de cada job, como acompanhar as execuções e
como usar as imagens publicadas: [`docs/ci-cd.md`](docs/ci-cd.md).

## Implantação e coleta

A pilha de produção (`docker-compose.prod.yml`, imagens do GHCR, `TOKEN_ADMIN`
obrigatório), o HTTPS sem conta para o celular (profile `tunel`), backup/restauração,
o checklist `scripts/preparar-coleta.sh` e o roteiro do dia de coleta:
[`docs/implantacao.md`](docs/implantacao.md).

## Backend

`docker compose up` já sobe a API (serviço `api`, build de `backend/Dockerfile`).
Para rodar fora do container (reload automático, testes) — pré-requisito:
[`uv`](https://docs.astral.sh/uv/) instalado; banco de cima já rodando.

```bash
cd backend
uv sync                                        # instala as dependências (backend/pyproject.toml)
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                                   # bate no PostGIS real, num banco de teste à parte
```

Os testes recriam `${POSTGRES_DB}_teste` do zero a cada execução
(`../db/banco.sh preparar-teste`, chamado por `backend/tests/conftest.py`) —
nunca tocam no banco de desenvolvimento.

## Simulação

> **Aviso de honestidade acadêmica.** Tudo nesta seção é **SIMULAÇÃO**: dados sintéticos
> para desenvolver e avaliar o pipeline, gravados com `origem='simulacao'` e rotulados
> "SIMULAÇÃO" em toda saída. Não são coleta real e não podem ser apresentados como tal.
> Nenhum destes scripts toca os dados reais (`origem='real'`).

Os scripts ficam em `backend/scripts/` e rodam contra o banco do `.env` (banco rodando,
`migrar` aplicado). Todos a partir de `backend/`:

```bash
# 1. Gerar e avaliar: cria as 5 populações (aglomerados, sessão repetida, ruído,
#    fora da área e inválidos) pelo mesmo caminho da API, roda o pipeline e compara
#    cada categoria com o destino esperado.
uv run python -m scripts.gerar_dados_sinteticos --limpar --executar-pipeline --avaliar

# 2. Sensibilidade: mede eps ∈ {2, 4, 8, 12, 20} m × min_confirmacoes ∈ {2, 3, 4}.
#    Além do controle, liga por padrão aglomerados de 2 a 5 sessões e 5 sequências
#    de barreiras distintas a 15 m (encadeamento, T5). NÃO TOCA O BANCO: roda tudo
#    numa transação desfeita no fim, e os resultados ficam só no console e no CSV.
#    O banco continua com a simulação do passo 1, então a ordem dos passos não importa.
uv run python -m scripts.analisar_sensibilidade

# 3. Figura do funil (docs/figuras/funil-simulacao.svg e .png), a partir das
#    estatísticas do banco. O matplotlib fica num grupo opcional.
uv sync --group analise
uv run python -m scripts.gerar_figura_funil --origem simulacao
```

- `--limpar` apaga antes todos os dados de simulação. Sem ele, os novos se somam aos
  antigos e a avaliação sai distorcida (o script avisa).
- `--help` lista as opções de geração (`--semente`, `--aglomerados`,
  `--pontos-por-aglomerado`, `--dispersao-metros`, `--sessao-repetida`, `--ruido`,
  `--fora-da-area`, `--invalidos`, `--sessoes-variaveis`, `--sequencias`,
  `--barreiras-por-sequencia`, `--espacamento-sequencia-metros`). A análise de
  sensibilidade aceita as mesmas, com padrões próprios.
- Saídas: tabelas no console e `backend/scripts/saida/simulacao-semente-<N>.json` e
  `sensibilidade-semente-<N>.csv` (não versionados; rode de novo para regerar). Com
  opções fora do padrão, o nome ganha um sufixo (ex.: `-dispersao-metros-10`), e o
  arquivo canônico nunca é sobrescrito.
- Com os padrões (semente 42), o teste de eficácia acerta 100% em cada categoria.
  **Isso confere a implementação, não a robustez:** o cenário é bem separado de
  propósito, e as "0 fusões" do controle acontecem por construção. A robustez está na
  análise de sensibilidade, cujos resultados estão em
  [docs/decisoes-pendentes.md](docs/decisoes-pendentes.md) (#4 e T5).
- No mapa, as barreiras simuladas só aparecem pedindo `origem=simulacao` em
  `GET /barreiras`; o padrão é `real`.

## Marcos

- [x] **M0**: Postgres + PostGIS via Docker Compose
- [x] **M1**: migrations e seeds
- [x] **M2**: `POST /alertas` e `GET /barreiras`
- [x] **M3**: dados sintéticos, pipeline de validação e estatísticas
- [x] **M4**: frontend com mapa (Leaflet/OSM) e envio de alerta
- [x] **M5**: integração ponta a ponta (`docker compose up` único, frontend
      containerizado, `scripts/ponta-a-ponta.sh`)
- [x] **M5.1**: CI/CD — rodou verde no GitHub Actions (banco, backend, frontend e
      ponta a ponta) num push do branch `tcc2`; `publicar-imagens` roda pela primeira
      vez só depois do merge deste branch em `main` ([`docs/ci-cd.md`](docs/ci-cd.md))
- [ ] **M6**: coleta em campo — **preparado**, não realizado. Protocolo, ética/LGPD,
      checklist e o que falta decidir com a equipe/orientadora:
      [`docs/coleta-em-campo.md`](docs/coleta-em-campo.md)
