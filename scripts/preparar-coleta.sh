#!/usr/bin/env bash
# Checklist executável da coleta em campo (docs/implantacao.md §4, §7 e §8,
# docs/coleta-em-campo.md §5). SÓ LÊ E RELATA: nunca apaga nem altera dado, nunca
# sobe ou derruba nada; quando algo falha, sugere o comando (sem executá-lo).
#
#   ./scripts/preparar-coleta.sh             ANTES da primeira abertura (pilha de PRODUÇÃO)
#   ./scripts/preparar-coleta.sh --reabrir   coleta JÁ EM ANDAMENTO (dia 2 em diante, túnel
#                                            que caiu): os relatos reais são informação
#   ./scripts/preparar-coleta.sh --dev ...   o mesmo na pilha de desenvolvimento (ensaio)
#
# Confere: TOKEN_ADMIN definido (avisa se tiver menos de 24 caracteres) e
# EXPOR_DOCS=false (lidos do container da API, o que de fato vale), serviços
# saudáveis, migrations aplicadas e o funil real.
# Antes da primeira abertura o funil real tem de estar zerado (recebidos = 0); se
# não estiver, diz quantos relatos reais há e de quando, e explica as duas saídas
# (testes: backup e zerar-real; coleta já aberta: --reabrir). Com --reabrir, os
# relatos reais são só informados (quantos e de quando) e o script NUNCA sugere
# apagá-los. Registra commit, hash dos seeds e as imagens em execução (ID local e
# RepoDigest do registro) em backend/scripts/saida/coleta-<pilha>[-reabrir]-<data-hora>.txt
# (não versionado; um arquivo por execução, nunca sobrescrito). Se o túnel (profile
# `tunel`) estiver no ar, imprime a URL pública lida dos logs da subida ATUAL do
# cloudflared. Sai com código 1 se algum item falhou.
set -uo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

if [[ ! -f .env ]]; then
    echo "erro: .env não encontrado. Rode: cp .env.example .env" >&2
    exit 1
fi
# .env é só configuração; o container é a fonte da verdade abaixo. Do shell só se
# preserva a mesma LISTA PERMITIDA do db/banco.sh (R35), para o teste ponta a ponta
# apontar este checklist para a pilha isolada: COMPOSE_PROJECT_NAME, IMAGEM_TAG,
# REGISTRO_DIR, *_PORTA_HOST e *_PORTA_PROD. Credenciais e nome do banco vêm
# SEMPRE do .env.
variavel_preservada_do_shell() {
    case "$1" in
        COMPOSE_PROJECT_NAME|IMAGEM_TAG|REGISTRO_DIR) return 0 ;;
        *_PORTA_HOST|*_PORTA_PROD) return 0 ;;
        *) return 1 ;;
    esac
}
carregar_env_preservando_lista_permitida() {
    local nome
    local -A do_shell=()
    while IFS= read -r nome; do
        if [[ -v "$nome" ]] && variavel_preservada_do_shell "$nome"; then
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
carregar_env_preservando_lista_permitida

uso() {
    echo "uso: $0 [--prod|--dev] [--reabrir]   (padrão: --prod, a pilha de produção, antes da primeira abertura)" >&2
    exit 2
}
modo_dev=""
reabrir=0
for argumento in "$@"; do
    case "$argumento" in
        --prod) [[ "$modo_dev" == 1 ]] && uso; modo_dev=0 ;;
        --dev)  [[ "$modo_dev" == 0 ]] && uso; modo_dev=1 ;;
        --reabrir) reabrir=1 ;;
        *) uso ;;
    esac
done

if [[ "$modo_dev" == 1 ]]; then
    arquivo_compose=docker-compose.yml
    porta_frontend="${FRONTEND_PORTA_HOST:-8081}"
    rotulo="desenvolvimento"
    flag_prod=""
    flag_dev="--dev "
else
    arquivo_compose=docker-compose.prod.yml
    porta_frontend="${FRONTEND_PORTA_PROD:-8091}"
    rotulo="produção"
    flag_prod="--prod "
    flag_dev=""
    # O compose de produção interpola TOKEN_ADMIN mesmo para ps/exec/logs. Este
    # script nunca recria nada (nenhum `up`), então o valor de enchimento é inócuo.
    export TOKEN_ADMIN="${TOKEN_ADMIN:-nao-usado-por-este-script}"
fi
export COMPOSE_FILE="$arquivo_compose"
url_base="http://127.0.0.1:${porta_frontend}"   # pelo frontend: confere o proxy /api/ também

