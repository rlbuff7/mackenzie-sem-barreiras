#!/bin/bash
# Prepara uma instância Ubuntu 24.04 (amd64) para rodar o protótipo do TCC:
# Docker Engine + plugin compose, git, python3 e Caddy (repositório oficial).
# Serve como user-data da EC2 (roda como root, uma vez) ou à mão: sudo bash preparar-maquina.sh
# Não contém segredo nenhum. Idempotente: pode rodar de novo sem estragar nada.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y ca-certificates curl gnupg git python3 debian-keyring debian-archive-keyring apt-transport-https

install -m 0755 -d /etc/apt/keyrings

# Docker Engine (repositório oficial da Docker)
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

# Caddy (repositório oficial do Caddy)
if [ ! -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg ]; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
fi
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin caddy

systemctl enable --now docker
usermod -aG docker ubuntu || true

# O Caddy sobe sozinho quando a máquina religa; o Caddyfile é escrito depois (deploy/aws/Caddyfile.exemplo).
systemctl enable caddy

touch /var/lib/preparar-maquina.ok
