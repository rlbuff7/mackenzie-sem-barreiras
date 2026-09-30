# Implantação e operação da coleta

Dois roteiros curtos: **§1–§10 para o Victor (infra)**, que sobe a pilha de produção,
o HTTPS e os backups; **§11 para o Maurício (dados)**, que conduz o dia de coleta.
Contexto: [`coleta-em-campo.md`](coleta-em-campo.md) (protocolo, LGPD, HTTPS),
[`ci-cd.md`](ci-cd.md) (de onde vêm as imagens).

**Primeiro dia ou dia seguinte?** A coleta pode durar vários dias, e a URL do túnel
muda a cada subida. O caminho de §2 a §7 (com relato de teste e `zerar-real`) vale
**só uma vez**, antes da PRIMEIRA abertura. Se a coleta já foi aberta alguma vez (dia 2
em diante, máquina reiniciada, túnel que caiu), vá direto ao **§8**: nele não há relato
de teste nem `zerar-real`, porque os relatos reais no banco já são os dados do TCC.

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
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # gera o segredo do "executar"
# no .env DESTA máquina, EDITE a linha TOKEN_ADMIN= que já existe (vem do .env.example):
#   TOKEN_ADMIN=<valor gerado>        (uma linha só; não acrescente uma segunda)
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --wait
```

- `TOKEN_ADMIN` é **obrigatório**, e o compose de produção o exige em **todo** comando,
  não só no `up`: `ps`, `logs`, `stop` e `down` também param com "defina TOKEN_ADMIN"
  se ele não estiver no `.env` nem no shell (o `${TOKEN_ADMIN:?…}` do arquivo é
  avaliado sempre). Por isso ele fica no **`.env` da máquina de produção** (que nunca vai
  para o Git): qualquer terminal novo, o do fim do dia ou o do dia seguinte, já o
  encontra, e o token da API não muda sem ninguém querer.
- Evite `export TOKEN_ADMIN=...`: o valor do shell tem prioridade sobre o `.env`, e um
  `up` feito com outro valor recria a API com outro token. `./db/banco.sh --prod` e
  `./scripts/preparar-coleta.sh` não usam o token (põem um valor de enchimento só para o
  compose aceitar `exec`, `ps` e `logs`).
- Para mandar o token no `executar` sem imprimi-lo na tela:
  `-H "X-Token-Admin: $(sed -n 's/^TOKEN_ADMIN=//p' .env | tail -n 1)"`
  ([`coleta-em-campo.md`](coleta-em-campo.md) §6). O `tail -n 1` pega a mesma linha que
  o compose usa (a última), caso o `.env` tenha ficado com duas.
- Se as duas pilhas rodam no mesmo checkout, a de desenvolvimento lê o mesmo `.env`:
  com o token lá, o `executar` do dev também passa a pedir o header (inofensivo).
- `EXPOR_DOCS` é fixo em `false` na produção: `/api/docs`, `/api/redoc` e
  `/api/openapi.json` respondem 404.
- `IMAGEM_TAG` (padrão `latest`) escolhe a versão das imagens. O CI publica (ver
  `docker/metadata-action` em `.github/workflows/ci-cd.yml`): `latest` a cada push em
  `main`; `sha-<7 primeiros caracteres do commit>` em todo push de `main` ou de tag; e,
  para uma tag `vX.Y.Z` do repositório, `X.Y.Z` e `X.Y` (sem o `v`). Para fixar uma
  versão conhecida: `IMAGEM_TAG=sha-050ec68 docker compose -f docker-compose.prod.yml
  up -d --wait` (ou a linha `IMAGEM_TAG=sha-050ec68` no `.env`, para valer em todo
  comando).
  **Atenção:** `latest` só passa a incluir `EXPOR_DOCS` e os limites de envio depois
  que o branch `fase2` for para `main` e o CI publicar; antes disso, `/api/docs` fica
  aberto mesmo com a variável (o `preparar-coleta.sh` acusa isso).

## 3. Aplicar migrations

```bash
./db/banco.sh --prod migrar        # equivale a COMPOSE_FILE=docker-compose.prod.yml ./db/banco.sh migrar
```

O `--prod` só troca o arquivo do compose; sem ele, `banco.sh` continua falando com a
pilha de desenvolvimento. Vale para `migrar`, `psql`, `backup`, `restaurar` e
`zerar-real`; `testar` e `preparar-teste` recusam `--prod` (§9).
Seeds (tipos e polígono) ficam **congelados** durante a coleta: não rode `migrar` com
`db/seeds/` alterado depois de abrir.

## 4. Checklist inicial

```bash
./scripts/preparar-coleta.sh        # pilha de produção; --dev ensaia na de desenvolvimento
```

Com a pilha recém-criada, tudo deve estar `[ok]` (o banco está vazio, então
`recebidos = 0`) e o túnel aparece como inativo. Confere: `TOKEN_ADMIN` definido,
`EXPOR_DOCS=false` (variável e efeito: `/api/docs` 404), db/api/frontend saudáveis,
migrations aplicadas, funil real zerado, e registra commit, hash dos seeds e as imagens
em execução (referência, ID e RepoDigest do GHCR) em
`backend/scripts/saida/coleta-<pilha>[-reabrir]-<data-hora>.txt` (não versionado; um
arquivo por execução, nenhum sobrescreve o outro). **Só lê e relata**: quando algo falha, sugere o comando, que você
decide rodar. Opções: `--prod` (padrão), `--dev` (ensaio na pilha de desenvolvimento) e
`--reabrir` (coleta já em andamento, §8); qualquer outro argumento dá erro.

Se o item 4 acusar "há N relatos reais, de <data> a <data>" logo nesta primeira
conferência, pare e olhe as datas: relatos de outros dias significam que a coleta já foi
aberta antes, e o caminho certo é o §8, não o `zerar-real`.

## 5. HTTPS sem conta (túnel)

A geolocalização do celular exige HTTPS ([`coleta-em-campo.md`](coleta-em-campo.md) §4).
Sem conta e sem domínio, use o Quick Tunnel da Cloudflare, opcional, no profile `tunel`
(imagem `cloudflare/cloudflared` com versão fixa em `docker-compose.prod.yml`):

```bash
docker compose -f docker-compose.prod.yml --profile tunel up -d --wait
docker compose -f docker-compose.prod.yml logs tunel | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | grep -v '^https://api\.' | tail -1
```

- Só o **frontend** é exposto; a API responde por `/api/` na mesma URL.
- A URL é **aleatória e muda a cada subida**; some quando o túnel cai. Use para coleta
  pontual, não como endereço permanente; avise o grupo a cada nova URL.
- O túnel **não volta sozinho** (`restart: "no"`): depois de reiniciar a máquina ou o
  Docker, ele só sobe de propósito. Nos dias seguintes ao primeiro, use o comando do §8
  (sobe só o túnel, sem recriar a pilha).
- Logo após subir, o nome novo pode levar cerca de 30 s para resolver no DNS: se der
  "não foi possível resolver", espere e tente de novo.
- **Privacidade:** a Cloudflare termina o TLS, então os relatos passam por um terceiro
  (como os tiles do OpenStreetMap, mas com o conteúdo do relato) e ela vê o IP do
  voluntário. O texto de consentimento deve dizer isso
  ([`coleta-em-campo.md`](coleta-em-campo.md) §3).
- Serviço gratuito, sem garantia de disponibilidade, sujeito aos termos da Cloudflare
  (uso justo; não é para tráfego pesado). O limite de envio do nginx é coletivo atrás
  do túnel (ver comentário em `frontend/nginx.conf`).
- **Só abra o túnel depois do checklist do §4 sem falhas** (a pilha já obriga
  `TOKEN_ADMIN`). Derrube ao fim do dia (§10).
- Alternativas com conta: túnel nomeado da Cloudflare (URL fixa em domínio seu) ou uma
  hospedagem com HTTPS de fábrica. Não implementadas; ver `coleta-em-campo.md` §4.

## 6. Testar no celular (só no primeiro dia)

1. Com o túnel no ar, abra a URL `https://….trycloudflare.com` no celular (dados móveis,
   fora do wifi de casa, para provar que é público).
