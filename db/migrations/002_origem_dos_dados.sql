-- 002: origem dos dados — real vs. simulação (D2, G10).
--
-- Aplicada por ./db/banco.sh migrar, dentro de uma transação.
-- IMUTÁVEL depois de aplicada: qualquer correção vira uma migration nova.
--
-- D2 (globais.md): toda linha de alertas, alertas_rejeitados e barreiras carrega
-- a origem do dado. Pela HTTP a origem é sempre 'real'; só o gerador de dados
-- sintéticos (a partir do M3) grava 'simulacao', chamando a mesma função de
-- entrada que a API usa — nunca inserção direta.
--
-- G10 (honestidade acadêmica): dado sintético tem sempre origem='simulacao' e é
-- rotulado "SIMULAÇÃO" em toda saída, log ou gráfico. O pipeline de validação
-- nunca mistura as duas origens (cada execução processa uma origem por vez).

ALTER TABLE alertas
    ADD COLUMN IF NOT EXISTS origem VARCHAR(12) NOT NULL DEFAULT 'real';

ALTER TABLE alertas_rejeitados
    ADD COLUMN IF NOT EXISTS origem VARCHAR(12) NOT NULL DEFAULT 'real';

ALTER TABLE barreiras
    ADD COLUMN IF NOT EXISTS origem VARCHAR(12) NOT NULL DEFAULT 'real';

-- DROP + ADD para a migration continuar idempotente (CLAUDE.md §10) mesmo que
-- seja reaplicada manualmente contra um banco que já tenha a constraint.
ALTER TABLE alertas
    DROP CONSTRAINT IF EXISTS alertas_origem_valida,
    ADD CONSTRAINT alertas_origem_valida CHECK (origem IN ('real', 'simulacao'));

ALTER TABLE alertas_rejeitados
    DROP CONSTRAINT IF EXISTS alertas_rejeitados_origem_valida,
    ADD CONSTRAINT alertas_rejeitados_origem_valida CHECK (origem IN ('real', 'simulacao'));

ALTER TABLE barreiras
    DROP CONSTRAINT IF EXISTS barreiras_origem_valida,
    ADD CONSTRAINT barreiras_origem_valida CHECK (origem IN ('real', 'simulacao'));

-- Estatísticas do funil (GET /validacao/estatisticas) e o pipeline (D6) sempre
-- filtram por origem e cruzam com status: atende as duas colunas juntas.
CREATE INDEX IF NOT EXISTS idx_alertas_origem_status ON alertas (origem, status);
