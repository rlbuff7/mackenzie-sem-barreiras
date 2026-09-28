#!/usr/bin/env bash
# Operações do banco do docker compose.
#
#   ./db/banco.sh migrar   aplica migrations pendentes e reaplica os seeds
#   ./db/banco.sh testar   roda db/tests/*.sql (em transação, sem deixar dados)
#   ./db/banco.sh psql     abre um console psql
#
# Migrations (db/migrations/NNN_*.sql) rodam UMA vez, em ordem, cada uma numa
# transação; o controle fica na tabela schema_migrations. São imutáveis depois de
# aplicadas: correção vira migration nova (CLAUDE.md §10).
#
# Seeds (db/seeds/*.sql) são idempotentes (upsert) e rodam em TODA execução de
# `migrar`, porque taxonomia e polígono ainda vão mudar (docs/decisoes-pendentes.md).
#
# Usa o psql de dentro do container: nada precisa ser instalado na máquina.
set -euo pipefail
shopt -s nullglob

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

if [[ ! -f .env ]]; then
    echo "erro: .env não encontrado. Rode: cp .env.example .env" >&2
    exit 1
fi
set -a; source .env; set +a

psql_no_container() {
    docker compose exec -T db \
        psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
}

migrar() {
    psql_no_container -c "SET client_min_messages = warning" -c "CREATE TABLE IF NOT EXISTS schema_migrations (
        versao      VARCHAR(255) PRIMARY KEY,
        aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now())"

    local aplicadas pendentes=0
    aplicadas="$(psql_no_container -At -c "SELECT versao FROM schema_migrations")"

    for arquivo in db/migrations/*.sql; do
        local versao
        versao="$(basename "$arquivo" .sql)"
        grep -qxF "$versao" <<< "$aplicadas" && continue

        echo "migration  $versao"
        # A migration e o seu registro entram na MESMA transação: ou os dois
        # acontecem, ou nenhum.
        { echo "SET client_min_messages = warning;"
          cat "$arquivo"
          printf "\nINSERT INTO schema_migrations (versao) VALUES ('%s');\n" "$versao"; } \
            | psql_no_container --single-transaction -f -
        pendentes=$((pendentes + 1))
    done
    [[ $pendentes -eq 0 ]] && echo "migrations: nada pendente"

    for arquivo in db/seeds/*.sql; do
        echo "seed       $(basename "$arquivo")"
        { echo "SET client_min_messages = warning;"; cat "$arquivo"; } \
            | psql_no_container --single-transaction -f -
    done
}

testar() {
    local arquivos=(db/tests/*.sql)
    if [[ ${#arquivos[@]} -eq 0 ]]; then
        echo "nenhum teste em db/tests/" >&2
        exit 1
    fi
    for arquivo in "${arquivos[@]}"; do
        echo "== $(basename "$arquivo")"
        # Tira o prefixo "psql:<stdin>:N: NOTICE:" das linhas de resultado.
        psql_no_container -f - < "$arquivo" 2>&1 \
            | sed -E 's/^psql:<stdin>:[0-9]+: (NOTICE|ERROR): +//'
    done
}

case "${1:-}" in
    migrar) migrar ;;
    testar) testar ;;
    psql)   docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" ;;
    *)
        echo "uso: $0 {migrar|testar|psql}" >&2
        exit 2
        ;;
esac
