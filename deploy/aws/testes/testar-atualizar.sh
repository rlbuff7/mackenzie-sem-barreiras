#!/usr/bin/env bash
# Testa deploy/aws/atualizar-se-mudou.sh SEM AWS, SEM Docker e SEM rede: docker, curl e
# git são stubs num PATH temporário que simulam GHCR, contêineres e a sonda de saúde.
#   bash deploy/aws/testes/testar-atualizar.sh
# Cenários: sem mudança; mudança + saúde ok; mudança + saúde falha (rollback, versão
# marcada ruim e não repetida); falha de git pull; lock ocupado.
set -euo pipefail
aqui="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$aqui/../atualizar-se-mudou.sh"
falhas=0

novo_ambiente() {
    T="$(mktemp -d)"; mkdir -p "$T/bin" "$T/repo/db"
    : >"$T/repo/docker-compose.prod.yml"
    printf '#!/bin/bash\necho "banco $*" >>"%s/chamadas"\n' "$T" >"$T/repo/db/banco.sh"
    chmod +x "$T/repo/db/banco.sh"
    for s in api frontend; do
        echo "sha256:${s}-v1" >"$T/local_$s"; echo "sha256:${s}-v1" >"$T/run_$s"
        echo "sha256:${s}-v1" >"$T/remote_$s"
    done
    : >"$T/chamadas"
    cat >"$T/bin/docker" <<'STUB'
#!/bin/bash
T="$STUB_DIR"
svc_de() { [[ "$1" == *-api:* ]] && echo api || echo frontend; }
case "$1" in
  image) cat "$T/local_$(svc_de "$5")" ;;  # image inspect --format F REF
  inspect) cat "$T/run_${4#c_}" ;;                       # inspect --format F c_<svc>
  tag) echo "tag $2 $3" >>"$T/chamadas"; echo "$2" >"$T/local_$(svc_de "$3")" ;;
  compose)
    shift; while [[ "$1" == -f || "$1" == --project-directory ]]; do shift 2; done
    case "$1" in
      pull) echo pull >>"$T/chamadas"; [[ -f "$T/sem_rede" ]] && exit 1
            for s in api frontend; do cp "$T/remote_$s" "$T/local_$s"; done ;;
      ps) echo "c_${@: -1}" ;;
      up) echo "up $*" >>"$T/chamadas"
          for s in api frontend; do cp "$T/local_$s" "$T/run_$s"; done ;;
    esac ;;
esac
STUB
    cat >"$T/bin/curl" <<'STUB'
#!/bin/bash
# saudável só se a api rodando NÃO é a versão quebrada
if [[ "$(cat "$STUB_DIR/run_api")" == *quebrada* ]]; then exit 22; fi
echo '{"status":"ok","banco":"ok"}'
STUB
    cat >"$T/bin/git" <<'STUB'
#!/bin/bash
echo "git $*" >>"$STUB_DIR/chamadas"; [[ -f "$STUB_DIR/git_falha" ]] && exit 1; exit 0
STUB
    chmod +x "$T/bin/"*
}

rodar() {  # saída em $T/saida, código em $T/codigo
    local cod=0
    STUB_DIR="$T" PATH="$T/bin:$PATH" DIR_REPO="$T/repo" DIR_ESTADO="$T/estado" \
        ARQ_LOCK="$T/lock" TENTATIVAS_SAUDE=2 ESPERA_SAUDE=0 \
        bash "$script" >"$T/saida" 2>&1 || cod=$?
    echo "$cod" >"$T/codigo"
}

confere() {  # confere "descrição" comando...
    local d="$1"; shift
    if "$@"; then echo "  ok   $d"; else echo "  FALHA $d"; falhas=$((falhas + 1)); fi
}
tem() { grep -q -- "$1" "$T/$2"; }
nao_tem() { ! grep -q -- "$1" "$T/$2"; }
cod_e() { [[ "$(cat "$T/codigo")" == "$1" ]]; }

echo "1) sem mudança: não faz nada"
novo_ambiente; rodar
confere "sai 0" cod_e 0
confere "não sobe nada" nao_tem '^up' chamadas
confere "não roda git nem migração" nao_tem '^git\|^banco' chamadas
confere "não escreve log" test ! -s "$T/saida"

echo "2) mudança + saúde ok"
novo_ambiente; echo "sha256:api-v2" >"$T/remote_api"; echo "sha256:frontend-v2" >"$T/remote_frontend"; rodar
confere "sai 0" cod_e 0
confere "git pull --ff-only" tem 'git .*pull --ff-only' chamadas
confere "up sem pull" tem '^up .*--pull never' chamadas
confere "migra com --prod" tem 'banco --prod migrar' chamadas
confere "log diz atualizado" tem 'atualizado e saudável' saida
confere "sem rollback" nao_tem ROLLBACK saida
confere "sem marca de versão ruim" test ! -f "$T/estado/versao-ruim"

echo "3) mudança + saúde falha: rollback"
novo_ambiente; echo "sha256:api-quebrada" >"$T/remote_api"; echo "sha256:frontend-v2" >"$T/remote_frontend"; rodar
confere "sai 1" cod_e 1
confere "log diz ROLLBACK" tem ROLLBACK saida
confere "recoloca a tag da api anterior" tem 'tag sha256:api-v1 ' chamadas
confere "recoloca a tag do frontend anterior" tem 'tag sha256:frontend-v1 ' chamadas
confere "api volta a rodar a v1" grep -qx 'sha256:api-v1' "$T/run_api"
confere "saúde restaurada" tem 'rollback ok' saida
confere "versão marcada como ruim" test -f "$T/estado/versao-ruim"
echo "3b) próximo ciclo com a mesma versão ruim: não tenta de novo"
: >"$T/chamadas"; rodar
confere "sai 0" cod_e 0
confere "não sobe nada" nao_tem '^up' chamadas
confere "devolve a tag à versão que roda" tem 'tag sha256:api-v1 ' chamadas
echo "3c) o CI publica outra versão boa: atualiza e limpa a marca"
echo "sha256:api-v3" >"$T/remote_api"; : >"$T/chamadas"; rodar
confere "sai 0" cod_e 0
confere "log diz atualizado" tem 'atualizado e saudável' saida
confere "marca removida" test ! -f "$T/estado/versao-ruim"

echo "4) git pull falha: não mexe nos contêineres"
novo_ambiente; echo "sha256:api-v2" >"$T/remote_api"; touch "$T/git_falha"; rodar
confere "sai 1" cod_e 1
confere "não sobe" nao_tem '^up' chamadas
confere "tag devolvida" tem 'tag sha256:api-v1 ' chamadas

echo "5) GHCR/rede fora: sai 0 sem alterar"
novo_ambiente; touch "$T/sem_rede"; rodar
confere "sai 0" cod_e 0
confere "não sobe" nao_tem '^up' chamadas

echo "6) lock ocupado: não roda duas vezes"
novo_ambiente; echo "sha256:api-v2" >"$T/remote_api"
( exec 9>"$T/lock"; flock -n 9; rodar; sleep 0 )
confere "sai 0" cod_e 0
confere "diz que há outra execução" tem 'outra execução' saida
confere "não faz pull" nao_tem '^pull' chamadas

echo "7) o .env nunca é lido pelo script"
confere "sem 'cat .env' nem 'set -x'" bash -c "! grep -v '^ *#' '$script' | grep -E 'set -x|cat .*\\.env|source .*\\.env'"

echo
if ((falhas)); then echo "FALHARAM $falhas verificação(ões)"; exit 1; fi
echo "tudo certo"
