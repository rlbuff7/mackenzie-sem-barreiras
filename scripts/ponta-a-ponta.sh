#!/usr/bin/env bash
# Teste ponta a ponta (E2E), M5: sobe uma pilha ISOLADA do docker compose
# (COMPOSE_PROJECT_NAME=msb-e2e, portas 55434/58000/58080, volume próprio),
# aplica migrations+seeds nela, roda o contrato inteiro da API por HTTP
# (backend/scripts/ponta_a_ponta.py) e SEMPRE derruba a pilha isolada no fim
# — sucesso, falha ou Ctrl-C — sem tocar a pilha principal nem o banco dela.
#
#   ./scripts/ponta-a-ponta.sh
#
# Depuração (prova de que uma falha deliberada também limpa e sai != 0), sem
# editar código: ESPERADO_BARREIRAS_CONFIRMADAS=2 ./scripts/ponta-a-ponta.sh
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

if [[ ! -f .env ]]; then
    echo "erro: .env não encontrado. Rode: cp .env.example .env" >&2
    exit 1
fi

# O teste em Python (backend/scripts/ponta_a_ponta.py) lê TOKEN_ADMIN do
# ambiente: com o token definido, POST /validacao/executar exige o header
# X-Token-Admin (D7), e sem o .env carregado aqui o teste recebia 401. Quem
# chamou o script tem prioridade sobre o .env, a mesma regra que o docker
# compose usa na interpolação: `TOKEN_ADMIN=... ./scripts/ponta-a-ponta.sh`
# testa com um token temporário sem editar o .env (o docker-compose.yml passa
# esse mesmo TOKEN_ADMIN para o container da API).
carregar_env_sem_sobrescrever_o_shell() {
    local nome
    local -A do_shell=()
    while IFS= read -r nome; do
        if [[ -v "$nome" ]]; then
            do_shell["$nome"]="${!nome}"
        fi
    done < <(sed -nE 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' .env)
    set -a
    # shellcheck source=/dev/null
    source .env
    set +a
    for nome in "${!do_shell[@]}"; do
        export "$nome=${do_shell[$nome]}"
    done
}
carregar_env_sem_sobrescrever_o_shell

# Projeto e portas isolados. Exportados DEPOIS do .env (para valerem sempre) e
# ANTES de qualquer `docker compose` ou `./db/banco.sh`: são variáveis de
# ambiente do shell, então têm prioridade sobre o .env na interpolação do
# docker-compose.yml (${VAR:-padrão}).
# db/banco.sh só preserva do shell uma lista permitida (COMPOSE_PROJECT_NAME e
# *_PORTA_HOST entre elas); e `docker compose exec` (usado por banco.sh)
# identifica o container pelo nome do SERVIÇO dentro do projeto, não por porta.
export COMPOSE_PROJECT_NAME=msb-e2e
export POSTGRES_PORTA_HOST=55434
export API_PORTA_HOST=58000
export FRONTEND_PORTA_HOST=58080

derrubar_pilha_isolada() {
    local codigo=$?
    echo
    echo "== derrubando a pilha isolada (projeto $COMPOSE_PROJECT_NAME) =="
    if ! docker compose down --volumes --remove-orphans; then
        echo "aviso: 'docker compose down' falhou; a pilha isolada '$COMPOSE_PROJECT_NAME' pode ter ficado de pé (docker compose -p $COMPOSE_PROJECT_NAME down --volumes)." >&2
    fi
    exit "$codigo"
}
trap derrubar_pilha_isolada EXIT INT TERM

echo "== confirmando que o projeto ativo é '$COMPOSE_PROJECT_NAME' (isolado da pilha principal) =="
# O JSON é lido por um parser (não por grep no texto): não depende de espaçamento.
docker compose config --format json | python3 -c '
import json, sys
sys.exit(0 if json.load(sys.stdin).get("name") == sys.argv[1] else 1)
' "$COMPOSE_PROJECT_NAME" || {
    echo "erro: docker compose não resolveu o projeto isolado '$COMPOSE_PROJECT_NAME'." >&2
    exit 1
}

echo "== subindo a pilha isolada em 127.0.0.1:${POSTGRES_PORTA_HOST}/${API_PORTA_HOST}/${FRONTEND_PORTA_HOST} =="
docker compose up -d --build --wait

echo "== aplicando migrations e seeds na pilha isolada =="
./db/banco.sh migrar

echo "== rodando o teste ponta a ponta por HTTP =="
(
    cd backend
    uv run python -m scripts.ponta_a_ponta \
        "http://localhost:${API_PORTA_HOST}" \
        "http://localhost:${FRONTEND_PORTA_HOST}"
)
