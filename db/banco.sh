#!/usr/bin/env bash
# Operações do banco do docker compose.
#
#   ./db/banco.sh migrar           aplica migrations pendentes e reaplica os seeds
#   ./db/banco.sh testar           roda db/tests/*.sql (em transação, sem deixar dados)
#   ./db/banco.sh psql             abre um console psql
#   ./db/banco.sh preparar-teste   apaga e recria "${POSTGRES_DB}_teste" do zero e
#                                  roda migrations + seeds nele (usado pelos testes
#                                  do backend, via backend/tests/conftest.py)
#   ./db/banco.sh backup           pg_dump -Fc do banco alvo para
#                                  backups/<pilha>-<banco>-<data>.dump, pilha = dev,
#                                  prod ou teste (pasta ignorada pelo git)
#   ./db/banco.sh restaurar ARQ --sim-substituir-banco [--sim-pilha-diferente]
#                                  SUBSTITUI o banco alvo pelo conteúdo do dump ARQ
#                                  (sem o argumento exato, só explica e sai com 1; um
#                                  dump de outra pilha, pelo nome, exige também
#                                  --sim-pilha-diferente; no --prod o banco anterior
#                                  fica guardado, nunca é apagado)
#   ./db/banco.sh zerar-real       SÓ ANTES DA PRIMEIRA ABERTURA DA COLETA: mostra quantas
#                                  linhas origem='real' existem e quantos relatos reais,
#                                  de que data a que data; com o argumento exato
#                                  --sim-apagar-dados-reais, apaga essas linhas
#                                  (docs/implantacao.md §7; reabrir a coleta: §8)
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
# Pilha de produção (docker-compose.prod.yml, docs/implantacao.md): `--prod` antes
# do subcomando (ex.: ./db/banco.sh --prod migrar) ou COMPOSE_FILE=
# docker-compose.prod.yml no ambiente. Sem isso, tudo vale para a pilha de
# desenvolvimento, como sempre. `--teste` aponta para "${POSTGRES_DB}_teste".
# `preparar-teste` recusa --prod: não cria banco de teste no servidor de produção.
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
# Capturado ANTES do source do .env: o que veio da chamada é o que as mensagens de
# recusa precisam repetir no comando sugerido.
banco_alvo_do_ambiente="${BANCO_ALVO:-}"
# Lê o .env. Do shell só se preserva uma LISTA PERMITIDA (o que o E2E, os testes e
# a pilha de produção precisam mudar por chamada): COMPOSE_PROJECT_NAME,
# COMPOSE_FILE, *_PORTA_HOST, *_PORTA_PROD, BANCO_ALVO, BACKUP_DIR, IMAGEM_TAG.
# POSTGRES_DB/USER/PASSWORD vêm SEMPRE do .env: um POSTGRES_DB esquecido no shell
# (a máquina tem outros projetos Postgres) faria backup/restaurar agir noutro
# banco em silêncio. Se divergirem do .env, avisa em stderr (sem mostrar valores
# de senha) e segue com o do .env.
variavel_preservada_do_shell() {
    case "$1" in
        COMPOSE_PROJECT_NAME|COMPOSE_FILE|BANCO_ALVO|BACKUP_DIR|IMAGEM_TAG) return 0 ;;
        *_PORTA_HOST|*_PORTA_PROD) return 0 ;;
        *) return 1 ;;
    esac
}
carregar_env_preservando_lista_permitida() {
    local nome
    local -A do_shell=()
    local -A protegidas_do_shell=()
    while IFS= read -r nome; do
        if [[ -v "$nome" ]]; then
            if variavel_preservada_do_shell "$nome"; then
                do_shell["$nome"]="${!nome}"
            else
                protegidas_do_shell["$nome"]="${!nome}"
            fi
        fi
    done < <(sed -nE 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' .env)
    set -a
    # shellcheck source=/dev/null
    source .env
    set +a
    for nome in "${!do_shell[@]}"; do
        export "$nome=${do_shell[$nome]}"
    done
    for nome in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD; do
        if [[ -v "protegidas_do_shell[$nome]" && "${protegidas_do_shell[$nome]}" != "${!nome}" ]]; then
            echo "aviso: $nome está exportado no shell com valor diferente do .env; ignorado, usando o do .env." >&2
        fi
    done
}
carregar_env_preservando_lista_permitida

# Opções antes do subcomando (podem vir juntas):
#   --prod   pilha de produção (docker-compose.prod.yml); recusado em preparar-teste
#   --teste  banco "${POSTGRES_DB}_teste" (resolvido aqui, com o .env), útil em backup/restaurar
opcao_teste=0
opcao_prod=0
while [[ "${1:-}" == --prod || "${1:-}" == --teste ]]; do
    case "$1" in
        --prod)  export COMPOSE_FILE=docker-compose.prod.yml; opcao_prod=1 ;;
        --teste) opcao_teste=1 ;;
    esac
    shift
