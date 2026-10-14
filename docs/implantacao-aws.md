# Implantação na AWS (Learner Lab)

Passo a passo para subir, operar e apagar o protótipo na AWS Academy Learner Lab do
Rodrigo. A pilha em si (compose de produção, `TOKEN_ADMIN`, backup) está em
[`implantacao.md`](implantacao.md); aqui fica só o que é da AWS.

Estado de 14/10/2026: uma instância `t3.small` (Ubuntu 24.04, disco gp3 de 20 GB), um
Elastic IP, um grupo de segurança e uma chave SSH, todos com as tags
`Name=tcc-navegacao` e `Projeto=tcc-navegacao`. HTTPS por Caddy no nome
`<ip-com-hífens>.sslip.io`. Os IDs e o endereço atual estão em
`.claude/agent-memory/aws-implantacao/MEMORY.md`.

## 1. A cada sessão do lab

O lab dura 4 h. Quando acaba, a instância **para** (o Elastic IP e o disco ficam; a pilha
volta sozinha quando a instância religa).

1. No AWS Academy, abra o Learner Lab e clique em **Start Lab**; espere a bolinha ficar
   verde.
2. **AWS Details** > **AWS CLI: Show** > copie o bloco e cole em
   `~/.aws/credentials` (no WSL é um link para `C:\Users\Rodrigo lucas\.aws\credentials`).
   As credenciais mudam a cada sessão: sem isso, a CLI responde `ExpiredToken`.
3. Confira: `aws sts get-caller-identity`. Sem AWS CLI instalada, use a imagem Docker
   (região `us-east-1` no `config`):

   ```bash
   alias aws='docker run --rm -v "/mnt/c/Users/Rodrigo lucas/.aws":/root/.aws:ro -v "$PWD":/aws amazon/aws-cli'
   ```

4. Se a instância estiver parada, ligue:
   `aws ec2 start-instances --instance-ids <id>` (ou pelo console, EC2 > Instances).
   O Elastic IP continua o mesmo, então o endereço HTTPS não muda. Dê 1 a 2 minutos
   para a pilha subir e confira `https://<host>/api/saude`.

## 2. Criar tudo do zero (só se a infra tiver sido apagada)

Os recursos são 1 instância, 1 volume, 1 Elastic IP, 1 grupo de segurança e 1 chave.
Todos com as tags `Name=tcc-navegacao` e `Projeto=tcc-navegacao`.

1. **Chave SSH** (a privada nunca vai para o Git):

   ```bash
   aws ec2 create-key-pair --key-name tcc-navegacao --key-type ed25519 \
     --query KeyMaterial --output text > ~/.ssh/tcc-navegacao.pem
   chmod 600 ~/.ssh/tcc-navegacao.pem
   ```

2. **Grupo de segurança** na VPC padrão: 22 só do seu IP (`curl -s https://checkip.amazonaws.com`),
   80 e 443 de qualquer lugar. Nenhuma outra porta: banco e API ficam em `127.0.0.1`.
3. **Instância**: `t3.small`, Ubuntu 24.04 amd64 (AMI pelo parâmetro público
   `/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id`),
   disco gp3 de 20 GB e `--user-data file://deploy/aws/preparar-maquina.sh` (instala
   Docker, compose, git, python3 e Caddy).
4. **Elastic IP**: `allocate-address`, `associate-address`, com as tags.
5. **Na máquina** (`ssh -i ~/.ssh/tcc-navegacao.pem ubuntu@<ip>`):

   ```bash
   git clone https://github.com/rlbuff7/mackenzie-sem-barreiras.git && cd mackenzie-sem-barreiras
   cp .env.example .env && chmod 600 .env
   # edite POSTGRES_PASSWORD e TOKEN_ADMIN com valores gerados AQUI:
   #   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   # e ponha EXPOR_DOCS=false
   docker compose -f docker-compose.prod.yml pull
   docker compose -f docker-compose.prod.yml up -d --wait
   ./db/banco.sh --prod migrar
   ```

6. **Caddy**: copie `deploy/aws/Caddyfile.exemplo` para `/etc/caddy/Caddyfile`, troque o
   nome pelo IP com hífens (`203.0.113.7` vira `203-0-113-7.sslip.io`), depois
   `sudo systemctl restart caddy`. O certificado do Let's Encrypt sai em segundos.
7. **Conferir de fora**: `https://<host>/medicao.html` responde 200, `/api/saude` responde
   `{"status":"ok","banco":"ok"}` e `/api/docs` responde 404.

## 3. Entrar na máquina

```bash
ssh -i ~/.ssh/tcc-navegacao.pem ubuntu@<ip-elastico>
```

