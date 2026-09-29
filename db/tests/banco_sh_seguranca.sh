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
#  5. POSTGRES_DB/USER/PASSWORD do shell NÃO valem sobre o .env (aviso em stderr);
#     a lista permitida (ex.: BACKUP_DIR) vale;
#  6. zerar-real (sem e com a confirmação) mostra quantos relatos reais serão
#     apagados e de que data a que data, e manda para --reabrir quem já abriu a coleta;
#  7. o backup diz de que pilha veio (nome e "Alvo:"); restaurar recusa um dump de
#     outra pilha (ou de pilha desconhecida) sem --sim-pilha-diferente; no --prod o
#     banco anterior fica guardado.
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
saida_backup="$(./db/banco.sh --teste backup)" || abortar "backup do banco de teste falhou"
dump="$(ls -t "$BACKUP_DIR"/teste-"${teste}"-*.dump 2>/dev/null | head -1)"
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
contem "restaurar --prod de um dump de teste: avisa a pilha diferente" "$msg" "--sim-substituir-banco --sim-pilha-diferente"

echo "== 2. restaurar bom e dump corrompido"
psql_teste "INSERT INTO tipos_barreira(codigo,nome) VALUES ('zz','zz')" || abortar "INSERT de preparo falhou"
antes="$(contar)"
# Nome com o prefixo da pilha certa: a recusa tem de vir do pg_restore --list, não
# da conferência da pilha.
head -c 400 "$dump" > "$tmp/teste-corrompido.dump"
msg="$(./db/banco.sh --teste restaurar "$tmp/teste-corrompido.dump" --sim-substituir-banco 2>&1)"
igual "corrompido aborta (rc)" "$?" "1"
contem "corrompido: recusado pela validação do dump" "$msg" "não é um dump válido"
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

echo "== 5. POSTGRES_* do shell não vencem o .env"
msg="$(POSTGRES_DB=postgres ./db/banco.sh --teste backup 2>&1)"
rc=$?
igual "backup com POSTGRES_DB=postgres no shell segue (rc)" "$rc" "0"
contem "aviso nomeia POSTGRES_DB" "$msg" "aviso: POSTGRES_DB está exportado no shell"
nao_contem "backup não tocou o banco postgres" "$msg" "postgres-"
contem "backup gravou o dump do banco _teste" "$(ls "$BACKUP_DIR")" "${teste}-"
msg="$(POSTGRES_PASSWORD=outra-senha-secreta ./db/banco.sh --teste backup 2>&1)"
contem "aviso nomeia POSTGRES_PASSWORD" "$msg" "aviso: POSTGRES_PASSWORD"
nao_contem "aviso não mostra o valor da senha" "$msg" "outra-senha-secreta"
msg="$(POSTGRES_DB="$POSTGRES_DB" ./db/banco.sh --teste backup 2>&1)"
nao_contem "sem aviso quando o valor é igual ao do .env" "$msg" "aviso:"

echo "== 6. zerar-real diz quantos relatos reais e de quando"
# Relatos reais SIMULADOS no banco de TESTE, com datas conhecidas (horário de São Paulo).
psql_teste "INSERT INTO alertas (geom, tipo_id, sessao_hash, criado_em, origem)
    SELECT ST_SetSRID(ST_MakePoint(-46.6524631, -23.5471938), 4326), id, repeat('a', 64), t, 'real'
    FROM tipos_barreira, (VALUES (timestamptz '2026-10-01 09:15:00-03'), ('2026-10-02 17:40:00-03')) AS d(t)
    WHERE codigo = 'degrau'" || abortar "INSERT dos alertas reais de teste falhou"
psql_teste "INSERT INTO alertas_rejeitados (payload, erros, recebido_em, origem)
    VALUES ('{}', '[]', '2026-10-01 10:00:00-03', 'real')" || abortar "INSERT do rejeitado real de teste falhou"
