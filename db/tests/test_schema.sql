-- Testes do schema (M1): tabelas, constraints, índices e seeds.
--
--   ./db/banco.sh testar
--
-- Roda dentro de uma transação e termina em ROLLBACK: não deixa dados no banco.
-- Cada rejeição é conferida pelo SQLSTATE esperado, para que um teste não passe
-- "por acidente" quando o comando falha por outro motivo.

\set ON_ERROR_STOP on
\set QUIET on
-- Descarta as tabelas de resultado dos SELECTs; o que importa são os NOTICEs.
\o /dev/null
BEGIN;

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

CREATE FUNCTION pg_temp.afirmar(caso text, condicao boolean) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF condicao IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'FALHOU: %', caso;
    END IF;
    RAISE NOTICE 'ok  %', caso;
END $$;

-- Executa o comando e exige que ele seja rejeitado com o SQLSTATE indicado.
-- 23502 not_null | 23503 foreign_key | 23505 unique | 23514 check | 22023 parâmetro inválido
CREATE FUNCTION pg_temp.deve_rejeitar(caso text, comando text, sqlstate_esperado text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE comando;
    EXCEPTION WHEN OTHERS THEN
        IF SQLSTATE = sqlstate_esperado THEN
            RAISE NOTICE 'ok  rejeita: %', caso;
            RETURN;
        END IF;
        RAISE EXCEPTION 'FALHOU %: esperava SQLSTATE %, veio % (%)',
            caso, sqlstate_esperado, SQLSTATE, SQLERRM;
    END;
    RAISE EXCEPTION 'FALHOU %: o comando deveria ter sido rejeitado', caso;
END $$;

-- Pontos de referência (lon, lat em SRID 4326)
CREATE TEMP TABLE ref AS SELECT
    ST_SetSRID(ST_MakePoint(-46.6524631, -23.5471938), 4326) AS centro_campus, -- OSM
    ST_SetSRID(ST_MakePoint(-46.6558, -23.5614), 4326)       AS masp,          -- ~1,6 km ao sul
    (SELECT id FROM tipos_barreira WHERE codigo = 'degrau')  AS tipo_degrau,
    repeat('a', 64)                                          AS sessao;

-- ---------------------------------------------------------------------------
-- Estrutura
-- ---------------------------------------------------------------------------

SELECT pg_temp.afirmar('extensão postgis instalada',
    EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis'));

SELECT pg_temp.afirmar('tabela ' || t || ' existe', to_regclass(t) IS NOT NULL)
FROM unnest(ARRAY['tipos_barreira', 'area_estudo', 'barreiras',
                  'alertas', 'alertas_rejeitados']) AS t;

SELECT pg_temp.afirmar('índice ' || i || ' é GiST',
    EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = i AND indexdef ILIKE '%USING gist%'))
FROM unnest(ARRAY['idx_alertas_geom', 'idx_barreiras_geom']) AS i;

SELECT pg_temp.afirmar('alertas.geom é Point em SRID 4326',
    (SELECT type = 'POINT' AND srid = 4326 FROM geometry_columns
     WHERE f_table_name = 'alertas' AND f_geometry_column = 'geom'));

-- ---------------------------------------------------------------------------
-- Seeds
-- ---------------------------------------------------------------------------

SELECT pg_temp.afirmar('seed: 4 tipos de barreira ativos (taxonomia provisória do pôster)',
    (SELECT count(*) FROM tipos_barreira WHERE ativo) = 4);

SELECT pg_temp.afirmar('seed: exatamente uma área de estudo',
    (SELECT count(*) FROM area_estudo) = 1);

SELECT pg_temp.afirmar('seed: polígono da área é válido',
    (SELECT bool_and(ST_IsValid(geom)) FROM area_estudo));

-- Raio de 500 m => área ~ pi * 500^2 ~ 0,785 km^2. Se o buffer tivesse sido feito
-- em graus (armadilha do SRID, CLAUDE.md §5), a área seria absurda.
SELECT pg_temp.afirmar('seed: área de estudo tem ~0,78 km² (buffer calculado em metros)',
    (SELECT ST_Area(geom::geography) BETWEEN 0.75e6 AND 0.80e6 FROM area_estudo));

SELECT pg_temp.afirmar('geofence: centro do campus está dentro da área',
    (SELECT ST_Within(r.centro_campus, a.geom) FROM ref r, area_estudo a));

SELECT pg_temp.afirmar('geofence: MASP está fora da área',
    (SELECT NOT ST_Within(r.masp, a.geom) FROM ref r, area_estudo a));

-- ---------------------------------------------------------------------------
-- alertas: caminho feliz
-- ---------------------------------------------------------------------------

INSERT INTO alertas (geom, tipo_id, severidade, sessao_hash)
SELECT centro_campus, tipo_degrau, 2, sessao FROM ref;

SELECT pg_temp.afirmar('alerta válido entra com status padrão ''bruto''',
    (SELECT status = 'bruto' AND criado_em IS NOT NULL FROM alertas ORDER BY id DESC LIMIT 1));

-- ---------------------------------------------------------------------------
-- alertas: rejeições
-- ---------------------------------------------------------------------------

SELECT pg_temp.deve_rejeitar('alerta sem geometria',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash)
              VALUES (NULL, %s, %L)$q$, tipo_degrau, sessao), '23502') FROM ref;

