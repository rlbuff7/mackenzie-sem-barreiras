#!/usr/bin/env bash
# Teste ponta a ponta (E2E), M5: sobe uma pilha ISOLADA do docker compose
# (COMPOSE_PROJECT_NAME=msb-e2e, portas 55434/58000/58080, volume próprio),
# aplica migrations+seeds nela, roda o contrato inteiro da API por HTTP
# (backend/scripts/ponta_a_ponta.py), confere preparar-coleta.sh (normal e
# --reabrir) e zerar-real (sem confirmação) com os relatos reais que o teste
# deixou, e SEMPRE derruba a pilha isolada no fim — sucesso, falha ou Ctrl-C —
# sem tocar a pilha principal nem o banco dela.
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
    [[ -n "${registros:-}" ]] && rm -rf "$registros"
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

# C1 (banco recriado): --reabrir com o banco SEM relato real nunca pode dar PRONTO.
# Roda aqui, antes de o teste por HTTP gravar o primeiro relato; conferido mais abaixo.
registros="$(mktemp -d)"
saida_reabrir_vazio="$(REGISTRO_DIR="$registros" ./scripts/preparar-coleta.sh --dev --reabrir 2>&1)" \
    && rc_reabrir_vazio=0 || rc_reabrir_vazio=$?

echo "== rodando o teste ponta a ponta por HTTP =="
(
    cd backend
    uv run python -m scripts.ponta_a_ponta \
        "http://localhost:${API_PORTA_HOST}" \
        "http://localhost:${FRONTEND_PORTA_HOST}"
)

# C1: com relatos reais no banco (os que o teste acima gravou pela API), nenhum
# script de operação pode induzir a apagá-los numa coleta em andamento. Tudo aqui
# só LÊ: preparar-coleta nunca altera nada, e zerar-real roda SEM a confirmação.
# preparar-coleta e banco.sh preservam do shell COMPOSE_PROJECT_NAME e *_PORTA_HOST
# (lista permitida, R35), então falam com esta pilha isolada.
echo
echo "== preparar-coleta e zerar-real com os relatos reais que ficaram na pilha isolada =="
falhas_operacao=0
conferir() {   # conferir "descrição" comando [argumentos...]
    local descricao="$1"
    shift
    if "$@"; then
        echo "[ok] $descricao"
    else
        echo "[FALHA] $descricao"
        falhas_operacao=$((falhas_operacao + 1))
    fi
}
contem() { [[ "$1" == *"$2"* ]]; }
nao_contem() { [[ "$1" != *"$2"* ]]; }
casa() { [[ "$1" =~ $2 ]]; }
recebidos_reais() {
    curl -fsS "http://localhost:${FRONTEND_PORTA_HOST}/api/validacao/estatisticas?origem=real" \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["alertas"]["recebidos"])'
}
dh='[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}'

conferir "preparar-coleta --reabrir com o banco sem relatos reais não fica PRONTO (rc 1)" \
    test "$rc_reabrir_vazio" -eq 1
conferir "preparar-coleta --reabrir com o banco vazio manda restaurar o último backup" \
    contem "$saida_reabrir_vazio" "restaure o backup dev-*.dump mais recente"
conferir "preparar-coleta --reabrir com o banco vazio não diz que os relatos continuam no banco" \
    nao_contem "$saida_reabrir_vazio" "PRONTO para reabrir"
conferir "preparar-coleta --reabrir com o banco vazio nunca sugere zerar-real" \
    nao_contem "$saida_reabrir_vazio" "zerar-real"
conferir "preparar-coleta --reabrir com o banco vazio nunca sugere pull" \
    nao_contem "$saida_reabrir_vazio" ".yml pull"

recebidos_antes="$(recebidos_reais)"
conferir "a pilha isolada tem relatos reais para conferir (recebidos = $recebidos_antes)" \
    test "$recebidos_antes" -gt 0

saida="$(REGISTRO_DIR="$registros" ./scripts/preparar-coleta.sh --dev 2>&1)" && rc=0 || rc=$?
conferir "preparar-coleta (antes da abertura) com relatos reais não fica PRONTO (rc 1)" test "$rc" -eq 1
conferir "preparar-coleta diz quantos relatos reais há e de quando" \
    casa "$saida" "há $recebidos_antes relatos reais, de $dh a $dh"
conferir "preparar-coleta separa 'coleta ainda não aberta' de 'coleta em andamento'" \
    contem "$saida" "AINDA NÃO FOI ABERTA"
conferir "preparar-coleta manda a coleta em andamento para --reabrir" \
    contem "$saida" "preparar-coleta.sh --dev --reabrir"

saida="$(REGISTRO_DIR="$registros" ./scripts/preparar-coleta.sh --dev --reabrir 2>&1)" && rc=0 || rc=$?
conferir "preparar-coleta --reabrir informa os relatos reais e o intervalo de datas" \
    casa "$saida" "coleta em andamento: $recebidos_antes relatos reais, de $dh a $dh"
conferir "preparar-coleta --reabrir nunca sugere zerar-real" nao_contem "$saida" "zerar-real"
conferir "preparar-coleta --reabrir nunca sugere pull no meio da coleta" nao_contem "$saida" ".yml pull"
if [[ -n "${TOKEN_ADMIN:-}" && "${EXPOR_DOCS:-true}" == [Ff][Aa][Ll][Ss][Ee] ]]; then
    # Configuração da coleta (token e docs fechados): tudo confere e fica PRONTO.
    conferir "preparar-coleta --reabrir com a configuração da coleta fica PRONTO (rc 0)" test "$rc" -eq 0
    if (( ${#TOKEN_ADMIN} < 24 )); then
        conferir "token com menos de 24 caracteres gera aviso" contem "$saida" "[AVISO]  TOKEN_ADMIN tem só"
    else
        conferir "token longo não gera aviso" nao_contem "$saida" "[AVISO]"
    fi
else
    conferir "preparar-coleta --reabrir sem token ou com docs abertos não fica PRONTO (rc 1)" test "$rc" -eq 1
fi
conferir "um registro por execução (nenhum sobrescreveu o outro)" \
    test "$(find "$registros" -name 'coleta-dev-*.txt' | wc -l)" -eq 3

saida="$(./db/banco.sh zerar-real 2>&1)" && rc=0 || rc=$?
conferir "zerar-real sem confirmação recusa (rc 1)" test "$rc" -eq 1
conferir "zerar-real mostra quantos relatos reais serão apagados e de quando" \
    casa "$saida" "relatos reais: $recebidos_antes \\([0-9]+ aceitos \\+ [0-9]+ reprovados no [^)]*\\), de $dh a $dh"
conferir "zerar-real avisa que coleta já aberta não se apaga" contem "$saida" "NÃO apague"
conferir "nada foi apagado (recebidos continua $recebidos_antes)" test "$(recebidos_reais)" -eq "$recebidos_antes"
rm -rf "$registros"

if (( falhas_operacao > 0 )); then
    echo "ponta a ponta: $falhas_operacao falha(s) nos scripts de operação" >&2
    exit 1
fi
echo "ponta a ponta: scripts de operação conferidos"
