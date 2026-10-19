#!/usr/bin/env bash
# Instala (ou remove) o timer systemd de auto-atualização no servidor. Idempotente.
#   sudo ./deploy/aws/instalar-auto-atualizacao.sh            instala e liga o timer
#   sudo ./deploy/aws/instalar-auto-atualizacao.sh --remover  desliga e apaga as unidades
# Variáveis: USUARIO (padrão: quem chamou o sudo, ou ubuntu), REPO (padrão: raiz deste
# checkout). Não toca no .env nem nos contêineres.
set -euo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "erro: rode com sudo" >&2; exit 1; }
aqui="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${REPO:-$(cd "$aqui/../.." && pwd)}"
usuario="${USUARIO:-${SUDO_USER:-ubuntu}}"
destino=/etc/systemd/system

if [[ "${1:-}" == "--remover" ]]; then
    systemctl disable --now msb-atualizar.timer 2>/dev/null || true
    rm -f "$destino/msb-atualizar.service" "$destino/msb-atualizar.timer"
    systemctl daemon-reload
    echo "auto-atualização removida"
    exit 0
fi

command -v flock >/dev/null || { echo "erro: flock (util-linux) ausente" >&2; exit 1; }
[[ -f "$repo/deploy/aws/atualizar-se-mudou.sh" ]] || { echo "erro: $repo não parece o repositório" >&2; exit 1; }
id "$usuario" >/dev/null
id -nG "$usuario" | tr ' ' '\n' | grep -qx docker || { echo "erro: $usuario não está no grupo docker" >&2; exit 1; }

for u in msb-atualizar.service msb-atualizar.timer; do
    sed -e "s|@USUARIO@|$usuario|g" -e "s|@REPO@|$repo|g" "$aqui/$u" >"$destino/$u"
    chmod 644 "$destino/$u"
done
systemctl daemon-reload
systemctl enable --now msb-atualizar.timer
systemctl list-timers msb-atualizar.timer --no-pager