SELECT pg_temp.deve_rejeitar('alerta em SRID diferente de 4326',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash)
              VALUES (ST_SetSRID(ST_MakePoint(-5193000, -2698000), 3857), %s, %L)$q$,
           tipo_degrau, sessao), '22023') FROM ref;

SELECT pg_temp.deve_rejeitar('alerta com polígono em vez de ponto',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash)
              SELECT geom, %s, %L FROM area_estudo$q$, tipo_degrau, sessao), '22023') FROM ref;

SELECT pg_temp.deve_rejeitar('alerta sem tipo',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash)
              VALUES (%L, NULL, %L)$q$, centro_campus, sessao), '23502') FROM ref;

SELECT pg_temp.deve_rejeitar('alerta com tipo inexistente',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash)
              VALUES (%L, 999999, %L)$q$, centro_campus, sessao), '23503') FROM ref;

SELECT pg_temp.deve_rejeitar('alerta sem sessão (quebraria a contagem de sessões distintas)',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash)
              VALUES (%L, %s, NULL)$q$, centro_campus, tipo_degrau), '23502') FROM ref;

SELECT pg_temp.deve_rejeitar('severidade ' || s,
    format($q$INSERT INTO alertas (geom, tipo_id, severidade, sessao_hash)
              VALUES (%L, %s, %s, %L)$q$, centro_campus, tipo_degrau, s, sessao), '23514')
FROM ref, unnest(ARRAY[0, 4]) AS s;

SELECT pg_temp.deve_rejeitar('status fora do ciclo de vida',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash, status)
              VALUES (%L, %s, %L, 'aprovado')$q$, centro_campus, tipo_degrau, sessao), '23514')
FROM ref;

SELECT pg_temp.deve_rejeitar('descartado sem motivo',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash, status)
              VALUES (%L, %s, %L, 'descartado')$q$, centro_campus, tipo_degrau, sessao), '23514')
FROM ref;

SELECT pg_temp.deve_rejeitar('motivo de descarte em alerta não descartado',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash, motivo_descarte)
              VALUES (%L, %s, %L, 'fora_da_area')$q$, centro_campus, tipo_degrau, sessao), '23514')
FROM ref;

SELECT pg_temp.deve_rejeitar('agrupado sem barreira',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash, status)
              VALUES (%L, %s, %L, 'agrupado')$q$, centro_campus, tipo_degrau, sessao), '23514')
FROM ref;

-- ---------------------------------------------------------------------------
-- barreiras
-- ---------------------------------------------------------------------------

INSERT INTO barreiras (geom, tipo_id, confirmacoes)
SELECT centro_campus, tipo_degrau, 1 FROM ref;

SELECT pg_temp.afirmar('barreira nova entra como ''pendente''',
    (SELECT status = 'pendente' FROM barreiras ORDER BY id DESC LIMIT 1));

SELECT pg_temp.deve_rejeitar('barreira com status inválido',
    format($q$INSERT INTO barreiras (geom, tipo_id, confirmacoes, status)
              VALUES (%L, %s, 3, 'validada')$q$, centro_campus, tipo_degrau), '23514') FROM ref;

SELECT pg_temp.deve_rejeitar('barreira com zero confirmações',
    format($q$INSERT INTO barreiras (geom, tipo_id, confirmacoes)
              VALUES (%L, %s, 0)$q$, centro_campus, tipo_degrau), '23514') FROM ref;

-- Alerta agrupado ligado a uma barreira existente: deve ser aceito.
INSERT INTO alertas (geom, tipo_id, sessao_hash, status, barreira_id)
SELECT centro_campus, tipo_degrau, sessao, 'agrupado', (SELECT max(id) FROM barreiras) FROM ref;
SELECT pg_temp.afirmar('alerta agrupado com barreira é aceito', true);

-- ---------------------------------------------------------------------------
-- alertas_rejeitados (estágio 1)
-- ---------------------------------------------------------------------------

INSERT INTO alertas_rejeitados (payload, erros)
VALUES ('{"lat": 200, "lon": -46.65, "tipo_id": 99}',
        '[{"campo": "lat", "erro": "fora da faixa"}]');