2. Toque em "Usar minha localização": o navegador deve **pedir permissão** (com HTTP
   simples o botão falharia).
3. Envie um relato de teste **dentro do círculo do campus**. Isso deixa
   `recebidos > 0` no banco real; o próximo passo remove.

Este teste com envio só existe **antes da primeira abertura**. Depois dela, todo envio
pela URL é um relato real, que fica no funil do TCC.

## 7. Limpar o teste e abrir a coleta (só antes da PRIMEIRA abertura)

Primeiro, só backup e conferência (nada é apagado aqui):

```bash
./db/banco.sh --prod backup                                  # por segurança, antes de apagar
./db/banco.sh --prod zerar-real                              # só mostra: contagens, quantos relatos e de quando
```

Leia a linha `relatos reais: N (...), de <data> a <data>` que o `zerar-real` imprimiu:
tem de ser só o teste que você acabou de fazer (poucos relatos, de hoje, de minutos
atrás). Se aparecer qualquer relato de outro dia, **pare**: a coleta já foi aberta antes,
esses relatos são dados do TCC, e o caminho certo é o §8. O `zerar-real` vale só neste
momento, uma vez. Só então, num comando separado (este bloco não vai junto do anterior
de propósito):

```bash
./db/banco.sh --prod zerar-real --sim-apagar-dados-reais     # remove os relatos de teste
./scripts/preparar-coleta.sh                                 # agora tem de estar tudo verde
```