done
# O compose de produção interpola TOKEN_ADMIN (obrigatório) mesmo em `exec`; as
# operações do banco não usam o token, então um valor de enchimento basta aqui.
if [[ "${COMPOSE_FILE:-}" == *docker-compose.prod.yml ]]; then
    export TOKEN_ADMIN="${TOKEN_ADMIN:-nao-usado-pelo-banco-sh}"
fi

# Sempre DEPOIS do source .env, para que o .env nunca sobrescreva um BANCO_ALVO
# já definido na chamada (ex.: BANCO_ALVO="${POSTGRES_DB}_teste" ./db/banco.sh migrar).
BANCO_ALVO="${BANCO_ALVO:-$POSTGRES_DB}"
[[ $opcao_teste -eq 1 ]] && BANCO_ALVO="${POSTGRES_DB}_teste"

# As mensagens de recusa sugerem um comando para copiar e colar: ele TEM de
# carregar as mesmas opções (--prod, --teste, BANCO_ALVO=) que apontaram para o
# alvo atual, senão o comando copiado atingiria outro banco (o principal!).
prefixo_do_comando() {
    local p=""
    [[ -n "$banco_alvo_do_ambiente" && $opcao_teste -eq 0 ]] && p="BANCO_ALVO=$banco_alvo_do_ambiente "
    p+="$0 "
    [[ $opcao_prod -eq 1 || "${COMPOSE_FILE:-}" == *docker-compose.prod.yml ]] && p+="--prod "
    [[ $opcao_teste -eq 1 ]] && p+="--teste "
    printf '%s' "$p"
}

pilha_de_producao() { [[ "${COMPOSE_FILE:-}" == *docker-compose.prod.yml ]]; }

descrever_alvo() {
    local pilha="desenvolvimento"
    pilha_de_producao && pilha="PRODUÇÃO"
    echo "Alvo: banco $BANCO_ALVO da pilha de $pilha"
}

# A "pilha" que vai no nome do backup e que o restaurar confere: "teste" (o banco
# <POSTGRES_DB>_teste, em qualquer pilha), "prod" (docker-compose.prod.yml) ou "dev".
pilha_do_alvo() {
    if [[ "$BANCO_ALVO" == "${POSTGRES_DB}_teste" ]]; then
        echo teste
    elif pilha_de_producao; then
        echo prod
    else
        echo dev
    fi
}

# De que pilha é um dump, pelo prefixo do nome (<pilha>-<banco>-<data>.dump). Vazio
# se o nome não começa com dev-, prod- ou teste- (ex.: backups de antes deste padrão).
pilha_do_arquivo() {
    local nome
    nome="$(basename "$1")"
    if [[ "$nome" =~ ^(dev|prod|teste)- ]]; then
        echo "${BASH_REMATCH[1]}"
    fi
}

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

