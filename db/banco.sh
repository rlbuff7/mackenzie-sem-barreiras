#!/usr/bin/env bash
# Operações do banco do docker compose.
#
#   ./db/banco.sh migrar           aplica migrations pendentes e reaplica os seeds
#   ./db/banco.sh testar           roda db/tests/*.sql (em transação, sem deixar dados)
#   ./db/banco.sh psql             abre um console psql
#   ./db/banco.sh preparar-teste   apaga e recria "${POSTGRES_DB}_teste" do zero e
#                                  roda migrations + seeds nele (usado pelos testes
#                                  do backend, via backend/tests/conftest.py)
#   ./db/banco.sh backup           pg_dump -Fc do banco alvo para backups/<banco>-<data>.dump
#                                  (pasta ignorada pelo git)
#   ./db/banco.sh restaurar ARQ --sim-substituir-banco
#                                  APAGA o banco alvo e o recria a partir do dump ARQ
#                                  (sem o argumento exato, só explica e sai com 1)
#   ./db/banco.sh zerar-real       SÓ ANTES DA COLETA EM CAMPO: mostra quantas linhas
#                                  origem='real' existem; com o argumento exato
#                                  --sim-apagar-dados-reais, apaga essas linhas
#                                  (docs/coleta-em-campo.md §5)
#
# Migrations (db/migrations/NNN_*.sql) rodam UMA vez, em ordem, cada uma numa
# transação; o controle fica na tabela schema_migrations. São imutáveis depois de
# aplicadas: correção vira migration nova (CLAUDE.md §10).
#
# Seeds (db/seeds/*.sql) são idempotentes (upsert) e rodam em TODA execução de
# `migrar`, porque taxonomia e polígono ainda vão mudar (docs/decisoes-pendentes.md).
# Durante a coleta em campo os seeds ficam congelados: mudar o polígono no meio
# misturaria dois geofences no funil real (docs/coleta-em-campo.md §5).
#
# Usa o psql de dentro do container: nada precisa ser instalado na máquina.
#
# Pilha de produção (docker-compose.prod.yml, docs/implantacao.md): `--prod` como
# PRIMEIRO argumento (ex.: ./db/banco.sh --prod migrar) ou COMPOSE_FILE=
# docker-compose.prod.yml no ambiente. Sem isso, tudo vale para a pilha de
# desenvolvimento, como sempre.
#
# BANCO_ALVO controla contra qual banco `migrar`, `zerar-real` e
# `psql_no_container` operam (padrão: $POSTGRES_DB). É assim que `preparar-teste`
# reaplica migrations e seeds no banco de teste sem duplicar essa lógica, e que
# os testes rodam `zerar-real` no banco de teste (backend/tests/test_zerar_real.py).
set -euo pipefail
shopt -s nullglob

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

if [[ ! -f .env ]]; then
    echo "erro: .env não encontrado. Rode: cp .env.example .env" >&2
    exit 1
fi
set -a; source .env; set +a

if [[ "${1:-}" == "--prod" ]]; then
    shift
    export COMPOSE_FILE=docker-compose.prod.yml
fi
# O compose de produção interpola TOKEN_ADMIN (obrigatório) mesmo em `exec`; as
# operações do banco não usam o token, então um valor de enchimento basta aqui.
if [[ "${COMPOSE_FILE:-}" == *docker-compose.prod.yml ]]; then
    export TOKEN_ADMIN="${TOKEN_ADMIN:-nao-usado-pelo-banco-sh}"
fi

# Sempre DEPOIS do source .env, para que o .env nunca sobrescreva um BANCO_ALVO
# já definido na chamada (ex.: BANCO_ALVO="${POSTGRES_DB}_teste" ./db/banco.sh migrar).
BANCO_ALVO="${BANCO_ALVO:-$POSTGRES_DB}"