Só com o checklist todo `[ok]` (e a URL do túnel impressa) entregue a URL ao Maurício
(§11): a coleta está aberta. A partir daqui, nunca mais `zerar-real` nesta pilha.

## 8. Reabrir a coleta (dia 2 em diante, ou o túnel caiu)

Use sempre que a coleta **já foi aberta** e precisa voltar ao ar: no começo de cada dia
seguinte, depois de reiniciar a máquina ou o Docker, ou quando o túnel cai no meio do dia
(a URL muda a cada subida). Aqui **não** há relato de teste pelo celular e **nunca**
`zerar-real`: os relatos reais no banco são os dados do TCC.

```bash
cd ~/projetos/mackenzie-sem-barreiras                          # o checkout da máquina de produção
docker compose -f docker-compose.prod.yml ps                   # 1. db, api e frontend "healthy"?
docker compose -f docker-compose.prod.yml --profile tunel up -d --wait --no-deps tunel   # 2. só o túnel: URL nova
./scripts/preparar-coleta.sh --reabrir                         # 3. confere tudo e imprime a URL nova
```

1. **A pilha continua de pé.** db, api e frontend voltam sozinhos quando a máquina ou o
   Docker reiniciam (`restart: unless-stopped`), com o mesmo token de antes. Se o `ps`
   mostrar algum fora do ar, suba com `docker compose -f docker-compose.prod.yml up -d
   --wait`, com o `TOKEN_ADMIN` do `.env` (§2): nunca com um token novo, e nunca com
   `down -v` (que apaga o volume). Se o `ps` responder "defina TOKEN_ADMIN", o token não
   está no `.env` da máquina: veja o §2 antes de seguir. Não rode `pull` no meio da
   coleta: uma imagem nova mudaria o código que recebe os relatos entre um dia e outro
   (para fixar a versão, `IMAGEM_TAG` no `.env`, §2).
2. **Suba só o túnel.** O `--no-deps` garante que subir o túnel não recria nada da pilha.
   Se o container do túnel ainda estiver rodando mas a URL parou de responder, o `up` não
   faz nada: use `docker compose -f docker-compose.prod.yml --profile tunel restart tunel`
   (a URL muda do mesmo jeito).
3. **Confira com `--reabrir`.** Nesse modo o item 4 só informa
   "coleta em andamento: N relatos reais, de <data> a <data>" e nunca sugere apagar nada.
   Compare o N com o do fim do dia anterior: o `coleta-prod-reabrir-<data de ontem>-*.txt`
   mais recente em `backend/scripts/saida/`, gravado no passo 5 de ontem (**não** o que
   este passo 3 acabou de gravar, que é o de hoje), e os números que o Maurício anotou
   (§11). O N só pode ter subido ou ficado igual.
   Se o banco estiver sem nenhum relato real, o item 4 **falha** e o script não dá
   PRONTO: o banco pode ter sido recriado (volume perdido). **Pare**, restaure o backup
   `prod-*.dump` do último dia (§9) e rode o `--reabrir` de novo antes de abrir. (Única
   exceção: a coleta foi aberta e o túnel caiu antes do primeiro relato; aí rode
   `./scripts/preparar-coleta.sh` sem `--reabrir`, que aceita `recebidos = 0`.)
   O `PRONTO para reabrir` e a URL impressa são o sinal verde.
