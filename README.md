# Mackenzie sem Barreiras

Mapeamento colaborativo de acessibilidade urbana no entorno da Universidade
Presbiteriana Mackenzie. TCC, FCI/Mackenzie.

Voluntários reportam barreiras físicas num mapa web. O sistema filtra, agrupa e
valida os reports antes de persistir em banco espacial (PostgreSQL + PostGIS).

Contexto completo do projeto, decisões e convenções: [CLAUDE.md](CLAUDE.md).
Pontos em aberto: [docs/decisoes-pendentes.md](docs/decisoes-pendentes.md).

## Estrutura

```
db/          migrations e seeds SQL
backend/     API FastAPI e camada de validação (backend/app/validacao/)
frontend/    mapa web (TypeScript + Leaflet)
docs/        decisões pendentes e documentos acadêmicos (docs/academico/)
```

## Rodando localmente

Pré-requisito: Docker com Compose v2. Nada é instalado direto na máquina.

```bash
cp .env.example .env      # primeira vez; troque a senha
docker compose up -d --wait
./db/banco.sh migrar      # cria as tabelas e carrega os seeds
./db/banco.sh testar      # confere tabelas, constraints e seeds
```

O `migrar` pode ser rodado quantas vezes quiser: só aplica as migrations novas
e atualiza os seeds.

Conectar ao banco: `./db/banco.sh psql`, ou de um cliente gráfico (DBeaver,
pgAdmin) em `localhost:5434`, com usuário e senha do `.env`.

Parar sem perder dados: `docker compose down`.
Apagar o banco e recomeçar do zero: `docker compose down -v`, depois `up` e
`migrar` de novo.

## Marcos

- [x] **M0**: Postgres + PostGIS via Docker Compose
- [x] **M1**: migrations e seeds
- [ ] **M2**: `POST /alertas` e `GET /barreiras`
- [ ] **M3**: dados sintéticos, pipeline de validação e estatísticas
- [ ] **M4**: frontend com mapa
- [ ] **M5**: integração ponta a ponta
- [ ] **M6**: coleta em campo
