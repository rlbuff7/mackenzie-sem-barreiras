-- 003: parâmetros da última execução do pipeline, por origem (R14).
--
-- Aplicada por ./db/banco.sh migrar, dentro de uma transação.
-- IMUTÁVEL depois de aplicada: qualquer correção vira uma migration nova.
--
-- Por que existe (honestidade do resultado empírico, G10): o funil de validação
-- (GET /validacao/estatisticas) é a figura que o TCC apresenta como resultado, e ele
-- só pode ser lido junto com os parâmetros que o produziram. As contagens e os
-- status das barreiras refletem a ÚLTIMA execução do pipeline daquela origem, não
-- a configuração atual: o .env pode ter sido recalibrado depois, ou um script de
-- análise de sensibilidade pode ter confirmado uma execução com outros valores.
-- Se as estatísticas lessem os parâmetros da configuração, a figura poderia levar
-- parâmetros que não produziram aqueles números.
--
-- Por isso executar_pipeline (backend/app/validacao/pipeline.py) grava aqui, NA
-- MESMA TRANSAÇÃO da reconstrução, os parâmetros que de fato usou; e as
-- estatísticas leem daqui. Uma linha por origem: só a última execução importa,
-- porque cada execução reconstrói tudo do zero (D6).

CREATE TABLE IF NOT EXISTS execucoes_pipeline (
    origem           VARCHAR(12)      PRIMARY KEY
                     CHECK (origem IN ('real', 'simulacao')),
    -- Mesmas faixas que Configuracoes (backend/app/config.py) e executar_pipeline
    -- aceitam: eps em METROS (medido em srid_calculo), contagens a partir de 1.
    eps_metros       DOUBLE PRECISION NOT NULL CHECK (eps_metros > 0),
    min_pontos       INT              NOT NULL CHECK (min_pontos >= 1),
    min_confirmacoes INT              NOT NULL CHECK (min_confirmacoes >= 1),
    -- SRID em que o eps foi medido: sem ele, "eps_metros" não teria unidade garantida.
    srid_calculo     INT              NOT NULL,
    executado_em     TIMESTAMPTZ      NOT NULL DEFAULT now()
);
