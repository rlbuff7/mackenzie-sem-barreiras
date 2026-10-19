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

-- ---------------------------------------------------------------------------
-- Grafo do campus (M1 do escopo novo): pontos_interesse, nos, arestas — migration 004
-- ---------------------------------------------------------------------------

SELECT pg_temp.afirmar('extensão pgrouting instalada',
    EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgrouting'));

SELECT pg_temp.afirmar('tabela ' || t || ' existe', to_regclass(t) IS NOT NULL)
FROM unnest(ARRAY['pontos_interesse', 'nos', 'arestas']) AS t;

SELECT pg_temp.afirmar('índice ' || i || ' existe', to_regclass(i) IS NOT NULL)
FROM unnest(ARRAY['idx_poi_geom', 'idx_nos_geom', 'idx_arestas_geom',
                  'idx_arestas_origem', 'idx_arestas_destino']) AS i;

SELECT pg_temp.afirmar('índice ' || i || ' é GiST',
    (SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam
      WHERE c.oid = to_regclass(i)) = 'gist')
FROM unnest(ARRAY['idx_poi_geom', 'idx_nos_geom', 'idx_arestas_geom']) AS i;

-- Pontos de interesse
INSERT INTO pontos_interesse (geom, tipo, nome)
VALUES ((SELECT centro_campus FROM ref), 'predio', 'Prédio de teste A');
SELECT pg_temp.afirmar('ponto de interesse válido é aceito, acessivel NULL = não verificado',
    (SELECT acessivel IS NULL FROM pontos_interesse WHERE nome = 'Prédio de teste A'));

SELECT pg_temp.deve_rejeitar('ponto de interesse com tipo ''banheiro'' inválido',
    $q$INSERT INTO pontos_interesse (geom, tipo, nome)
       VALUES (ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 'banheiro', 'x')$q$, '23514');

SELECT pg_temp.deve_rejeitar('ponto de interesse sem nome',
    $q$INSERT INTO pontos_interesse (geom, tipo, nome)
       VALUES (ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 'predio', NULL)$q$, '23502');

SELECT pg_temp.deve_rejeitar('ponto de interesse sem geometria',
    $q$INSERT INTO pontos_interesse (geom, tipo, nome) VALUES (NULL, 'predio', 'x')$q$, '23502');

SELECT pg_temp.deve_rejeitar('ponto de interesse com SRID 31983 em vez de 4326',
    $q$INSERT INTO pontos_interesse (geom, tipo, nome)
       VALUES (ST_SetSRID(ST_MakePoint(333000, 7394000), 31983), 'predio', 'x')$q$, '22023');

-- Nós
INSERT INTO nos (geom) VALUES
    (ST_SetSRID(ST_MakePoint(-46.6530, -23.5470), 4326)),
    (ST_SetSRID(ST_MakePoint(-46.6525, -23.5470), 4326)),
    (ST_SetSRID(ST_MakePoint(-46.6520, -23.5470), 4326));
SELECT pg_temp.afirmar('três nós de teste inseridos', (SELECT count(*) FROM nos) = 3);

SELECT pg_temp.deve_rejeitar('nó apontando para ponto de interesse inexistente',
    $q$INSERT INTO nos (geom, ponto_interesse_id)
       VALUES (ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), -1)$q$, '23503');

SELECT pg_temp.deve_rejeitar('nó sem geometria',
    $q$INSERT INTO nos (geom) VALUES (NULL)$q$, '23502');

-- Arestas: grafo mínimo n1 --(100 m)-- n2 --(100 m)-- n3, e um atalho por escada n1 -> n3
CREATE TEMP TABLE no_ids AS
SELECT row_number() OVER (ORDER BY id) AS n, id FROM nos;

CREATE FUNCTION pg_temp.inserir_aresta(
    de int, para int, tipo_aresta text, comp_m double precision,
    custo_ida double precision, custo_volta double precision) RETURNS void
