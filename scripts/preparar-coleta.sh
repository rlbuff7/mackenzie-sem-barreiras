#!/usr/bin/env bash
# Checklist executável ANTES de abrir a coleta em campo (docs/implantacao.md §7,
# docs/coleta-em-campo.md §5). SÓ LÊ E RELATA: nunca apaga nem altera dado, nunca
# sobe ou derruba nada; quando algo falha, sugere o comando (sem executá-lo).
#
#   ./scripts/preparar-coleta.sh          confere a pilha de PRODUÇÃO (docker-compose.prod.yml)
#   ./scripts/preparar-coleta.sh --dev    confere a pilha de desenvolvimento (para ensaio)
#
# Confere: TOKEN_ADMIN definido e EXPOR_DOCS=false (lidos do container da API, o
# que de fato vale), serviços saudáveis, migrations aplicadas, funil real
# zerado (recebidos = 0), e registra commit + hash dos seeds em
# backend/scripts/saida/coleta-<data>.txt (não versionado). Se o profile `tunel`
# estiver ativo, imprime a URL pública lida dos logs do cloudflared.
# Sai com código 1 se algum item falhou.
set -uo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

if [[ ! -f .env ]]; then
    echo "erro: .env não encontrado. Rode: cp .env.example .env" >&2
    exit 1
fi
set -a; source .env; set +a   # .env é só configuração; o container é a fonte da verdade abaixo

if [[ "${1:-}" == "--dev" ]]; then
    arquivo_compose=docker-compose.yml
    porta_frontend="${FRONTEND_PORTA_HOST:-8081}"
    rotulo="desenvolvimento"
    flag_prod=""
else
    arquivo_compose=docker-compose.prod.yml
    porta_frontend="${FRONTEND_PORTA_PROD:-8091}"
    rotulo="produção"
    flag_prod="--prod "
    # O compose de produção interpola TOKEN_ADMIN mesmo para ps/exec/logs.
    export TOKEN_ADMIN="${TOKEN_ADMIN:-nao-usado-por-este-script}"
fi
export COMPOSE_FILE="$arquivo_compose"
url_base="http://127.0.0.1:${porta_frontend}"   # pelo frontend: confere o proxy /api/ também

falhas=0
relatorio=()
ok()    { echo "  [ok]     $1"; relatorio+=("ok     $1"); }
falha() { echo "  [FALHA]  $1"; relatorio+=("FALHA  $1"); [[ -n "${2:-}" ]] && echo "           sugestão: $2"; falhas=$((falhas + 1)); }
info()  { echo "  [info]   $1"; relatorio+=("info   $1"); }

echo "== preparar-coleta: pilha de $rotulo ($arquivo_compose) =="

echo "1. Configuração efetiva da API (lida do container)"
if token_no_container="$(docker compose exec -T api printenv TOKEN_ADMIN 2>/dev/null)"; then
    if [[ -n "${token_no_container//[$'\r\n ']/}" ]]; then
        ok "TOKEN_ADMIN definido na API"
    else
        falha "TOKEN_ADMIN vazio na API: /validacao/executar ficaria aberto" \
              "TOKEN_ADMIN=<segredo> docker compose -f $arquivo_compose up -d"
    fi
    expor_docs="$(docker compose exec -T api printenv EXPOR_DOCS 2>/dev/null | tr -d '\r\n ' | tr 'A-Z' 'a-z')"
    if [[ "$expor_docs" == "false" ]]; then
        ok "EXPOR_DOCS=false"
    else
        falha "EXPOR_DOCS=${expor_docs:-<vazio>} (esperado false)" \
              "defina EXPOR_DOCS=false e recrie a API (docker compose -f $arquivo_compose up -d)"
    fi
else
    falha "container da API não encontrado (pilha de $rotulo fora do ar?)" \
          "docker compose -f $arquivo_compose up -d --wait"
fi