4. **Passe a URL nova ao Maurício** (e ao grupo). Ele confere abrindo o mapa no celular,
   sem enviar relato.
5. **No fim do dia:** `./scripts/preparar-coleta.sh --reabrir` de novo (o registro guarda
   quantos relatos reais o dia terminou com), backup (`./db/banco.sh --prod backup`, §9) e
   túnel derrubado (§10). No fim do PRIMEIRO dia, faça o mesmo: é esse registro que o
   dia 2 compara.

## 9. Backup e restauração

```bash
./db/banco.sh --prod backup        # backups/prod-<banco>-<data-hora>.dump (formato -Fc)
./db/banco.sh --prod restaurar backups/prod-ARQUIVO.dump --sim-substituir-banco
```

- **O nome diz de onde o backup veio:** `<pilha>-<banco>-<data-hora>.dump`, com pilha
  `prod` (`--prod`), `dev` (desenvolvimento) ou `teste` (`--teste`). O `backup` imprime
  antes a linha "Alvo:" (banco e pilha); confira que é a de produção.
- Faça backup **antes** de abrir a coleta, **ao fim de cada dia** e **depois** do
  último `executar`. A pasta `backups/` é ignorada pelo Git: os dumps contêm dados de
  voluntários ([`coleta-em-campo.md`](coleta-em-campo.md) §3); guarde-os em local
  privado, não em pasta pública. O `backup` roda com `umask 077`: o dump nasce legível
  só pelo seu usuário (600), e a pasta, se for criada por ele, também (700).
- `restaurar` valida o arquivo (`pg_restore --list`; recusa `.parcial`), restaura num
  banco temporário e só então troca pelo banco alvo: um dump ruim aborta com o banco
  original intacto. Sem o argumento literal `--sim-substituir-banco` ele só explica e sai.
- **Pilha diferente é recusada.** O `restaurar` mostra de que pilha o arquivo veio (pelo
  nome) e, se ela não for a do alvo (ex.: um `dev-….dump` na produção) ou se o nome não
  disser (backups antigos, sem o prefixo), recusa e sai sem mudar nada. Só segue com
  mais um argumento literal, `--sim-pilha-diferente`, para quando isso é de propósito
  (ex.: ensaiar no banco de teste um backup da produção).
- **Na produção, o banco anterior nunca é apagado.** Depois da troca, o `--prod` guarda o
  banco de antes como `<banco>_antigo_<data-hora>` (fechado para conexões) e imprime como
  apagá-lo: confira o restaurado (`./scripts/preparar-coleta.sh --reabrir`, contagens) e
  só então, no `./db/banco.sh --prod psql`, `DROP DATABASE <banco>_antigo_<data-hora>;`.
  Fora da produção o anterior é apagado no fim, como antes.
- **Restaurar em `--prod` derruba as conexões da API por instantes** (entre as duas
  trocas de nome, `ALLOW_CONNECTIONS` fica desligado no banco atual): faça antes de
  abrir a coleta ou com o frontend parado. Se a troca for interrompida (Ctrl-C, erro),
  o script devolve o banco original; se nem isso der, imprime o SQL para recuperar à mão
  (os dados ficam em `<banco>_antigo_<data-hora>`).
- **Não interrompa um `restaurar` em andamento.** Um sinal (Ctrl-C) durante um
  `docker compose exec` só dispara a reversão depois que o processo filho termina,
  então interromper não é livre de corrida. Se acontecer, siga o SQL de recuperação
  que o script imprime.
- As mensagens de recusa de `restaurar` e `zerar-real` mostram o alvo em palavras e o
  comando completo, já com `--prod`/`--teste`: confira o "Alvo:" antes de copiar.