LANGUAGE sql AS $$
    INSERT INTO arestas (geom, origem_id, destino_id, comprimento_m, tipo, custo, custo_inverso)
    SELECT ST_MakeLine(a.geom, b.geom), a.id, b.id, comp_m, tipo_aresta, custo_ida, custo_volta
      FROM nos a, nos b
     WHERE a.id = (SELECT id FROM no_ids WHERE n = de)
       AND b.id = (SELECT id FROM no_ids WHERE n = para)
$$;

SELECT pg_temp.inserir_aresta(1, 2, 'calcada', 100, 100, 100);
SELECT pg_temp.inserir_aresta(2, 3, 'calcada', 100, 100, 100);
SELECT pg_temp.inserir_aresta(1, 3, 'escada',  150, 600, -1);   -- 150 m x 4,0; só de ida
SELECT pg_temp.afirmar('três arestas de teste inseridas', (SELECT count(*) FROM arestas) = 3);

SELECT pg_temp.deve_rejeitar('aresta com tipo ''elevador'' inválido',
    $q$SELECT pg_temp.inserir_aresta(1, 2, 'elevador', 10, 10, 10)$q$, '23514');
SELECT pg_temp.deve_rejeitar('aresta com comprimento 0',
    $q$SELECT pg_temp.inserir_aresta(1, 2, 'calcada', 0, 10, 10)$q$, '23514');
SELECT pg_temp.deve_rejeitar('aresta com comprimento negativo',
    $q$SELECT pg_temp.inserir_aresta(1, 2, 'calcada', -5, 10, 10)$q$, '23514');
SELECT pg_temp.deve_rejeitar('aresta com custo negativo',
    $q$SELECT pg_temp.inserir_aresta(1, 2, 'calcada', 10, -1, 10)$q$, '23514');
SELECT pg_temp.deve_rejeitar('aresta com custo_inverso -2 (só vale -1 ou >= 0)',
    $q$SELECT pg_temp.inserir_aresta(1, 2, 'calcada', 10, 10, -2)$q$, '23514');
SELECT pg_temp.deve_rejeitar('aresta com origem igual ao destino',
    $q$SELECT pg_temp.inserir_aresta(1, 1, 'calcada', 10, 10, 10)$q$, '23514');
SELECT pg_temp.deve_rejeitar('aresta com origem inexistente',
    $q$INSERT INTO arestas (geom, origem_id, destino_id, comprimento_m, tipo, custo, custo_inverso)
       VALUES (ST_SetSRID(ST_MakeLine(ST_MakePoint(-46.65, -23.54), ST_MakePoint(-46.64, -23.54)), 4326),
               -1, (SELECT id FROM no_ids WHERE n = 2), 10, 'calcada', 10, 10)$q$, '23503');
SELECT pg_temp.deve_rejeitar('aresta sem custo',
    $q$INSERT INTO arestas (geom, origem_id, destino_id, comprimento_m, tipo, custo, custo_inverso)
       VALUES (ST_SetSRID(ST_MakeLine(ST_MakePoint(-46.65, -23.54), ST_MakePoint(-46.64, -23.54)), 4326),
               (SELECT id FROM no_ids WHERE n = 1), (SELECT id FROM no_ids WHERE n = 2),
               10, 'calcada', NULL, 10)$q$, '23502');
SELECT pg_temp.deve_rejeitar('aresta com SRID 31983 em vez de 4326',
    $q$INSERT INTO arestas (geom, origem_id, destino_id, comprimento_m, tipo, custo, custo_inverso)
       VALUES (ST_SetSRID(ST_MakeLine(ST_MakePoint(333000, 7394000), ST_MakePoint(333100, 7394000)), 31983),
               (SELECT id FROM no_ids WHERE n = 1), (SELECT id FROM no_ids WHERE n = 2),
               10, 'calcada', 10, 10)$q$, '22023');

-- pgRouting funciona com as colunas custo / custo_inverso
SELECT pg_temp.afirmar('pgr_dijkstra escolhe as duas calçadas (custo 200) e não a escada (600)',
    (SELECT array_agg(node ORDER BY seq) = (SELECT array_agg(id ORDER BY n) FROM no_ids)
        AND max(agg_cost) = 200
       FROM pgr_dijkstra(
            'SELECT id, origem_id AS source, destino_id AS target,
                    custo AS cost, custo_inverso AS reverse_cost FROM arestas',
            (SELECT id FROM no_ids WHERE n = 1), (SELECT id FROM no_ids WHERE n = 3),
            directed => true)));