echo "2. Serviços saudáveis"
servicos_ruins="$(docker compose ps --format '{{.Service}}={{.Health}}/{{.State}}' 2>/dev/null \
    | grep -v -e '=healthy/running' -e '^tunel=' || true)"
servicos_ok="$(docker compose ps --format '{{.Service}}={{.Health}}/{{.State}}' 2>/dev/null \
    | grep -c '=healthy/running' || true)"
if [[ -z "$servicos_ruins" && "$servicos_ok" -ge 3 ]]; then
    ok "db, api e frontend healthy"
else
    falha "serviços fora de 'healthy': ${servicos_ruins:-nenhum serviço no ar}" \
          "docker compose -f $arquivo_compose ps; docker compose -f $arquivo_compose logs --tail 50"
fi

echo "3. Migrations aplicadas"
aplicadas="$(docker compose exec -T db psql -X -q -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT versao FROM schema_migrations" 2>/dev/null || true)"
faltando=()
for arq in db/migrations/*.sql; do
    v="$(basename "$arq" .sql)"
    grep -qxF "$v" <<< "$aplicadas" || faltando+=("$v")
done
if [[ ${#faltando[@]} -eq 0 && -n "$aplicadas" ]]; then
    ok "todas as migrations de db/migrations/ aplicadas"
else
    falha "migrations pendentes ou banco inacessível: ${faltando[*]:-tabela schema_migrations ausente}" \
          "./db/banco.sh ${flag_prod}migrar"
fi

echo "4. Funil real zerado"
if estat="$(curl -fsS --max-time 10 "$url_base/api/validacao/estatisticas?origem=real" 2>/dev/null)"; then
    recebidos="$(sed -nE 's/.*"recebidos":([0-9]+).*/\1/p' <<< "$estat")"
    if [[ "$recebidos" == "0" ]]; then
        ok "estatisticas?origem=real com recebidos = 0"
    else
        falha "recebidos = ${recebidos:-?} (testes deixaram dados reais)" \
              "./db/banco.sh ${flag_prod}backup && ./db/banco.sh ${flag_prod}zerar-real   (confira a contagem; só então: --sim-apagar-dados-reais)"
    fi
else
    falha "GET $url_base/api/validacao/estatisticas?origem=real não respondeu" \
          "confira a pilha (item 2) e a porta do frontend"
fi

echo "5. Versão dos seeds (registro para o TCC)"
commit="$(git rev-parse --short HEAD 2>/dev/null || echo desconhecido)"
sujo=""; [[ -n "$(git status --porcelain -- db/seeds db/migrations 2>/dev/null)" ]] && sujo=" (COM alterações não commitadas em db/)"
hash_seeds="$(cat db/seeds/*.sql | sha256sum | cut -c1-16)"
info "commit $commit$sujo; sha256 dos seeds $hash_seeds"

echo "6. Túnel HTTPS"
url_tunel="$(docker compose logs tunel 2>/dev/null | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
if [[ -n "$url_tunel" ]]; then
    info "URL pública do túnel: $url_tunel   (confira no celular; some quando o túnel cair)"
else
    info "túnel inativo (profile tunel): sem HTTPS público; o celular não libera a geolocalização"
fi

mkdir -p backend/scripts/saida
saida="backend/scripts/saida/coleta-$(date +%Y-%m-%d).txt"
{
    echo "preparar-coleta ($rotulo) em $(date -Is)"
    echo "commit: $commit$sujo"
    echo "seeds sha256: $hash_seeds"
    printf '%s\n' "${relatorio[@]}"
    echo "resultado: $([[ $falhas -eq 0 ]] && echo PRONTO || echo "$falhas item(ns) com falha")"
} > "$saida"
echo
echo "registro: $saida"
if [[ $falhas -eq 0 ]]; then
    echo "PRONTO: todos os itens conferem."
else
    echo "NÃO ESTÁ PRONTO: $falhas item(ns) com falha (nada foi alterado)."
    exit 1
fi
