-- 007: nova condição 'entrada_predio' ("Entrada de prédio" dos pontos P04..P06 do
-- Maurício, docs/medicao-gps.md), distinta de 'coberto' para não misturar condições
-- na análise de erro do GPS. As migrations 005 e 006 já foram aplicadas e são
-- imutáveis: aqui só se trocam as duas CHECK de condição, com os mesmos nomes.
-- A API/app precisam aceitar o valor novo (backend/app/schemas/medicao.py e o
-- frontend); até lá o banco aceita, mas o POST /medicoes rejeita com 422.

ALTER TABLE medicoes_gps DROP CONSTRAINT IF EXISTS medicoes_gps_condicao_valida;
ALTER TABLE medicoes_gps ADD CONSTRAINT medicoes_gps_condicao_valida
    CHECK (condicao IN ('ceu_aberto', 'entre_predios', 'coberto', 'entrada_predio'));

ALTER TABLE pontos_controle DROP CONSTRAINT IF EXISTS pontos_controle_condicao_valida;
ALTER TABLE pontos_controle ADD CONSTRAINT pontos_controle_condicao_valida
    CHECK (condicao IN ('ceu_aberto', 'entre_predios', 'coberto', 'entrada_predio'));