# Relatos reais (o `recebidos` do funil: aceitos em `alertas` + reprovados no
# estágio 1 em `alertas_rejeitados`) e o intervalo em que chegaram, no horário de
# São Paulo (o TZ do compose). Saída do psql -At: total|aceitos|rejeitados|primeiro|último.
SQL_RELATOS_REAIS="
WITH relatos AS (
    SELECT 'aceito' AS destino, criado_em AS em FROM alertas WHERE origem = 'real'
    UNION ALL
    SELECT 'rejeitado', recebido_em FROM alertas_rejeitados WHERE origem = 'real'
)
SELECT count(*),
       count(*) FILTER (WHERE destino = 'aceito'),
       count(*) FILTER (WHERE destino = 'rejeitado'),
       coalesce(to_char(min(em) AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'), '-'),
       coalesce(to_char(max(em) AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'), '-')
FROM relatos"

# Uma linha: quantos relatos reais existem e de quando a quando. É o que impede
# alguém de apagar dias de coleta achando que são só testes.
resumo_dos_relatos_reais() {
    local linha total aceitos rejeitados primeiro ultimo
    linha="$(psql_no_container -At -c "$SQL_RELATOS_REAIS")"
    IFS='|' read -r total aceitos rejeitados primeiro ultimo <<< "$linha"
    if [[ "$total" == 0 ]]; then
        echo "relatos reais: nenhum"
    else
        echo "relatos reais: $total ($aceitos aceitos + $rejeitados reprovados no estágio 1), de $primeiro a $ultimo (horário de São Paulo)"
    fi
}

# Apaga os dados REAIS (origem='real') que testes manuais deixaram na pilha,
# para o funil da coleta começar do zero. Uso: SÓ antes da PRIMEIRA abertura da
# coleta; depois disso, estes são os dados do TCC (reabrir a coleta num dia
# seguinte é `./scripts/preparar-coleta.sh --reabrir`, que nunca apaga nada).
# Sem o argumento exato de confirmação, só mostra o que seria apagado (contagens,
# quantos relatos e de quando) e sai com código 1.
zerar_real() {
    local confirmacao="${1:-}"
    echo "banco $BANCO_ALVO, antes:"
    psql_no_container -c "$SQL_CONTAGENS_POR_ORIGEM"
    local resumo
    resumo="$(resumo_dos_relatos_reais)"

    if [[ "$confirmacao" != "--sim-apagar-dados-reais" ]]; then
        {
            echo "nada foi apagado. Isto apaga TODOS os dados reais (origem='real'):"
            echo "  $resumo"
            echo "É só para ANTES da PRIMEIRA abertura da coleta (docs/implantacao.md §7): aí"
            echo "esses relatos são testes. Se a coleta já foi aberta alguma vez, eles são os"
            echo "dados do TCC: NÃO apague. Para reabrir a coleta (dia 2 em diante, túnel que"
            echo "caiu), use ./scripts/preparar-coleta.sh --reabrir (docs/implantacao.md §8)."
            descrever_alvo
            echo "Para apagar: $(prefixo_do_comando)zerar-real --sim-apagar-dados-reais"
        } >&2
        exit 1
    fi
    echo "apagando do banco $BANCO_ALVO: $resumo"

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
# §3). O dump sai pelo stdout do container, então nada fica dentro dele. Grava em
# .parcial e só renomeia se o pg_dump terminar bem; em falha ou Ctrl-C o .parcial
# é removido. O nome começa pela pilha (dev-, prod- ou teste-): um backup diz de
# onde veio, e o restaurar recusa trocar a produção por um dump do dev sem que
# isso seja pedido com todas as letras.
arquivo_parcial=""
backup() {
    # Os dumps têm as trajetórias dos voluntários (sessao_hash + criado_em + geom):
    # arquivo e pasta nascem legíveis só pelo dono (600/700).
    umask 077
    # BACKUP_DIR só existe para os testes não tocarem a pasta real (backups/).
    local pasta="${BACKUP_DIR:-backups}"
    mkdir -p "$pasta"
    descrever_alvo
    local arquivo
    arquivo="${pasta}/$(pilha_do_alvo)-${BANCO_ALVO}-$(date +%Y%m%d-%H%M%S).dump"
    arquivo_parcial="$arquivo.parcial"
    trap '[[ -n "$arquivo_parcial" ]] && rm -f "$arquivo_parcial"' EXIT
    docker compose exec -T db \
        pg_dump -Fc -U "$POSTGRES_USER" -d "$BANCO_ALVO" > "$arquivo_parcial"
    mv "$arquivo_parcial" "$arquivo"
    arquivo_parcial=""
    echo "backup: $arquivo ($(du -h "$arquivo" | cut -f1))"
}

# Substitui o banco alvo pelo conteúdo de um dump, sem nunca deixá-lo vazio ou
# pela metade (R32): valida o arquivo (pg_restore --list), restaura num banco
# temporário "<alvo>_restaurando" e SÓ se isso der certo troca os nomes (o antigo
# vira "<alvo>_antigo_<data>"; fora da produção ele é apagado no fim, e no --prod
# fica GUARDADO, para ser apagado à mão depois de conferir o restaurado). Qualquer
# falha antes da troca apaga só o temporário e o banco original fica como estava.
# Exige o argumento literal --sim-substituir-banco; se o nome do dump diz que ele
# veio de outra pilha (ou não diz de qual veio), exige também --sim-pilha-diferente.
restaurar() {
    local arquivo="${1:-}" confirmacao="" pilha_diferente_confirmada=0 argumento
    shift || true
    for argumento in "$@"; do
        case "$argumento" in
            --sim-substituir-banco) confirmacao="$argumento" ;;
            --sim-pilha-diferente) pilha_diferente_confirmada=1 ;;
            *)
                echo "erro: argumento desconhecido: $argumento (nada foi feito). Uso: $0 restaurar backups/ARQUIVO.dump --sim-substituir-banco [--sim-pilha-diferente]" >&2
                exit 2
                ;;
        esac
    done
    if [[ -z "$arquivo" || ! -f "$arquivo" ]]; then
        echo "erro: informe um dump existente. Uso: $0 restaurar backups/ARQUIVO.dump --sim-substituir-banco" >&2
        exit 2
    fi
    if [[ "$arquivo" == *.parcial ]]; then
        echo "erro: $arquivo é um backup incompleto (.parcial); recuse-o e refaça o backup." >&2
        exit 1
    fi
    local pilha_alvo pilha_origem origem_do_arquivo
    pilha_alvo="$(pilha_do_alvo)"
    pilha_origem="$(pilha_do_arquivo "$arquivo")"
    if [[ -n "$pilha_origem" ]]; then
        origem_do_arquivo="Arquivo: backup da pilha $pilha_origem (pelo nome); o alvo é da pilha $pilha_alvo."
    else
        origem_do_arquivo="Arquivo: pilha de origem DESCONHECIDA (o nome não começa com dev-, prod- ou teste-); o alvo é da pilha $pilha_alvo."
    fi
    local extra=""
    [[ "$pilha_origem" != "$pilha_alvo" ]] && extra=" --sim-pilha-diferente"
    if [[ "$confirmacao" != "--sim-substituir-banco" ]]; then
        {
            echo "nada foi feito. Isto SUBSTITUI o banco $BANCO_ALVO pelo conteúdo de $arquivo."
            descrever_alvo
            echo "$origem_do_arquivo"
            [[ -n "$extra" ]] && echo "ATENÇÃO: a pilha do arquivo não é a do alvo; só siga se for de propósito (ex.: ensaiar no banco de teste um backup da produção)."
            echo "Para continuar: $(prefixo_do_comando)restaurar $arquivo --sim-substituir-banco$extra"
        } >&2
        exit 1
    fi
    if [[ -n "$extra" && $pilha_diferente_confirmada -eq 0 ]]; then
        {
            echo "nada foi feito: $origem_do_arquivo"
            descrever_alvo
            echo "Trocar um banco por um backup de outra pilha (ex.: a produção por um dump do"
            echo "desenvolvimento) apagaria dados reais. Se é isso mesmo, acrescente --sim-pilha-diferente:"
            echo "  $(prefixo_do_comando)restaurar $arquivo --sim-substituir-banco --sim-pilha-diferente"
        } >&2
        exit 1
    fi
    if ! docker compose exec -T db pg_restore --list < "$arquivo" > /dev/null 2>&1; then
        echo "erro: $arquivo não é um dump válido do pg_dump -Fc (truncado, corrompido ou de outro formato). Nada foi alterado." >&2
        exit 1
    fi

    local temporario="${BANCO_ALVO}_restaurando"
    local antigo="${BANCO_ALVO}_antigo_$(date +%Y%m%d%H%M%S)"
    local -a admin=(docker compose exec -T db psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres)

    echo "restaurando $arquivo em $temporario (o banco $BANCO_ALVO continua intacto até o fim)"
    "${admin[@]}" -c "DROP DATABASE IF EXISTS ${temporario} WITH (FORCE)" -c "CREATE DATABASE ${temporario}"
    if ! docker compose exec -T db \
            pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d "$temporario" < "$arquivo"; then
        "${admin[@]}" -c "DROP DATABASE IF EXISTS ${temporario} WITH (FORCE)" || true
        echo "erro: a restauração falhou; $BANCO_ALVO não foi tocado e o temporário foi apagado." >&2
        exit 1
    fi

    local existe
    existe="$("${admin[@]}" -At -c "SELECT 1 FROM pg_database WHERE datname = '${BANCO_ALVO}'")"
    local afastado=0
    # Desfaz a troca se algo falhar ou o script for interrompido (Ctrl-C, kill)
    # entre os dois RENAME; se nem isso der, imprime o SQL para recuperar à mão.
    reverter_troca() {
        trap - INT TERM ERR
        set +e
        echo >&2
        echo "interrompido durante a troca: tentando devolver o banco original..." >&2
        local ok=1
        if [[ $afastado -eq 0 && -n "$existe" ]] \
                && [[ -z "$("${admin[@]}" -At -c "SELECT 1 FROM pg_database WHERE datname = '${BANCO_ALVO}'" 2>/dev/null)" ]]; then
            afastado=1   # o RENAME chegou a acontecer antes da interrupção
        fi
        if [[ $afastado -eq 0 && -n "$existe" ]]; then
            # A chamada que afasta o original pode ter parado no meio, depois do
            # ALLOW_CONNECTIONS false e antes do RENAME: reabre o original.
            "${admin[@]}" -c "ALTER DATABASE ${BANCO_ALVO} ALLOW_CONNECTIONS true" > /dev/null 2>&1 || {
                ok=0
                echo "NÃO consegui reabrir as conexões de ${BANCO_ALVO}. No psql do banco postgres: ALTER DATABASE ${BANCO_ALVO} ALLOW_CONNECTIONS true;" >&2
            }
        fi
        if [[ $afastado -eq 1 ]]; then
            "${admin[@]}" -c "ALTER DATABASE ${BANCO_ALVO} RENAME TO ${temporario}_perdido" > /dev/null 2>&1 || true
            "${admin[@]}" -c "ALTER DATABASE ${antigo} RENAME TO ${BANCO_ALVO}" \
                -c "ALTER DATABASE ${BANCO_ALVO} ALLOW_CONNECTIONS true" > /dev/null 2>&1 || ok=0
        fi
        if [[ $ok -eq 1 ]]; then
            "${admin[@]}" -c "DROP DATABASE IF EXISTS ${temporario} WITH (FORCE)" > /dev/null 2>&1 || true
            "${admin[@]}" -c "DROP DATABASE IF EXISTS ${temporario}_perdido WITH (FORCE)" > /dev/null 2>&1 || true
            echo "erro: troca desfeita; $BANCO_ALVO é o banco original." >&2
        else
            {
                echo "NÃO consegui devolver o banco. Seus dados estão em ${antigo}. Para recuperar à mão, no psql do banco postgres:"
                echo "  ALTER DATABASE ${BANCO_ALVO} RENAME TO ${BANCO_ALVO}_descartado;  -- só se ${BANCO_ALVO} existir"
                echo "  ALTER DATABASE ${antigo} RENAME TO ${BANCO_ALVO};"
                echo "  ALTER DATABASE ${BANCO_ALVO} ALLOW_CONNECTIONS true;"
            } >&2
        fi
        exit 1
    }
    trap reverter_troca INT TERM ERR
    if [[ -n "$existe" ]]; then
        # Impede novas conexões e derruba as atuais, para o RENAME não falhar.
        "${admin[@]}" \
            -c "ALTER DATABASE ${BANCO_ALVO} ALLOW_CONNECTIONS false" \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${BANCO_ALVO}' AND pid <> pg_backend_pid()" \
            -c "ALTER DATABASE ${BANCO_ALVO} RENAME TO ${antigo}" > /dev/null
        afastado=1
    fi
    "${admin[@]}" -c "ALTER DATABASE ${temporario} RENAME TO ${BANCO_ALVO}"
    trap - INT TERM ERR
    if [[ -z "$existe" ]]; then
        echo "restaurado: $BANCO_ALVO"
        return
    fi
    # O `psql` do banco.sh abre o banco alvo; dali dá para apagar OUTRO banco, como o antigo.
    if pilha_de_producao; then
        # Na produção o banco anterior pode ter dias de coleta: nunca é apagado aqui.
        echo "restaurado: $BANCO_ALVO."
        echo "O banco anterior NÃO foi apagado: ficou guardado como ${antigo} (fechado para conexões)."
        echo "Confira o restaurado (./scripts/preparar-coleta.sh --reabrir, contagens) e só então apague o guardado:"
        echo "  $(prefixo_do_comando)psql      e, no psql:  DROP DATABASE ${antigo};"
        return
    fi
    if ! "${admin[@]}" -c "DROP DATABASE IF EXISTS ${antigo} WITH (FORCE)"; then
        echo "restaurado: $BANCO_ALVO. Mas o banco antigo ficou como ${antigo}; apague depois com:" >&2
        echo "  $(prefixo_do_comando)psql      e, no psql:  DROP DATABASE ${antigo} WITH (FORCE);" >&2
        exit 0
    fi
    echo "restaurado: $BANCO_ALVO"
}

preparar_teste() {
    if [[ "${COMPOSE_FILE:-}" == *docker-compose.prod.yml ]]; then
        echo "erro: preparar-teste não roda na pilha de produção (--prod)." >&2
        exit 2
    fi
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
    restaurar)      restaurar "${@:2}" ;;
    *)
        echo "uso: $0 [--prod] [--teste] {migrar|testar|psql|preparar-teste|backup|restaurar ARQ --sim-substituir-banco [--sim-pilha-diferente]|zerar-real [--sim-apagar-dados-reais]}" >&2
        exit 2
        ;;
esac
