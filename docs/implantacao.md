# Implantação e operação da coleta

Dois roteiros curtos: **§1–§8 para o Victor (infra)**, que sobe a pilha de produção,
o HTTPS e os backups; **§9 para o Maurício (dados)**, que conduz o dia de coleta.
Contexto: [`coleta-em-campo.md`](coleta-em-campo.md) (protocolo, LGPD, HTTPS),
[`ci-cd.md`](ci-cd.md) (de onde vêm as imagens).

A pilha de produção (`docker-compose.prod.yml`) usa as imagens **já publicadas** no
GHCR, sem build. É separada da de desenvolvimento: projeto
`mackenzie-sem-barreiras-prod`, volume `pgdata_prod`, portas só em `127.0.0.1`
(`POSTGRES_PORTA_PROD` 5435, `API_PORTA_PROD` 8010, `FRONTEND_PORTA_PROD` 8091).
As duas podem rodar ao mesmo tempo.

---

## 1. Pré-requisitos (Victor)

- Docker com Compose v2 e o repositório clonado (ver README, "Onde clonar").
- `.env` criado (`cp .env.example .env`) com senha do banco trocada.
- As imagens são públicas: `docker pull` funciona sem login.

## 2. Subir a pilha de produção

```bash
export TOKEN_ADMIN="$(openssl rand -hex 24)"   # guarde: é o segredo do "executar"
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --wait
```

- `TOKEN_ADMIN` é **obrigatório**: sem ele o compose recusa subir. Precisa estar no
  shell em todo comando `docker compose -f docker-compose.prod.yml ...` que recria a
  API (ou no `.env`, se preferir; o do shell tem prioridade).
- `EXPOR_DOCS` é fixo em `false` na produção: `/api/docs`, `/api/redoc` e
  `/api/openapi.json` respondem 404.
- `IMAGEM_TAG` (padrão `latest`) escolhe a versão das imagens: um sha curto do commit
  ou `vX.Y.Z` fixa uma versão conhecida (`IMAGEM_TAG=ab12cd3 docker compose ...`).
  **Atenção:** `latest` só passa a incluir `EXPOR_DOCS` e os limites de envio depois
  que o branch `fase2` for para `main` e o CI publicar; antes disso, `/api/docs` fica
  aberto mesmo com a variável (o `preparar-coleta.sh` acusa isso).

## 3. Aplicar migrations

```bash
./db/banco.sh --prod migrar        # equivale a COMPOSE_FILE=docker-compose.prod.yml ./db/banco.sh migrar
```

O `--prod` só troca o arquivo do compose; sem ele, `banco.sh` continua falando com a
pilha de desenvolvimento. Vale para todos os comandos (`psql`, `testar`, `backup`...).
Seeds (tipos e polígono) ficam **congelados** durante a coleta: não rode `migrar` com
`db/seeds/` alterado depois de abrir.

## 4. HTTPS sem conta (túnel)

A geolocalização do celular exige HTTPS ([`coleta-em-campo.md`](coleta-em-campo.md) §4).
Sem conta e sem domínio, use o Quick Tunnel da Cloudflare, opcional, no profile `tunel`:

```bash
docker compose -f docker-compose.prod.yml --profile tunel up -d --wait
docker compose -f docker-compose.prod.yml logs tunel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

- Só o **frontend** é exposto; a API responde por `/api/` na mesma URL.
- A URL é **aleatória e muda a cada subida**; some quando o túnel cai. Use para coleta
  pontual, não como endereço permanente; avise o grupo a cada nova URL.
- Logo após subir, o nome novo pode levar cerca de 30 s para resolver no DNS: se der
  "não foi possível resolver", espere e tente de novo.
- Serviço gratuito, sem garantia de disponibilidade, sujeito aos termos da Cloudflare
  (uso justo; não é para tráfego pesado). O limite de envio do nginx é coletivo atrás
  do túnel (ver comentário em `frontend/nginx.conf`).
- **Só abra o túnel com `TOKEN_ADMIN` definido** (a pilha já obriga) e com o
  `preparar-coleta.sh` sem falhas. Derrube ao fim do dia (§8).
- Alternativas com conta: túnel nomeado da Cloudflare (URL fixa em domínio seu) ou uma
  hospedagem com HTTPS de fábrica. Não implementadas; ver `coleta-em-campo.md` §4.

## 5. Testar no celular

1. Com o túnel no ar, abra a URL `https://….trycloudflare.com` no celular (dados móveis,
   fora do wifi de casa, para provar que é público).