falhas=0
relatorio=()
ok()    { echo "  [ok]     $1"; relatorio+=("ok     $1"); }
# falha "o que falhou" ["sugestão" ["continuação da sugestão" ...]]
falha() {
    echo "  [FALHA]  $1"
    relatorio+=("FALHA  $1")
    shift
    local prefixo="sugestão: "
    for linha in "$@"; do
        echo "           $prefixo$linha"
        prefixo="          "
    done
    falhas=$((falhas + 1))
}
info()  { echo "  [info]   $1"; relatorio+=("info   $1"); }
# aviso: algo a corrigir que não impede o PRONTO (nem apaga nada), só enfraquece.
avisos=0
aviso() {
    echo "  [AVISO]  $1"
    relatorio+=("AVISO  $1")
    [[ -n "${2:-}" ]] && echo "           sugestão: $2"
    avisos=$((avisos + 1))
}
comando_novo_token='python3 -c "import secrets; print(secrets.token_urlsafe(32))"'

if [[ $reabrir -eq 1 ]]; then
    echo "== preparar-coleta --reabrir: pilha de $rotulo ($arquivo_compose), coleta EM ANDAMENTO =="
else
    echo "== preparar-coleta: pilha de $rotulo ($arquivo_compose), antes da primeira abertura =="
fi

echo "1. Configuração efetiva da API (lida do container)"
if [[ -z "$(docker compose ps -q api 2>/dev/null)" ]]; then
    falha "container da API não encontrado (pilha de $rotulo fora do ar?)" \
          "docker compose -f $arquivo_compose up -d --wait"
