#!/usr/bin/env bash
# Auto-atualização por PULL, rodada no servidor pelo timer msb-atualizar (systemd).
# Baixa as imagens do GHCR (tag IMAGEM_TAG, padrão latest); se alguma mudou em relação
# ao que está rodando: git pull --ff-only, `up -d`, migrações e teste de saúde. Se a
# saúde (ou a migração) falhar, volta para as imagens que estavam rodando antes.
# Sem mudança, não faz nada. Nunca imprime o .env (sem `set -x`).
#
# O "digest" comparado é o ID da imagem (sha256 do manifesto de configuração), que muda
# a cada publicação nova. Uma versão que falhou fica marcada e NÃO é tentada de novo
# até o CI publicar outra (senão o servidor ficaria em ciclo de falha a cada 5 min).
#
# Variáveis (todas opcionais; os testes em deploy/aws/testes/ trocam estas):
#   DIR_REPO        checkout do repositório      (padrão ~/mackenzie-sem-barreiras)
#   IMAGEM_TAG      tag das imagens              (padrão latest)
#   URL_SAUDE       sonda de saúde               (padrão http://127.0.0.1:8091/api/saude)
#   TENTATIVAS_SAUDE / ESPERA_SAUDE   quantas vezes / segundos entre elas (padrão 18 x 5 s)
#   DIR_ESTADO, ARQ_LOCK            onde guardar a marca de versão ruim e o lock
set -euo pipefail

main() {
    local repo="${DIR_REPO:-$HOME/mackenzie-sem-barreiras}"
    local tag="${IMAGEM_TAG:-latest}"
    local url_saude="${URL_SAUDE:-http://127.0.0.1:${FRONTEND_PORTA_PROD:-8091}/api/saude}"
    local tentativas="${TENTATIVAS_SAUDE:-18}"
    local espera="${ESPERA_SAUDE:-5}"
    local estado="${DIR_ESTADO:-$HOME/.local/state/msb-atualizar}"
    local lock="${ARQ_LOCK:-/tmp/msb-atualizar.lock}"
    local servicos=(api frontend)
    local -A ref=(
        [api]="ghcr.io/rlbuff7/mackenzie-sem-barreiras-api:$tag"
        [frontend]="ghcr.io/rlbuff7/mackenzie-sem-barreiras-frontend:$tag"
    )
    local -A antes=() depois=()
    local s

    log() { echo "msb-atualizar: $*"; }
    compose() { docker compose -f "$repo/docker-compose.prod.yml" --project-directory "$repo" "$@" </dev/null; }
    id_rodando() {  # ID da imagem do contêiner em execução ("" se não há)
        local c
        c="$(compose ps -q "$1" 2>/dev/null | head -n 1 || true)"
        [[ -n "$c" ]] && docker inspect --format '{{.Image}}' "$c" 2>/dev/null || true
    }
    id_local() { docker image inspect --format '{{.Id}}' "${ref[$1]}" 2>/dev/null || true; }
    esta_saudavel() {
        local i corpo
        for ((i = 1; i <= tentativas; i++)); do
            corpo="$(curl -fsS --max-time 5 "$url_saude" 2>/dev/null || true)"
            [[ "$corpo" == *'"status":"ok"'* && "$corpo" == *'"banco":"ok"'* ]] && return 0
            ((i < tentativas)) && sleep "$espera"
        done
        return 1
    }
    voltar_atras() {
        log "ROLLBACK para as imagens anteriores"
        for s in "${servicos[@]}"; do
            if [[ -n "${antes[$s]}" ]]; then
                docker tag "${antes[$s]}" "${ref[$s]}"
            fi
        done
        compose up -d --no-deps --pull never "${servicos[@]}" || log "ERRO: rollback falhou, intervenção manual"
        if esta_saudavel; then log "rollback ok, saúde restaurada"; else log "ERRO: saúde NÃO voltou após o rollback"; fi
    }

    mkdir -p "$estado"
    exec 9>"$lock"
    flock -n 9 || { log "já há outra execução, saindo"; return 0; }

    [[ -f "$repo/docker-compose.prod.yml" ]] || { log "ERRO: $repo/docker-compose.prod.yml não existe"; return 1; }

    for s in "${servicos[@]}"; do antes[$s]="$(id_rodando "$s")"; done

    compose pull --quiet "${servicos[@]}" || { log "pull falhou (sem rede ou GHCR fora); tento no próximo ciclo"; return 0; }

    local mudou=0 marca=""
    for s in "${servicos[@]}"; do
        depois[$s]="$(id_local "$s")"
        marca+="${depois[$s]};"
        [[ "${depois[$s]}" != "${antes[$s]}" ]] && mudou=1
    done
    if ((mudou == 0)); then
        return 0  # nada novo: silêncio, para não encher o journal a cada 5 min
    fi

    if [[ -f "$estado/versao-ruim" && "$(cat "$estado/versao-ruim")" == "$marca" ]]; then
        # o pull moveu a tag para a versão que já falhou: devolve a tag à que roda
        for s in "${servicos[@]}"; do
            [[ -n "${antes[$s]}" ]] && docker tag "${antes[$s]}" "${ref[$s]}"
        done
        return 0
    fi

    log "imagens novas no GHCR (tag $tag); atualizando"
    if ! git -C "$repo" pull --ff-only --quiet </dev/null; then
        log "ERRO: git pull --ff-only falhou; nada foi alterado no servidor"
        for s in "${servicos[@]}"; do
            [[ -n "${antes[$s]}" ]] && docker tag "${antes[$s]}" "${ref[$s]}"
        done
        return 1
    fi

    local falhou=""
    compose up -d --no-deps --pull never "${servicos[@]}" || falhou="up"
    if [[ -z "$falhou" ]]; then
        (cd "$repo" && ./db/banco.sh --prod migrar </dev/null >/dev/null) || falhou="migração"
    fi
    if [[ -z "$falhou" ]] && ! esta_saudavel; then falhou="saúde"; fi

    if [[ -n "$falhou" ]]; then
        log "ERRO: falha em '$falhou'; versão marcada como ruim"
        echo "$marca" >"$estado/versao-ruim"
        voltar_atras
        return 1
    fi
    rm -f "$estado/versao-ruim"
    log "atualizado e saudável (api ${depois[api]:7:12}, frontend ${depois[frontend]:7:12})"
}

# Uma linha só: o bash já leu a função inteira antes de executar, então o git pull
# trocar este arquivo no meio da execução não corrompe a leitura.
main "$@"; exit $?