2. Toque em "Usar minha localização": o navegador deve **pedir permissão** (com HTTP
   simples o botão falharia).
3. Envie um relato de teste **dentro do círculo do campus**. Depois, apague os dados de
   teste antes de abrir a coleta (§6, `zerar-real`), ou faça este teste numa pilha
   descartável (`down -v` em seguida).

## 6. Checklist antes de abrir a coleta

```bash
./scripts/preparar-coleta.sh        # pilha de produção; use --dev para ensaiar na de dev
```

Confere: `TOKEN_ADMIN` definido, `EXPOR_DOCS=false` (variável e efeito: `/api/docs`
404), db/api/frontend saudáveis, migrations aplicadas, funil real com `recebidos = 0`,
e registra o commit e o hash dos seeds em `backend/scripts/saida/coleta-<data>.txt`
(não versionado). Imprime a URL do túnel se ele estiver no ar. **Só lê e relata**:
quando algo falha, sugere o comando, que você decide rodar. Se sobrou dado de teste:

```bash
./db/banco.sh --prod backup                       # antes de qualquer apagamento
./db/banco.sh --prod zerar-real                   # só mostra as contagens
./db/banco.sh --prod zerar-real --sim-apagar-dados-reais
```

## 7. Backup e restauração

```bash
./db/banco.sh --prod backup        # backups/<banco>-<data-hora>.dump (formato -Fc)
./db/banco.sh --prod restaurar backups/ARQUIVO.dump --sim-substituir-banco
```

- Faça backup **antes** de abrir a coleta, **ao fim de cada dia** e **depois** do
  último `executar`. A pasta `backups/` é ignorada pelo Git: os dumps contêm dados de
  voluntários ([`coleta-em-campo.md`](coleta-em-campo.md) §3); guarde-os em local
  privado, não em pasta pública.
- `restaurar` **apaga o banco alvo** e o recria a partir do dump; sem o argumento
  literal `--sim-substituir-banco` ele só explica e sai. Ensaie a restauração no banco
  de teste (`BANCO_ALVO=${POSTGRES_DB}_teste ./db/banco.sh backup`) antes de precisar
  dela de verdade.

## 8. Derrubar

```bash
docker compose -f docker-compose.prod.yml --profile tunel stop tunel   # só o túnel
docker compose -f docker-compose.prod.yml down                          # para tudo, MANTÉM os dados
docker compose -f docker-compose.prod.yml down -v                       # APAGA o volume: só com backup em mãos
```

Sem `--profile tunel` o `down` não enxerga o container do túnel; use o perfil se ele
estiver ativo. Nunca deixe o túnel no ar fora da janela de coleta.

---

## 9. Dia de coleta (Maurício, dados)

Este é o resumo; o protocolo completo (voluntários, tipos, LGPD) está em
[`coleta-em-campo.md`](coleta-em-campo.md).

1. **Antes:** peça ao Victor a confirmação "PRONTO" do `scripts/preparar-coleta.sh` e a
   URL pública do dia. Confira você mesmo abrindo a URL num celular e vendo o mapa.
2. **Distribua** a URL e o roteiro dos voluntários (`coleta-em-campo.md` §2): reportar
   do local, com a localização ligada, tipo mais específico. Relatos fora do círculo do
   campus são descartados de propósito (não é erro).
3. **Durante:** acompanhe o funil em `<URL>/api/validacao/estatisticas?origem=real`
   (`recebidos` deve subir). URL mudou (túnel caiu)? Peça a nova ao Victor e reenvie.
4. **Ao fim:** peça ao Victor o backup do dia (§7) e o `executar` com o token
   (`coleta-em-campo.md` §6); depois confira o funil de novo e anote os números.
5. **Nunca** apague dados reais nem rode `migrar` com seeds alterados durante a coleta.
   Dados de simulação **não** entram nos números da coleta.
