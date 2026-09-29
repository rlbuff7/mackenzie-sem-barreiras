#!/usr/bin/env bash
# Testes de segurança do db/banco.sh (rodar na pilha de desenvolvimento, só toca
# o banco de TESTE): ./db/tests/banco_sh_seguranca.sh
#  1. as mensagens de recusa de `restaurar` e `zerar-real` carregam as opções
#     (--teste, --prod) e nomeiam o alvo certo;
#  2. um restaurar bom funciona e um dump corrompido aborta com o original intacto;
#  3. se a segunda troca de nomes falha, o banco original é devolvido.
set -uo pipefail
raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$raiz"
set -a; source .env; set +a
teste="${POSTGRES_DB}_teste"
falhas=0
confere() { if [[ "$2" == *"$3"* ]]; then echo "ok   $1"; else echo "FALHA $1: faltou '$3' em: $2"; falhas=$((falhas+1)); fi; }
nao_tem() { if [[ "$2" != *"$3"* ]]; then echo "ok   $1"; else echo "FALHA $1: não devia ter '$3'"; falhas=$((falhas+1)); fi; }
contar() { docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d "$teste" -c "SELECT count(*) FROM tipos_barreira"; }

./db/banco.sh preparar-teste > /dev/null
./db/banco.sh --teste backup > /dev/null
dump="$(ls -t backups/${teste}-*.dump | head -1)"

echo "== 1. mensagens de recusa"
msg="$(./db/banco.sh --teste restaurar "$dump" 2>&1)"
confere "restaurar --teste: comando com --teste" "$msg" "banco.sh --teste restaurar $dump --sim-substituir-banco"
confere "restaurar --teste: alvo nomeado" "$msg" "Alvo: banco $teste da pilha de desenvolvimento"
msg="$(./db/banco.sh --teste zerar-real 2>&1)"
confere "zerar-real --teste: comando com --teste" "$msg" "banco.sh --teste zerar-real --sim-apagar-dados-reais"
confere "zerar-real --teste: alvo nomeado" "$msg" "Alvo: banco $teste da pilha de desenvolvimento"
# --prod: o compose de produção só interpola com TOKEN_ADMIN; a recusa sai antes de tocar o banco
msg="$(TOKEN_ADMIN=x ./db/banco.sh --prod restaurar "$dump" 2>&1)"
confere "restaurar --prod: comando com --prod" "$msg" "banco.sh --prod restaurar"
confere "restaurar --prod: alvo de produção" "$msg" "da pilha de PRODUÇÃO"
nao_tem "restaurar --teste não sugere comando sem opção" "$(./db/banco.sh --teste restaurar "$dump" 2>&1)" "banco.sh restaurar"

echo "== 2. restaurar bom e dump corrompido"
docker compose exec -T db psql -q -U "$POSTGRES_USER" -d "$teste" -c "INSERT INTO tipos_barreira(codigo,nome) VALUES ('zz','zz')"
antes="$(contar)"
head -c 400 "$dump" > backups/corrompido.dump
./db/banco.sh --teste restaurar backups/corrompido.dump --sim-substituir-banco > /dev/null 2>&1
rc=$?
confere "corrompido aborta (rc 1)" "$rc" "1"
confere "corrompido: original intacto" "$(contar)" "$antes"
./db/banco.sh --teste restaurar "$dump" --sim-substituir-banco > /dev/null 2>&1
confere "restauração boa volta ao estado do dump" "$(contar)" "$((antes-1))"

echo "== 3. falha na segunda troca devolve o original"
docker compose exec -T db psql -q -U "$POSTGRES_USER" -d "$teste" -c "INSERT INTO tipos_barreira(codigo,nome) VALUES ('yy','yy')"
antes="$(contar)"
mkdir -p backups/.shim
real_docker="$(command -v docker)"
cat > backups/.shim/docker <<SHIM
#!/usr/bin/env bash
# Falha só o RENAME do temporário para o nome final.
if [[ "\$*" == *"RENAME TO ${teste}"* && "\$*" != *"_antigo_"* ]]; then echo "falha simulada" >&2; exit 1; fi
exec "$real_docker" "\$@"
SHIM
chmod +x backups/.shim/docker
PATH="$raiz/backups/.shim:$PATH" ./db/banco.sh --teste restaurar "$dump" --sim-substituir-banco > /dev/null 2>&1
rc=$?
confere "troca falha (rc 1)" "$rc" "1"
confere "original devolvido com os dados" "$(contar)" "$antes"
sobras="$(docker compose exec -T db psql -q -At -U "$POSTGRES_USER" -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '${teste}_%'")"
confere "sem bancos temporários sobrando" "[$sobras]" "[]"

rm -rf backups
[[ $falhas -eq 0 ]] && echo "banco_sh_seguranca: todos os testes passaram" || { echo "banco_sh_seguranca: $falhas falha(s)"; exit 1; }