psql_no_container() {
    docker compose exec -T db \
        psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$BANCO_ALVO" "$@"
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

# Linhas de cada tabela que zerar-real limpa, por origem: a coluna `simulacao`
# está aqui para mostrar que ela nunca muda.
SQL_CONTAGENS_POR_ORIGEM="
SELECT 'alertas' AS tabela,
       count(*) FILTER (WHERE origem = 'real') AS real,
       count(*) FILTER (WHERE origem = 'simulacao') AS simulacao
FROM alertas
UNION ALL
SELECT 'barreiras', count(*) FILTER (WHERE origem = 'real'),
       count(*) FILTER (WHERE origem = 'simulacao')
FROM barreiras
UNION ALL
SELECT 'alertas_rejeitados', count(*) FILTER (WHERE origem = 'real'),
       count(*) FILTER (WHERE origem = 'simulacao')
FROM alertas_rejeitados
UNION ALL
SELECT 'execucoes_pipeline', count(*) FILTER (WHERE origem = 'real'),
       count(*) FILTER (WHERE origem = 'simulacao')
FROM execucoes_pipeline"

# Apaga os dados REAIS (origem='real') que testes manuais deixaram na pilha
# principal, para o funil da coleta começar do zero. Uso: SÓ antes de abrir a
# coleta; depois disso, estes são os dados do TCC. Sem o argumento exato de
# confirmação, só mostra o que seria apagado e sai com código 1.
zerar_real() {
    local confirmacao="${1:-}"
    echo "banco $BANCO_ALVO, antes:"
    psql_no_container -c "$SQL_CONTAGENS_POR_ORIGEM"

    if [[ "$confirmacao" != "--sim-apagar-dados-reais" ]]; then
        {
            echo "nada foi apagado. Isto apaga TODOS os dados reais (origem='real') e"
            echo "é só para ANTES da coleta em campo (docs/coleta-em-campo.md §5)."
            echo "Para apagar: ./db/banco.sh zerar-real --sim-apagar-dados-reais"
        } >&2
        exit 1
    fi

    # Uma transação só (ON_ERROR_STOP): ou apaga tudo, ou nada. alertas antes
    # de barreiras, por causa da FK alertas.barreira_id. Nenhum WHERE toca
    # origem='simulacao'.
    psql_no_container --single-transaction \
        -c "DELETE FROM alertas WHERE origem = 'real'" \
        -c "DELETE FROM barreiras WHERE origem = 'real'" \
        -c "DELETE FROM alertas_rejeitados WHERE origem = 'real'" \
        -c "DELETE FROM execucoes_pipeline WHERE origem = 'real'"

    echo "banco $BANCO_ALVO, depois:"
    psql_no_container -c "$SQL_CONTAGENS_POR_ORIGEM"
}

# pg_dump no formato custom (-Fc): compacto e restaurável com pg_restore. Vai para
# backups/, ignorada pelo git (contém dados de voluntários: docs/coleta-em-campo.md
# §3). O dump sai pelo stdout do container, então nada fica dentro dele.
backup() {
    mkdir -p backups
    local arquivo
    arquivo="backups/${BANCO_ALVO}-$(date +%Y%m%d-%H%M%S).dump"
    docker compose exec -T db \
        pg_dump -Fc -U "$POSTGRES_USER" -d "$BANCO_ALVO" > "$arquivo.parcial"
    mv "$arquivo.parcial" "$arquivo"
    echo "backup: $arquivo ($(du -h "$arquivo" | cut -f1))"
}

# Substitui o banco alvo pelo conteúdo de um dump. Destrutivo: exige o argumento
# literal. Encerra conexões abertas (WITH FORCE), recria o banco vazio e restaura.
restaurar() {
    local arquivo="${1:-}" confirmacao="${2:-}"
    if [[ -z "$arquivo" || ! -f "$arquivo" ]]; then
        echo "erro: informe um dump existente. Uso: $0 restaurar backups/ARQUIVO.dump --sim-substituir-banco" >&2
        exit 2
    fi
    if [[ "$confirmacao" != "--sim-substituir-banco" ]]; then
        {
            echo "nada foi feito. Isto APAGA o banco $BANCO_ALVO e o recria a partir de $arquivo."
            echo "Para continuar: $0 restaurar $arquivo --sim-substituir-banco"
        } >&2
        exit 1
    fi
    echo "restaurando $arquivo em $BANCO_ALVO (o banco atual será apagado)"
    docker compose exec -T db \
        psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS ${BANCO_ALVO} WITH (FORCE)" \
        -c "CREATE DATABASE ${BANCO_ALVO}"
    docker compose exec -T db \
        pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d "$BANCO_ALVO" < "$arquivo"
    echo "restaurado: $BANCO_ALVO"
}

preparar_teste() {
    local banco_teste="${POSTGRES_DB}_teste"
    echo "recriando banco de teste: $banco_teste"
    # Sempre contra o banco "postgres": não dá para DROP DATABASE do banco em que
    # se está conectado. WITH (FORCE) derruba conexões residuais de execuções
    # anteriores (ex.: um pytest interrompido no meio).
    docker compose exec -T db \
        psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS ${banco_teste} WITH (FORCE)" \
        -c "CREATE DATABASE ${banco_teste}"
    BANCO_ALVO="$banco_teste" migrar
}

case "${1:-}" in
    migrar)         migrar ;;
    testar)         testar ;;
    psql)           docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" ;;
    preparar-teste) preparar_teste ;;
    zerar-real)     zerar_real "${2:-}" ;;
    backup)         backup ;;
    restaurar)      restaurar "${2:-}" "${3:-}" ;;
    *)
        echo "uso: $0 [--prod] {migrar|testar|psql|preparar-teste|backup|restaurar ARQ --sim-substituir-banco|zerar-real [--sim-apagar-dados-reais]}" >&2
        exit 2
        ;;
esac