- A regra de SSH do grupo de segurança vale **só para o IP público que você tinha ao criá-la**.
  Se o seu IP mudou (`Connection timed out`), troque a regra:

  ```bash
  aws ec2 revoke-security-group-ingress --group-id <sg> --protocol tcp --port 22 --cidr <ip-antigo>/32
  aws ec2 authorize-security-group-ingress --group-id <sg> --protocol tcp --port 22 \
    --cidr "$(curl -s https://checkip.amazonaws.com)/32"
  ```

- O `TOKEN_ADMIN` e a senha do banco estão só no `~/mackenzie-sem-barreiras/.env` da máquina
  (permissão 600). Para usar o token sem imprimi-lo:
  `-H "X-Token-Admin: $(sed -n 's/^TOKEN_ADMIN=//p' .env | tail -n 1)"`.

## 4. Deploy manual de uma versão nova

O CI não consegue entrar na AWS com credenciais do lab (mudam a cada sessão), então o
deploy é manual, depois que o CI publicou as imagens no GHCR:

```bash
ssh -i ~/.ssh/tcc-navegacao.pem ubuntu@<ip-elastico>
cd ~/mackenzie-sem-barreiras
git pull
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --wait
./db/banco.sh --prod migrar
```

Nunca `down -v` (apaga o volume do banco). Confira depois `/api/saude` por HTTPS.

## 5. Backup do banco

A conta do Learner Lab some quando o curso acaba, e o disco só existe lá: o backup tem de
ficar **fora da AWS**.

```bash
# na máquina
cd ~/mackenzie-sem-barreiras && ./db/banco.sh --prod backup      # grava em backups/, na raiz do repositório
# no WSL, copiando para fora da máquina
scp -i ~/.ssh/tcc-navegacao.pem 'ubuntu@<ip-elastico>:mackenzie-sem-barreiras/backups/*' ~/backups-tcc/
```

Faça antes de qualquer mudança de migration e antes do fim do curso. Restaurar:
`./db/banco.sh --prod restaurar backups/<arquivo> --sim-substituir-banco` (ver [`implantacao.md`](implantacao.md)).

## 6. Custo (conferido em 14/10/2026)

Orçamento do lab: US$ 50. Preços de us-east-1, aproximados:

| Item | Por hora | Observação |
|---|---|---|
| EC2 `t3.small` | US$ 0,0208 | só enquanto a instância estiver ligada |
| Disco gp3 20 GB | US$ 0,0022 | cobra ligado ou parado |
| Elastic IP (IPv4 público) | US$ 0,005 | cobra associado ou solto |
| **Total ligada** | **~US$ 0,028** | ~US$ 0,67 por dia, ~US$ 20 por 30 dias |
| **Total parada** | ~US$ 0,007 | disco + Elastic IP |

Como a sessão do lab dura 4 h e a instância para sozinha ao fim, o gasto real fica abaixo
do "sempre ligada". Veja o saldo na página do Learner Lab (**AWS Details**, "Cost").
Os dados de transferência para fora (15 GB de graça por mês) não devem pesar neste uso.

## 7. Limites do Learner Lab

- Só a região `us-east-1`.
- Não dá para criar usuários, grupos ou papéis IAM; só o papel `voclabs`.
- Tipos de instância pequenos (use `t3.small`); alguns serviços são bloqueados.
- A sessão dura 4 h; ao fim as instâncias param. Credenciais temporárias (vão em
  `~/.aws/credentials`, nunca no repositório).
- O CI não deploya (credenciais mudam a cada sessão): deploy manual, §4.
- A conta some quando o curso acaba: tenha backup fora da AWS (§5) e o túnel
  Cloudflare como plano B ([`implantacao.md`](implantacao.md) §5).
- O IP de quem usa o protótipo chega à AWS (e ao Let's Encrypt só o nome do site):
  está no termo de consentimento.

## 8. Apagar tudo pela tag

Ordem importa (o grupo de segurança só sai depois da instância):

```bash
aws ec2 describe-instances --filters Name=tag:Projeto,Values=tcc-navegacao \
  --query 'Reservations[].Instances[].InstanceId' --output text
aws ec2 terminate-instances --instance-ids <id>             # o disco de 20 GB vai junto
aws ec2 wait instance-terminated --instance-ids <id>
aws ec2 describe-addresses --filters Name=tag:Projeto,Values=tcc-navegacao \
  --query 'Addresses[].AllocationId' --output text
aws ec2 release-address --allocation-id <eipalloc-...>
aws ec2 delete-security-group --group-id <sg-...>
aws ec2 delete-key-pair --key-name tcc-navegacao && rm ~/.ssh/tcc-navegacao.pem
```

Depois confira que não sobrou nada: `describe-instances`, `describe-volumes`,
`describe-addresses` e `describe-security-groups` filtrando pela tag `Projeto=tcc-navegacao`
devem voltar vazios. Faça o backup (§5) antes.
