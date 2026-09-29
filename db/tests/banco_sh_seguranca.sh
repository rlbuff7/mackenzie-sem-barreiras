#!/usr/bin/env bash
# Testes de segurança do db/banco.sh (pilha de desenvolvimento no ar; só toca o
# banco de TESTE e uma pasta temporária, NUNCA a pasta backups/):
#   ./db/tests/banco_sh_seguranca.sh
#  1. as mensagens de recusa de `restaurar` e `zerar-real` carregam as opções
#     (--teste, --prod) e nomeiam o alvo certo;
#  2. restaurar bom funciona e dump corrompido aborta com o original intacto;
#  3. se a 2ª troca de nomes falha, o banco original é devolvido;
#  4. se a 1ª chamada da troca para NO MEIO (depois de fechar as conexões), o
#     original volta a aceitar conexões;
#  5. variável já exportada no shell vale mais que o .env (POSTGRES_DB=x ...).
set -uo pipefail
raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$raiz"
set -a; source .env; set +a
teste="${POSTGRES_DB}_teste"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export BACKUP_DIR="$tmp/backups"   # banco.sh backup grava aqui, não em backups/

falhas=0
igual() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FALHA $1: esperado '$3', veio '$2'"; falhas=$((falhas+1)); fi; }
contem() { if [[ "$2" == *"$3"* ]]; then echo "ok   $1"; else echo "FALHA $1: faltou '$3' em: $2"; falhas=$((falhas+1)); fi; }
nao_contem() { if [[ "$2" != *"$3"* ]]; then echo "ok   $1"; else echo "FALHA $1: não devia ter '$3'"; falhas=$((falhas+1)); fi; }
abortar() { echo "erro de pré-requisito: $1" >&2; exit 2; }
contar() { docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d "$teste" -c "SELECT count(*) FROM tipos_barreira" 2>&1; }
psql_teste() { docker compose exec -T db psql -q -U "$POSTGRES_USER" -d "$teste" -c "$1" > /dev/null; }

./db/banco.sh preparar-teste > /dev/null || abortar "preparar-teste falhou (a pilha de desenvolvimento está no ar?)"
./db/banco.sh --teste backup > /dev/null || abortar "backup do banco de teste falhou"
dump="$(ls -t "$BACKUP_DIR"/"${teste}"-*.dump 2>/dev/null | head -1)"
[[ -n "$dump" && -s "$dump" ]] || abortar "o backup não produziu um dump em $BACKUP_DIR"

echo "== 1. mensagens de recusa"
msg="$(./db/banco.sh --teste restaurar "$dump" 2>&1)"
contem "restaurar --teste: comando com --teste" "$msg" "banco.sh --teste restaurar $dump --sim-substituir-banco"
contem "restaurar --teste: alvo nomeado" "$msg" "Alvo: banco $teste da pilha de desenvolvimento"
nao_contem "restaurar --teste não sugere comando sem opção" "$msg" "banco.sh restaurar"
msg="$(./db/banco.sh --teste zerar-real 2>&1)"
contem "zerar-real --teste: comando com --teste" "$msg" "banco.sh --teste zerar-real --sim-apagar-dados-reais"
contem "zerar-real --teste: alvo nomeado" "$msg" "Alvo: banco $teste da pilha de desenvolvimento"
# --prod: a recusa sai antes de tocar qualquer banco (o compose de produção só interpola com TOKEN_ADMIN)
msg="$(TOKEN_ADMIN=x ./db/banco.sh --prod restaurar "$dump" 2>&1)"
contem "restaurar --prod: comando com --prod" "$msg" "banco.sh --prod restaurar"
contem "restaurar --prod: alvo de produção" "$msg" "da pilha de PRODUÇÃO"

echo "== 2. restaurar bom e dump corrompido"
psql_teste "INSERT INTO tipos_barreira(codigo,nome) VALUES ('zz','zz')" || abortar "INSERT de preparo falhou"
antes="$(contar)"
head -c 400 "$dump" > "$tmp/corrompido.dump"
./db/banco.sh --teste restaurar "$tmp/corrompido.dump" --sim-substituir-banco > /dev/null 2>&1
igual "corrompido aborta (rc)" "$?" "1"
igual "corrompido: original intacto" "$(contar)" "$antes"
./db/banco.sh --teste restaurar "$dump" --sim-substituir-banco > /dev/null 2>&1
igual "restauração boa volta ao estado do dump (rc)" "$?" "0"
igual "restauração boa: contagem do dump" "$(contar)" "$((antes-1))"

# Shim de `docker`: reescreve o psql da troca para simular falhas pontuais.
mkdir -p "$tmp/shim"
real_docker="$(command -v docker)"
cat > "$tmp/shim/docker" <<SHIM
#!/usr/bin/env bash
args=("\$@")
for i in "\${!args[@]}"; do
    case "\${args[\$i]}" in
        # 3: só o RENAME do temporário para o nome final
        "ALTER DATABASE ${teste}_restaurando RENAME TO ${teste}")
            [[ "\$MODO_SHIM" == segunda ]] && { echo "falha simulada (2a troca)" >&2; exit 1; } ;;
        # 4: o RENAME que afasta o original vira erro, DEPOIS de fechar as conexões
        "ALTER DATABASE ${teste} RENAME TO ${teste}_antigo_"*)
            [[ "\$MODO_SHIM" == primeira ]] && args[\$i]="SELECT 1/0" ;;
    esac
done
exec "$real_docker" "\${args[@]}"
SHIM
chmod +x "$tmp/shim/docker"

echo "== 3. falha na 2a troca devolve o original"
psql_teste "INSERT INTO tipos_barreira(codigo,nome) VALUES ('yy','yy')" || abortar "INSERT de preparo falhou"
antes="$(contar)"
MODO_SHIM=segunda PATH="$tmp/shim:$PATH" ./db/banco.sh --teste restaurar "$dump" --sim-substituir-banco > /dev/null 2>&1
igual "troca falha (rc)" "$?" "1"
igual "original devolvido com os dados" "$(contar)" "$antes"
sobras="$(docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '${teste}_%'")"
igual "sem bancos temporários sobrando" "$sobras" ""

echo "== 4. 1a chamada da troca para no meio: original reabre"
MODO_SHIM=primeira PATH="$tmp/shim:$PATH" ./db/banco.sh --teste restaurar "$dump" --sim-substituir-banco > /dev/null 2>&1
igual "1a chamada falha (rc)" "$?" "1"
igual "original aceita conexões e mantém os dados" "$(contar)" "$antes"
sobras="$(docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '${teste}_%'")"
igual "sem bancos temporários sobrando (4)" "$sobras" ""

echo "== 5. o shell tem prioridade sobre o .env"
msg="$(POSTGRES_DB=zz_nao_existe ./db/banco.sh --teste backup 2>&1)"
rc=$?
igual "backup com POSTGRES_DB do shell falha (rc)" "$([[ $rc -ne 0 ]] && echo diferente_de_0)" "diferente_de_0"
contem "backup usou o POSTGRES_DB do shell, não o do .env" "$msg" "zz_nao_existe_teste"

if [[ $falhas -eq 0 ]]; then echo "banco_sh_seguranca: todos os testes passaram"; else echo "banco_sh_seguranca: $falhas falha(s)"; exit 1; fi