SELECT pg_temp.afirmar('payload inválido é guardado em alertas_rejeitados',
    (SELECT payload->>'lat' = '200' FROM alertas_rejeitados ORDER BY id DESC LIMIT 1));

SELECT pg_temp.deve_rejeitar('rejeitado sem payload',
    $q$INSERT INTO alertas_rejeitados (payload, erros) VALUES (NULL, '[]')$q$, '23502');

-- ---------------------------------------------------------------------------
-- origem (D2, G10): dado real vs. simulação — migration 002
-- ---------------------------------------------------------------------------

INSERT INTO alertas (geom, tipo_id, sessao_hash)
SELECT centro_campus, tipo_degrau, sessao FROM ref;
SELECT pg_temp.afirmar('alertas.origem padrão é ''real''',
    (SELECT origem = 'real' FROM alertas ORDER BY id DESC LIMIT 1));

SELECT pg_temp.deve_rejeitar('alertas com origem ''teste'' inválida',
    format($q$INSERT INTO alertas (geom, tipo_id, sessao_hash, origem)
              VALUES (%L, %s, %L, 'teste')$q$, centro_campus, tipo_degrau, sessao), '23514')
FROM ref;

INSERT INTO barreiras (geom, tipo_id, confirmacoes)
SELECT centro_campus, tipo_degrau, 1 FROM ref;
SELECT pg_temp.afirmar('barreiras.origem padrão é ''real''',
    (SELECT origem = 'real' FROM barreiras ORDER BY id DESC LIMIT 1));

SELECT pg_temp.deve_rejeitar('barreiras com origem ''teste'' inválida',
    format($q$INSERT INTO barreiras (geom, tipo_id, confirmacoes, origem)
              VALUES (%L, %s, 1, 'teste')$q$, centro_campus, tipo_degrau), '23514')
FROM ref;

INSERT INTO alertas_rejeitados (payload, erros)
VALUES ('{"lat": 200}', '[{"campo": "lat", "erro": "fora da faixa"}]');
SELECT pg_temp.afirmar('alertas_rejeitados.origem padrão é ''real''',
    (SELECT origem = 'real' FROM alertas_rejeitados ORDER BY id DESC LIMIT 1));

SELECT pg_temp.deve_rejeitar('alertas_rejeitados com origem ''teste'' inválida',
    $q$INSERT INTO alertas_rejeitados (payload, erros, origem)
       VALUES ('{}', '[]', 'teste')$q$, '23514');

-- ---------------------------------------------------------------------------
-- execucoes_pipeline (R14): parâmetros da última execução, por origem — migration 003
-- ---------------------------------------------------------------------------

SELECT pg_temp.afirmar('tabela execucoes_pipeline existe',
    to_regclass('execucoes_pipeline') IS NOT NULL);

INSERT INTO execucoes_pipeline (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
VALUES ('real', 8, 2, 3, 31983);
SELECT pg_temp.afirmar('execução válida é aceita, com executado_em preenchido',
    (SELECT executado_em IS NOT NULL FROM execucoes_pipeline WHERE origem = 'real'));

SELECT pg_temp.deve_rejeitar('segunda linha para a mesma origem (uma linha por origem)',
    $q$INSERT INTO execucoes_pipeline (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
       VALUES ('real', 4, 2, 3, 31983)$q$, '23505');

SELECT pg_temp.deve_rejeitar('execucoes_pipeline com origem ''teste'' inválida',
    $q$INSERT INTO execucoes_pipeline (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
       VALUES ('teste', 8, 2, 3, 31983)$q$, '23514');

SELECT pg_temp.deve_rejeitar('eps_metros ' || e,
    format($q$INSERT INTO execucoes_pipeline
                  (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
              VALUES ('simulacao', %s, 2, 3, 31983)$q$, e), '23514')
FROM unnest(ARRAY[0, -1]) AS e;

SELECT pg_temp.deve_rejeitar('min_pontos 0',
    $q$INSERT INTO execucoes_pipeline (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
       VALUES ('simulacao', 8, 0, 3, 31983)$q$, '23514');

SELECT pg_temp.deve_rejeitar('min_confirmacoes 0',
    $q$INSERT INTO execucoes_pipeline (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
       VALUES ('simulacao', 8, 2, 0, 31983)$q$, '23514');

SELECT pg_temp.deve_rejeitar('execução sem srid_calculo',
    $q$INSERT INTO execucoes_pipeline (origem, eps_metros, min_pontos, min_confirmacoes, srid_calculo)
       VALUES ('simulacao', 8, 2, 3, NULL)$q$, '23502');

ROLLBACK;
\echo 'test_schema.sql: todos os testes passaram (transação desfeita, nenhum dado gravado)'