else
    # printenv sai com 1 quando a variável não existe: isso é "sem token", não "sem container".
    token_no_container="$(docker compose exec -T api printenv TOKEN_ADMIN 2>/dev/null || true)"
    token_no_container="${token_no_container//[$'\r\n ']/}"   # o valor nunca é impresso
    if [[ -n "$token_no_container" ]]; then
        ok "TOKEN_ADMIN definido na API"
        # Pela URL pública, qualquer um pode tentar adivinhar o token do executar.
        if (( ${#token_no_container} < 24 )); then
            aviso "TOKEN_ADMIN tem só ${#token_no_container} caracteres (menos de 24): fácil de adivinhar" \
                  "gere um com $comando_novo_token, grave TOKEN_ADMIN=<valor> no .env e recrie a API (docker compose -f $arquivo_compose up -d)"
        fi
    else
        falha "TOKEN_ADMIN ausente ou vazio na API: /validacao/executar ficaria aberto" \
              "gere um com $comando_novo_token, grave TOKEN_ADMIN=<valor> no .env e recrie a API (docker compose -f $arquivo_compose up -d)"
    fi
    expor_docs="$(docker compose exec -T api printenv EXPOR_DOCS 2>/dev/null | tr -d '\r\n ' | tr 'A-Z' 'a-z' || true)"
    if [[ "$expor_docs" == "false" ]]; then
        # A variável sozinha não prova nada se a imagem for anterior à Task 8
        # (não lê EXPOR_DOCS): confere o efeito, /docs tem de dar 404.
        codigo_docs="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url_base/api/docs" || true)"
        if [[ "$codigo_docs" == "404" ]]; then
            ok "EXPOR_DOCS=false e /api/docs responde 404"
        else
            falha "EXPOR_DOCS=false, mas GET /api/docs respondeu ${codigo_docs:-sem resposta} (imagem antiga, sem EXPOR_DOCS?)" \
                  "docker compose -f $arquivo_compose pull && docker compose -f $arquivo_compose up -d (ou fixe uma versão: IMAGEM_TAG=sha-<7 caracteres do commit> no .env)"
        fi
    else
        falha "EXPOR_DOCS=${expor_docs:-<vazio>} (esperado false)" \
              "defina EXPOR_DOCS=false e recrie a API (docker compose -f $arquivo_compose up -d)"
    fi
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

echo "4. Relatos reais (funil real)"
# De quando são os relatos reais (aceitos + reprovados no estágio 1, os mesmos
# que formam `recebidos`), no horário de São Paulo (o TZ do compose): é o que
# separa "testes de antes da abertura" de "dias de coleta".
intervalo="$(docker compose exec -T db psql -X -q -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
    SELECT coalesce(to_char(min(em) AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'), '?'),
           coalesce(to_char(max(em) AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI'), '?')
    FROM (SELECT criado_em AS em FROM alertas WHERE origem = 'real'
          UNION ALL
          SELECT recebido_em FROM alertas_rejeitados WHERE origem = 'real') AS relatos" 2>/dev/null || true)"
IFS='|' read -r primeiro ultimo <<< "$intervalo"
de_quando="de ${primeiro:-?} a ${ultimo:-?} (horário de São Paulo)"
if estat="$(curl -fsS --max-time 10 "$url_base/api/validacao/estatisticas?origem=real" 2>/dev/null)"; then
    recebidos="$(sed -nE 's/.*"recebidos":([0-9]+).*/\1/p' <<< "$estat")"
    if [[ $reabrir -eq 1 ]]; then
        # Coleta em andamento: relato real é dado do TCC. Nada aqui sugere apagar.
        if [[ "$recebidos" == "0" ]]; then
            info "coleta em andamento, mas nenhum relato real no banco (recebidos = 0): se a coleta já recebeu relatos, o banco pode ter sido recriado; confira o backup do último dia antes de seguir"
        else
            info "coleta em andamento: ${recebidos:-?} relatos reais, $de_quando; são dados do TCC e ficam como estão"
        fi
    elif [[ "$recebidos" == "0" ]]; then
        ok "estatisticas?origem=real com recebidos = 0"
    else
        falha "há ${recebidos:-?} relatos reais, $de_quando" \
              "se a coleta AINDA NÃO FOI ABERTA, são testes: faça backup e zerar-real" \
              "  (./db/banco.sh ${flag_prod}backup && ./db/banco.sh ${flag_prod}zerar-real; confira contagem e datas; só então --sim-apagar-dados-reais)." \
              "Se a coleta já está em andamento, NÃO apague nada: rode $0 ${flag_dev}--reabrir"
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
for svc in api frontend; do
    cid="$(docker compose ps -q "$svc" 2>/dev/null)"
    if [[ -n "$cid" ]]; then
        read -r referencia id_imagem <<< "$(docker inspect --format '{{.Config.Image}} {{.Image}}' "$cid")"
        # O RepoDigest (ghcr.io/<dono>/<imagem>@sha256:...) identifica a imagem
        # PUBLICADA, a mesma em qualquer máquina que a puxe; o ID é só local. Imagem
        # construída na própria máquina (pilha de desenvolvimento, E2E) não veio de um
        # registro: conforme o armazenamento de imagens do Docker, ela não tem
        # RepoDigest (o `index` falha e fica registrado só o ID) ou tem um digest sem
        # o nome do registro (<imagem>@sha256:...).
        digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$id_imagem" 2>/dev/null || true)"
        info "imagem $svc: $referencia; ID $id_imagem; ${digest:-sem RepoDigest (construída localmente, não veio de um registro)}"
    fi
done

echo "6. Túnel HTTPS"
# Só vale a URL da subida ATUAL: um túnel parado (ou reiniciado) deixa nos logs a
# URL de antes, que já não existe. `ps` sem -a lista só containers rodando, e os
# logs são lidos a partir do instante em que o container rodando começou.
cid_tunel="$(docker compose --profile tunel ps -q tunel 2>/dev/null || true)"
if [[ -n "$cid_tunel" ]]; then
    desde="$(docker inspect --format '{{.State.StartedAt}}' "$cid_tunel" 2>/dev/null || true)"
    url_tunel="$(docker compose --profile tunel logs ${desde:+--since "$desde"} tunel 2>/dev/null \
        | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | grep -v '^https://api\.trycloudflare\.com$' | tail -1 || true)"
    if [[ -n "$url_tunel" ]]; then
        info "URL pública do túnel: $url_tunel   (confira no celular; some quando o túnel cair)"
    else
        info "túnel no ar, mas a URL ainda não apareceu nos logs: espere uns segundos e rode de novo"
    fi
else
    info "túnel inativo (profile tunel): sem HTTPS público; o celular não libera a geolocalização"
fi

# Um arquivo por execução, com a pilha, o modo e o horário no nome: o registro do
# primeiro dia não é sobrescrito pelo da reabertura, nem o da produção pelo do
# ensaio. REGISTRO_DIR só existe para o teste ponta a ponta não sujar a pasta real.
pasta_registro="${REGISTRO_DIR:-backend/scripts/saida}"
mkdir -p "$pasta_registro"
saida="$pasta_registro/coleta-$([[ "$modo_dev" == 1 ]] && echo dev || echo prod)$([[ $reabrir -eq 1 ]] && echo -reabrir)-$(date +%Y-%m-%d-%H%M%S).txt"
{
    echo "preparar-coleta ($rotulo$([[ $reabrir -eq 1 ]] && echo ", reabertura da coleta em andamento")) em $(date -Is)"
    echo "projeto do compose: ${COMPOSE_PROJECT_NAME:-o do $arquivo_compose}"
    echo "commit: $commit$sujo"
    echo "seeds sha256: $hash_seeds"
    printf '%s\n' "${relatorio[@]}"
    echo "resultado: $([[ $falhas -eq 0 ]] && echo PRONTO || echo "$falhas item(ns) com falha")$([[ $avisos -gt 0 ]] && echo ", $avisos aviso(s)")"
} > "$saida"
echo
echo "registro: $saida"
if [[ $falhas -eq 0 ]]; then
    ressalva=""; [[ $avisos -gt 0 ]] && ressalva=" (com $avisos aviso(s) acima: corrija se puder)"
    if [[ $reabrir -eq 1 ]]; then
        echo "PRONTO para reabrir: todos os itens conferem, e os relatos reais continuam no banco$ressalva."
    else
        echo "PRONTO: todos os itens conferem$ressalva."
    fi
else
    echo "NÃO ESTÁ PRONTO: $falhas item(ns) com falha (nada foi alterado)."
    exit 1
fi
