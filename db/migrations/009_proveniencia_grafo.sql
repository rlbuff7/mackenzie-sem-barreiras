-- 009: proveniência do mapeamento do campus (dado de pesquisa, CLAUDE.md §17).
--
-- Registra, por aresta e por ponto de interesse, QUEM mapeou, QUANDO e com que grau de
-- verificação:
--   conferido_a_pe = a equipe percorreu o trecho;
--   imagem         = desenhado sobre mapa/satélite, ainda não conferido a pé
--                    (recebe PENALIDADE_TRECHO_NAO_VERIFICADO na rota);
--   provisorio     = grafo de desenvolvimento (ex.: importado do OpenStreetMap) ou
--                    esquemático; a API devolve o rótulo PROVISÓRIO.
-- Isto é diferente de acessivel_cadeirante: acessibilidade e verificação são coisas
-- distintas (NULL em acessivel_cadeirante = "não verificado" só para acessibilidade).
--
-- As listas de valores são CHECK constraints nomeadas (padrão da 004): mudar a lista
-- exige uma migration nova.

ALTER TABLE arestas
    ADD COLUMN IF NOT EXISTS fonte_verificacao VARCHAR(16) NOT NULL DEFAULT 'imagem',
    ADD COLUMN IF NOT EXISTS mapeado_por VARCHAR(60),
    ADD COLUMN IF NOT EXISTS mapeado_em DATE;

ALTER TABLE pontos_interesse
    ADD COLUMN IF NOT EXISTS fonte_verificacao VARCHAR(16) NOT NULL DEFAULT 'imagem',
    ADD COLUMN IF NOT EXISTS mapeado_por VARCHAR(60),
    ADD COLUMN IF NOT EXISTS mapeado_em DATE;

-- ADD CONSTRAINT não tem IF NOT EXISTS: confere em pg_constraint para reaplicar sem erro.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'arestas_fonte_valida') THEN
        ALTER TABLE arestas ADD CONSTRAINT arestas_fonte_valida
            CHECK (fonte_verificacao IN ('conferido_a_pe', 'imagem', 'provisorio'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pontos_interesse_fonte_valida') THEN
        ALTER TABLE pontos_interesse ADD CONSTRAINT pontos_interesse_fonte_valida
            CHECK (fonte_verificacao IN ('conferido_a_pe', 'imagem', 'provisorio'));
    END IF;
END $$;