SELECT pg_temp.afirmar('pgr_dijkstra respeita custo_inverso = -1 (escada sem caminho de volta)',
    NOT EXISTS (SELECT 1 FROM pgr_dijkstra(
            'SELECT id, origem_id AS source, destino_id AS target,
                    custo AS cost, custo_inverso AS reverse_cost
               FROM arestas WHERE tipo = ''escada''',
            (SELECT id FROM no_ids WHERE n = 3), (SELECT id FROM no_ids WHERE n = 1),
            directed => true)));

-- ---------------------------------------------------------------------------
-- Medições de GPS em tempo real (medicoes_gps) — migration 005
-- ---------------------------------------------------------------------------

SELECT pg_temp.afirmar('tabela medicoes_gps existe', to_regclass('medicoes_gps') IS NOT NULL);

SELECT pg_temp.afirmar('medicoes_gps.geom é Point em SRID 4326',
    (SELECT type = 'POINT' AND srid = 4326 FROM geometry_columns
     WHERE f_table_name = 'medicoes_gps' AND f_geometry_column = 'geom'));

SELECT pg_temp.afirmar('índice ' || i || ' existe em medicoes_gps',
    EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'medicoes_gps' AND indexname = i))
FROM unnest(ARRAY['idx_medicoes_gps_geom', 'idx_medicoes_gps_medido_em',
                  'idx_medicoes_gps_aparelho_ponto']) AS i;

SELECT pg_temp.afirmar('índice idx_medicoes_gps_geom é GiST',
    EXISTS (SELECT 1 FROM pg_indexes
            WHERE indexname = 'idx_medicoes_gps_geom' AND indexdef ILIKE '%USING gist%'));

SELECT pg_temp.afirmar('índice (aparelho, ponto) cobre as duas colunas, nessa ordem',
    EXISTS (SELECT 1 FROM pg_indexes
            WHERE indexname = 'idx_medicoes_gps_aparelho_ponto'
              AND indexdef ILIKE '%(aparelho, ponto)%'));

SELECT pg_temp.afirmar('id_cliente tem UNIQUE (reenvio idempotente)',
    EXISTS (SELECT 1 FROM pg_constraint
            WHERE conrelid = 'medicoes_gps'::regclass AND contype = 'u'
              AND conname = 'medicoes_gps_id_cliente_unico'));

-- Medição de ponto válida (base para as variações abaixo)
INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, condicao, geom, precisao_m)
VALUES ('11111111-1111-4111-8111-111111111111', 'ponto', now(), 'Galaxy A54', 3, 'ceu_aberto',
        ST_SetSRID(ST_MakePoint(-46.6524631, -23.5471938), 4326), 4.5);

SELECT pg_temp.afirmar('medição de ponto válida entra, com recebido_em preenchido pelo servidor',
    (SELECT count(*) = 1 AND bool_and(recebido_em IS NOT NULL) FROM medicoes_gps
      WHERE id_cliente = '11111111-1111-4111-8111-111111111111'));

SELECT pg_temp.deve_rejeitar('id_cliente repetido',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, geom, precisao_m)
       VALUES ('11111111-1111-4111-8111-111111111111', 'ponto', now(), 'Galaxy A54', 3,
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 5)$q$, '23505');

-- Outros tipos válidos, sem geom: bússola e vibração
INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, bussola_graus, bussola_fonte,
                          bussola_oscilacao_graus)
VALUES ('22222222-2222-4222-8222-222222222222', 'bussola', now(), 'iPhone 13', 359.9,
        'webkitCompassHeading', 2.5);
INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, vibracao_suportada)
VALUES ('33333333-3333-4333-8333-333333333333', 'vibracao', now(), 'iPhone 13', false);
INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, geom, precisao_m)
VALUES ('44444444-4444-4444-8444-444444444444', 'trajeto', now(), 'Galaxy A54',
        ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 8);
SELECT pg_temp.afirmar('bússola, vibração e trajeto válidos entram (ponto fica NULL)',
    (SELECT count(*) = 3 FROM medicoes_gps WHERE ponto IS NULL));

SELECT pg_temp.deve_rejeitar('tipo ''gravidade'' inválido',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho)
       VALUES (gen_random_uuid(), 'gravidade', now(), 'X')$q$, '23514');
SELECT pg_temp.deve_rejeitar('sem id_cliente',
    $q$INSERT INTO medicoes_gps (tipo, medido_em, aparelho)
       VALUES ('vibracao', now(), 'X')$q$, '23502');
SELECT pg_temp.deve_rejeitar('sem medido_em',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, aparelho)
       VALUES (gen_random_uuid(), 'vibracao', 'X')$q$, '23502');
SELECT pg_temp.deve_rejeitar('sem aparelho',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em)
       VALUES (gen_random_uuid(), 'vibracao', now())$q$, '23502');
SELECT pg_temp.deve_rejeitar('aparelho vazio',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho)
       VALUES (gen_random_uuid(), 'vibracao', now(), '')$q$, '23514');
SELECT pg_temp.deve_rejeitar('aparelho só com espaços',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho)
       VALUES (gen_random_uuid(), 'vibracao', now(), '   ')$q$, '23514');
SELECT pg_temp.deve_rejeitar('aparelho com mais de 80 caracteres',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho)
       VALUES (gen_random_uuid(), 'vibracao', now(), repeat('a', 81))$q$, '22001');

SELECT pg_temp.deve_rejeitar('ponto 0 (faixa é 1..12)',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, geom, precisao_m)
       VALUES (gen_random_uuid(), 'ponto', now(), 'X', 0,
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 5)$q$, '23514');
SELECT pg_temp.deve_rejeitar('ponto 13 (faixa é 1..12)',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, geom, precisao_m)
       VALUES (gen_random_uuid(), 'ponto', now(), 'X', 13,
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 5)$q$, '23514');
SELECT pg_temp.deve_rejeitar('tipo ponto sem o número do ponto',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, geom, precisao_m)
       VALUES (gen_random_uuid(), 'ponto', now(), 'X',
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 5)$q$, '23514');
SELECT pg_temp.deve_rejeitar('condição ''chuva'' inválida',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, condicao)
       VALUES (gen_random_uuid(), 'vibracao', now(), 'X', 'chuva')$q$, '23514');

SELECT pg_temp.deve_rejeitar('tipo ponto sem geom',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, precisao_m)
       VALUES (gen_random_uuid(), 'ponto', now(), 'X', 1, 5)$q$, '23514');
SELECT pg_temp.deve_rejeitar('tipo ponto sem precisao_m',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, geom)
       VALUES (gen_random_uuid(), 'ponto', now(), 'X', 1,
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('tipo trajeto sem geom',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, precisao_m)
       VALUES (gen_random_uuid(), 'trajeto', now(), 'X', 5)$q$, '23514');
SELECT pg_temp.deve_rejeitar('tipo trajeto sem precisao_m',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, geom)
       VALUES (gen_random_uuid(), 'trajeto', now(), 'X',
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('geom em tipo bússola sem precisao_m (geom exige precisão)',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, geom)
       VALUES (gen_random_uuid(), 'bussola', now(), 'X',
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('precisao_m negativa',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, geom, precisao_m)
       VALUES (gen_random_uuid(), 'trajeto', now(), 'X',
               ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), -1)$q$, '23514');
SELECT pg_temp.deve_rejeitar('geom com SRID 31983 em vez de 4326',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, geom, precisao_m)
       VALUES (gen_random_uuid(), 'trajeto', now(), 'X',
               ST_SetSRID(ST_MakePoint(333000, 7394000), 31983), 5)$q$, '22023');

SELECT pg_temp.deve_rejeitar('bússola 360 (faixa é 0 <= x < 360)',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, bussola_graus)
       VALUES (gen_random_uuid(), 'bussola', now(), 'X', 360)$q$, '23514');
SELECT pg_temp.deve_rejeitar('bússola negativa',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, bussola_graus)
       VALUES (gen_random_uuid(), 'bussola', now(), 'X', -0.1)$q$, '23514');
SELECT pg_temp.deve_rejeitar('bussola_fonte ''giroscopio'' inválida',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, bussola_graus, bussola_fonte)
       VALUES (gen_random_uuid(), 'bussola', now(), 'X', 10, 'giroscopio')$q$, '23514');
SELECT pg_temp.deve_rejeitar('oscilação da bússola negativa',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, bussola_graus,
                                 bussola_oscilacao_graus)
       VALUES (gen_random_uuid(), 'bussola', now(), 'X', 10, -1)$q$, '23514');
SELECT pg_temp.deve_rejeitar('observação com mais de 500 caracteres',
    $q$INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, observacao)
       VALUES (gen_random_uuid(), 'vibracao', now(), 'X', repeat('a', 501))$q$, '22001');

-- ---------------------------------------------------------------------------
-- Pontos de controle e erro das medições (migration 006 + seed 003)
-- ---------------------------------------------------------------------------

SELECT pg_temp.afirmar('tabela pontos_controle existe', to_regclass('pontos_controle') IS NOT NULL);
SELECT pg_temp.afirmar('seed: 10 pontos de controle (P01..P10)',
    (SELECT count(*) = 10 AND min(numero) = 1 AND max(numero) = 10 FROM pontos_controle));
SELECT pg_temp.afirmar('seed: código P01..P10 confere com o número',
    NOT EXISTS (SELECT 1 FROM pontos_controle WHERE codigo <> 'P' || lpad(numero::text, 2, '0')));
SELECT pg_temp.afirmar('seed: todas as referências caem no campus (lat -23,55..-23,54; lon -46,654..-46,651)',
    NOT EXISTS (SELECT 1 FROM pontos_controle
                WHERE ST_Y(geom_referencia) NOT BETWEEN -23.55 AND -23.54
                   OR ST_X(geom_referencia) NOT BETWEEN -46.654 AND -46.651));
SELECT pg_temp.afirmar('seed: condições 5 ceu_aberto / 2 entre_predios / 3 coberto',
    (SELECT count(*) FILTER (WHERE condicao = 'ceu_aberto') = 5
        AND count(*) FILTER (WHERE condicao = 'entre_predios') = 2
        AND count(*) FILTER (WHERE condicao = 'coberto') = 3 FROM pontos_controle));
SELECT pg_temp.afirmar('seed: P04..P06 são "Entrada de prédio" mapeados para coberto',
    (SELECT count(*) = 3 FROM pontos_controle
     WHERE rotulo_condicao_original = 'Entrada de prédio' AND condicao = 'coberto'
       AND numero IN (4, 5, 6)));
SELECT pg_temp.afirmar('pontos_controle.geom_referencia é Point em SRID 4326',
    EXISTS (SELECT 1 FROM geometry_columns
            WHERE f_table_name = 'pontos_controle' AND f_geometry_column = 'geom_referencia'
              AND type = 'POINT' AND srid = 4326));
SELECT pg_temp.afirmar('índice idx_pontos_controle_geom é GiST',
    EXISTS (SELECT 1 FROM pg_indexes
            WHERE indexname = 'idx_pontos_controle_geom' AND indexdef ILIKE '%USING gist%'));
SELECT pg_temp.afirmar('origem_referencia padrão diz estimativa por satélite',
    (SELECT bool_and(origem_referencia LIKE '%estimativa%') FROM pontos_controle));

SELECT pg_temp.deve_rejeitar('ponto de controle com número 13',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao, geom_referencia)
       VALUES (13, 'P13', 'x', 'ceu_aberto', ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('ponto de controle com condição fora da lista do app',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao, geom_referencia)
       VALUES (11, 'P11', 'x', 'entrada_predio', ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('código que não confere com o número',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao, geom_referencia)
       VALUES (11, 'P99', 'x', 'ceu_aberto', ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('código repetido',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao, geom_referencia)
       VALUES (11, 'P01', 'x', 'ceu_aberto', ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23514');
SELECT pg_temp.deve_rejeitar('número repetido',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao, geom_referencia)
       VALUES (1, 'P01', 'x', 'ceu_aberto', ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326))$q$, '23505');
SELECT pg_temp.deve_rejeitar('geom_referencia obrigatória',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao)
       VALUES (11, 'P11', 'x', 'ceu_aberto')$q$, '23502');
SELECT pg_temp.deve_rejeitar('geom_referencia com SRID 31983 em vez de 4326',
    $q$INSERT INTO pontos_controle (numero, codigo, nome, condicao, geom_referencia)
       VALUES (11, 'P11', 'x', 'ceu_aberto', ST_SetSRID(ST_MakePoint(333000, 7394000), 31983))$q$, '22023');

-- Distância conhecida: pontos deslocados 0, 10 e 20 m para o norte do P01 (o
-- deslocamento é feito em 31983, onde a unidade é metro) e um aparelho 'T-erro'.
-- Também confere que medição de outro tipo e de ponto sem referência (11) fica de fora.
INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, condicao, geom, precisao_m)
SELECT gen_random_uuid(), 'ponto', now(), 'T-erro', 1, 'ceu_aberto',
       ST_Transform(ST_Translate(ST_Transform(p.geom_referencia, 31983), 0, d.deslocamento_m), 4326),
       d.precisao
FROM pontos_controle p,
     (VALUES (0.0, 12.0), (10.0, 12.0), (20.0, 12.0)) AS d(deslocamento_m, precisao)
WHERE p.numero = 1;
INSERT INTO medicoes_gps (id_cliente, tipo, medido_em, aparelho, ponto, geom, precisao_m)
VALUES (gen_random_uuid(), 'ponto', now(), 'T-erro', 11,
        ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 5),
       (gen_random_uuid(), 'trajeto', now(), 'T-erro', 1,
        ST_SetSRID(ST_MakePoint(-46.65, -23.54), 4326), 5);

SELECT pg_temp.afirmar('vw_erro_medicoes: 3 linhas do T-erro (sem ponto 11, sem trajeto)',
    (SELECT count(*) = 3 FROM vw_erro_medicoes WHERE aparelho = 'T-erro'));
SELECT pg_temp.afirmar('vw_erro_medicoes: deslocamento de 10 m dá erro_m = 10 +- 0,5',
    EXISTS (SELECT 1 FROM vw_erro_medicoes
            WHERE aparelho = 'T-erro' AND abs(erro_m - 10) <= 0.5));
SELECT pg_temp.afirmar('vw_erro_medicoes: erro_m em metros, não em grau (máximo 20 +- 0,5)',
    (SELECT abs(max(erro_m) - 20) <= 0.5 AND min(erro_m) <= 0.5
     FROM vw_erro_medicoes WHERE aparelho = 'T-erro'));
SELECT pg_temp.afirmar('vw_erro_medicoes: traz ponto_codigo, precisao_m, aparelho, condicao e medido_em',
    (SELECT bool_and(ponto_codigo = 'P01' AND precisao_m = 12 AND condicao = 'ceu_aberto'
                     AND medido_em IS NOT NULL)
     FROM vw_erro_medicoes WHERE aparelho = 'T-erro'));
SELECT pg_temp.afirmar('vw_erro_por_ponto_aparelho: n = 3, mediana ~ 10 m, p90 ~ 18 m',
    (SELECT n = 3 AND abs(erro_mediana_m - 10) <= 0.5 AND abs(erro_p90_m - 18) <= 0.5
     FROM vw_erro_por_ponto_aparelho WHERE aparelho = 'T-erro' AND ponto = 1));
SELECT pg_temp.afirmar('vw_erro_por_ponto_aparelho: erro <= precisão em 2 de 3 medições (0 m e 10 m; 20 m não)',
    (SELECT abs(fracao_erro_dentro_precisao - 2.0 / 3) < 1e-9
     FROM vw_erro_por_ponto_aparelho WHERE aparelho = 'T-erro' AND ponto = 1));

ROLLBACK;
\echo 'test_schema.sql: todos os testes passaram (transação desfeita, nenhum dado gravado)'