resumo_esperado="relatos reais: 3 (2 aceitos + 1 reprovados no estágio 1), de 01/10/2026 09:15 a 02/10/2026 17:40"
msg="$(./db/banco.sh --teste zerar-real 2>&1)"
igual "zerar-real sem confirmação (rc)" "$?" "1"
contem "dry-run: contagem e intervalo de datas" "$msg" "$resumo_esperado"
contem "dry-run: coleta já aberta = não apague" "$msg" "NÃO apague"
contem "dry-run: aponta o --reabrir" "$msg" "preparar-coleta.sh --reabrir"
reais() { docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d "$teste" -c "SELECT (SELECT count(*) FROM alertas WHERE origem = 'real') + (SELECT count(*) FROM alertas_rejeitados WHERE origem = 'real')" 2>&1; }
igual "dry-run não apagou nada" "$(reais)" "3"
msg="$(./db/banco.sh --teste zerar-real --sim-apagar-dados-reais 2>&1)"
igual "zerar-real com confirmação (rc)" "$?" "0"
contem "confirmação: contagem e datas antes de apagar" "$msg" "apagando do banco $teste: $resumo_esperado"
igual "confirmação apagou os relatos reais do banco de teste" "$(reais)" "0"

echo "== 7. backups dizem de que pilha vieram"
casa() { if [[ "$2" =~ $3 ]]; then echo "ok   $1"; else echo "FALHA $1: '$2' não casa com '$3'"; falhas=$((falhas+1)); fi; }
casa "nome do backup: teste-<banco>-<data>.dump" "$(basename "$dump")" "^teste-${teste}-[0-9]{8}-[0-9]{6}\.dump$"
contem "backup imprime o alvo" "$saida_backup" "Alvo: banco $teste da pilha de desenvolvimento"
bancos_de_sobra() { docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '${teste}_%' ORDER BY 1"; }
antes="$(contar)"
cp "$dump" "$tmp/dev-${teste}-20260101-000000.dump"
msg="$(./db/banco.sh --teste restaurar "$tmp/dev-${teste}-20260101-000000.dump" --sim-substituir-banco 2>&1)"
igual "dump do dev no banco de teste: recusado sem --sim-pilha-diferente (rc)" "$?" "1"
contem "recusa nomeia a pilha do arquivo e a do alvo" "$msg" "backup da pilha dev (pelo nome); o alvo é da pilha teste"
contem "recusa sugere --sim-pilha-diferente" "$msg" "--sim-substituir-banco --sim-pilha-diferente"
igual "recusa por pilha: banco intacto" "$(contar)" "$antes"
cp "$dump" "$tmp/sem-prefixo.dump"
msg="$(./db/banco.sh --teste restaurar "$tmp/sem-prefixo.dump" --sim-substituir-banco 2>&1)"
igual "dump sem pilha no nome: recusado sem --sim-pilha-diferente (rc)" "$?" "1"
contem "recusa diz que a pilha é desconhecida" "$msg" "pilha de origem DESCONHECIDA"
./db/banco.sh --teste restaurar "$tmp/sem-prefixo.dump" --sim-substitui 2>/dev/null
igual "argumento desconhecido no restaurar (rc)" "$?" "2"
./db/banco.sh --teste restaurar "$tmp/dev-${teste}-20260101-000000.dump" --sim-substituir-banco --sim-pilha-diferente > /dev/null 2>&1
igual "com --sim-pilha-diferente restaura (rc)" "$?" "0"
igual "sem bancos temporários sobrando (7)" "$(bancos_de_sobra)" ""
# --prod guarda o antigo. O compose de produção é usado com o NOME DE PROJETO da
# pilha de desenvolvimento, para o `exec` cair no container db que já está no ar;
# com --teste, o alvo continua sendo só o banco de teste.
projeto_dev="$(docker compose config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["name"])')"
msg="$(TOKEN_ADMIN=x COMPOSE_PROJECT_NAME="$projeto_dev" ./db/banco.sh --prod --teste restaurar "$dump" --sim-substituir-banco 2>&1)"
igual "restaurar --prod (rc)" "$?" "0"
contem "--prod: diz que o anterior NÃO foi apagado" "$msg" "NÃO foi apagado: ficou guardado como ${teste}_antigo_"
contem "--prod: explica como apagar o guardado" "$msg" "banco.sh --prod --teste psql      e, no psql:  DROP DATABASE ${teste}_antigo_"
guardado="$(bancos_de_sobra)"
casa "--prod: o banco anterior continua existindo" "$guardado" "^${teste}_antigo_[0-9]{14}$"
[[ "$guardado" =~ ^${teste}_antigo_[0-9]{14}$ ]] && docker compose exec -T db psql -q -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE ${guardado}" > /dev/null
igual "banco guardado apagado no fim do teste" "$(bancos_de_sobra)" ""

if [[ $falhas -eq 0 ]]; then echo "banco_sh_seguranca: todos os testes passaram"; else echo "banco_sh_seguranca: $falhas falha(s)"; exit 1; fi