- Ensaie no banco de teste, sem `--prod`: `./db/banco.sh --teste backup` e
  `./db/banco.sh --teste restaurar backups/teste-ARQUIVO.dump --sim-substituir-banco`
  (`--teste` aponta para `<POSTGRES_DB>_teste`; crie-o antes com
  `./db/banco.sh preparar-teste`, na pilha de desenvolvimento).
- Opções de `banco.sh` (antes do subcomando): `--prod` vale para `migrar`, `psql`,
  `backup`, `restaurar` e `zerar-real`. `testar` e `preparar-teste` **recusam** `--prod`:
  os testes de schema gravam (e desfazem) dados, que disputariam com a coleta, e não se
  cria banco de teste no servidor de produção. `--teste` (banco `<POSTGRES_DB>_teste`)
  vale para `psql`, `testar`, `backup`, `restaurar` e `zerar-real`. Testes de segurança
  do script: `./db/tests/banco_sh_seguranca.sh`.

## 10. Derrubar (fim do dia)

No fim de cada dia de coleta, depois do registro e do backup (§8, passo 5), derrube o
túnel. Num terminal novo não há nada a exportar: o token está no `.env` (§2).

```bash
cd ~/projetos/mackenzie-sem-barreiras
docker compose -f docker-compose.prod.yml --profile tunel stop tunel      # só o túnel: fim do dia
docker compose -f docker-compose.prod.yml --profile tunel ps              # confira: o tunel não aparece mais
```

A pilha (db, api, frontend) pode ficar de pé entre um dia e outro: sem o túnel, ela só
escuta em `127.0.0.1`. No dia seguinte, reabra pelo §8. No fim da coleta inteira:

```bash
docker compose -f docker-compose.prod.yml --profile tunel down            # para tudo, MANTÉM os dados
```

O `--profile tunel` faz o `down` remover também o container do túnel e a rede. Nunca
deixe o túnel no ar fora da janela de coleta.

Apagar também o volume (o banco com os relatos) é outro comando, de propósito fora do
bloco acima: só depois do último `executar`, com o backup final conferido (§9) e guardado
fora da máquina, e só se for descartar a instalação:
`docker compose -f docker-compose.prod.yml --profile tunel down -v`.

Se um comando parar com "defina TOKEN_ADMIN", o token não está no `.env` desta máquina.
Para `stop`, `ps`, `logs` e `down`, que não recriam a API, qualquer valor serve
(`TOKEN_ADMIN=x docker compose -f docker-compose.prod.yml --profile tunel stop tunel`).
Nunca faça isso com `up`: ele recriaria a API com o token errado. Grave o token no
`.env` (§2) antes do próximo `up`.

---

## 11. Dia de coleta (Maurício, dados)

Este é o resumo; o protocolo completo (voluntários, tipos, LGPD) está em
[`coleta-em-campo.md`](coleta-em-campo.md).

1. **Antes:** no primeiro dia, peça ao Victor o "PRONTO" do segundo
   `scripts/preparar-coleta.sh` (§7); nos dias seguintes (ou quando o túnel cair), o
   "PRONTO para reabrir" do `--reabrir` (§8). Nos dois casos, peça a URL pública do dia e
   confira você mesmo abrindo a URL num celular e vendo o mapa, sem enviar relato.
2. **Distribua** a URL e o roteiro dos voluntários (`coleta-em-campo.md` §2): reportar
   do local, com a localização ligada, tipo mais específico. Relatos fora do círculo do
   campus são descartados de propósito (não é erro).
3. **Durante:** acompanhe o funil em `<URL>/api/validacao/estatisticas?origem=real`
   (`recebidos` deve subir). URL mudou (túnel caiu)? Peça a nova ao Victor e reenvie.
4. **Ao fim:** peça ao Victor o backup do dia (§9) e o `executar` com o token
   (`coleta-em-campo.md` §6); depois confira o funil de novo e anote os números (o
   `recebidos` do dia seguinte só pode ser maior ou igual).
5. **Nunca** apague dados reais nem rode `migrar` com seeds alterados durante a coleta.
   Se alguém sugerir `zerar-real` depois da primeira abertura, a resposta é não: reabrir é
   o §8. Dados de simulação **não** entram nos números da coleta.
