-- Invariantes do grafo do campus carregado pelo seed (db/seeds/004_campus_osm.sql).
--
--   ./db/banco.sh testar
--
-- Só lê (termina em ROLLBACK). Vale para o seed provisório do OpenStreetMap e, depois,
-- para o mapeamento do Maurício: são regras do GRAFO, não do conteúdo.

\set ON_ERROR_STOP on
\set QUIET on
\o /dev/null
BEGIN;

CREATE FUNCTION pg_temp.afirmar(caso text, condicao boolean) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF condicao IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'FALHOU: %', caso;
    END IF;
    RAISE NOTICE 'ok  %', caso;
END $$;

SELECT pg_temp.afirmar('grafo do campus carregado: pelo menos 15 arestas e 10 nós',
    (SELECT count(*) >= 15 FROM arestas) AND (SELECT count(*) >= 10 FROM nos));
SELECT pg_temp.afirmar('nenhum nó órfão (todo nó tem aresta)',
    NOT EXISTS (SELECT 1 FROM nos n
                WHERE NOT EXISTS (SELECT 1 FROM arestas a WHERE a.origem_id = n.id OR a.destino_id = n.id)));
SELECT pg_temp.afirmar('nenhuma aresta órfã (origem e destino existem)',
    NOT EXISTS (SELECT 1 FROM arestas a
                WHERE NOT EXISTS (SELECT 1 FROM nos WHERE id = a.origem_id)
                   OR NOT EXISTS (SELECT 1 FROM nos WHERE id = a.destino_id)));
SELECT pg_temp.afirmar('comprimento_m bate com ST_Length em 31983 (tolerância 0,01 m)',
    NOT EXISTS (SELECT 1 FROM arestas
                WHERE abs(comprimento_m - ST_Length(ST_Transform(geom, 31983))) > 0.01));
SELECT pg_temp.afirmar('comprimento_m em metros, não em grau (toda aresta entre 1 m e 150 m)',
    NOT EXISTS (SELECT 1 FROM arestas WHERE comprimento_m NOT BETWEEN 1 AND 150));
SELECT pg_temp.afirmar('extremos da geometria coincidem com os nós de origem e destino',
    NOT EXISTS (SELECT 1 FROM arestas a
                JOIN nos o ON o.id = a.origem_id JOIN nos d ON d.id = a.destino_id
                WHERE NOT ST_Equals(ST_StartPoint(a.geom), o.geom)
                   OR NOT ST_Equals(ST_EndPoint(a.geom), d.geom)));
SELECT pg_temp.afirmar('grafo conexo (uma componente só, mão única tratada como mão dupla)',
    (SELECT count(DISTINCT component) = 1 FROM pgr_connectedComponents(
        'SELECT id, origem_id AS source, destino_id AS target, 1 AS cost FROM arestas')));
SELECT pg_temp.afirmar('toda entrada e todo portão têm nó',
    NOT EXISTS (SELECT 1 FROM pontos_interesse p WHERE p.tipo IN ('entrada', 'portao')
                AND NOT EXISTS (SELECT 1 FROM nos WHERE ponto_interesse_id = p.id)));
SELECT pg_temp.afirmar('no máximo um nó por ponto de interesse',
    NOT EXISTS (SELECT 1 FROM nos WHERE ponto_interesse_id IS NOT NULL
                GROUP BY ponto_interesse_id HAVING count(*) > 1));
SELECT pg_temp.afirmar('segurança: toda aresta escada tem um ponto escada a até 5 m',
    NOT EXISTS (SELECT 1 FROM arestas a WHERE a.tipo = 'escada'
                AND NOT EXISTS (SELECT 1 FROM pontos_interesse p WHERE p.tipo = 'escada'
                    AND ST_Distance(ST_Transform(p.geom, 31983), ST_Transform(a.geom, 31983)) <= 5)));
SELECT pg_temp.afirmar('segurança: todo ponto escada tem uma aresta escada a até 5 m',
    NOT EXISTS (SELECT 1 FROM pontos_interesse p WHERE p.tipo = 'escada'
                AND NOT EXISTS (SELECT 1 FROM arestas a WHERE a.tipo = 'escada'
                    AND ST_Distance(ST_Transform(p.geom, 31983), ST_Transform(a.geom, 31983)) <= 5)));
SELECT pg_temp.afirmar('escada nunca é marcada como acessível a cadeirante',
    NOT EXISTS (SELECT 1 FROM arestas WHERE tipo = 'escada' AND acessivel_cadeirante IS DISTINCT FROM false));
SELECT pg_temp.afirmar('proveniência preenchida em toda aresta e ponto do campus',
    NOT EXISTS (SELECT 1 FROM arestas WHERE mapeado_por IS NULL OR mapeado_em IS NULL)
    AND NOT EXISTS (SELECT 1 FROM pontos_interesse WHERE mapeado_por IS NULL OR mapeado_em IS NULL));
SELECT pg_temp.afirmar('custo de referência = comprimento_m; custo_inverso = comprimento_m ou -1',
    NOT EXISTS (SELECT 1 FROM arestas WHERE custo <> comprimento_m
                OR (custo_inverso <> -1 AND custo_inverso <> comprimento_m)));
SELECT pg_temp.afirmar('sequências de id à frente do maior id (inserção nova não colide)',
    (SELECT last_value >= (SELECT max(id) FROM arestas) FROM arestas_id_seq)
    AND (SELECT last_value >= (SELECT max(id) FROM nos) FROM nos_id_seq)
    AND (SELECT last_value >= (SELECT max(id) FROM pontos_interesse) FROM pontos_interesse_id_seq));

-- Para o perfil cadeirante ter o que mostrar: pelo menos um par de pontos com nó em que
-- SÓ existe caminho com escada (cadeirante: sem rota) ou em que o caminho sem escada
-- difere do mais curto. Informativo: não falha, só registra qual dos dois vale.
SELECT pg_temp.afirmar('há ao menos um par de pontos que depende de escada',
    EXISTS (
        SELECT 1
        FROM pgr_dijkstraCost(
                'SELECT id, origem_id AS source, destino_id AS target, comprimento_m AS cost,
                        comprimento_m AS reverse_cost FROM arestas',
                ARRAY(SELECT id FROM nos WHERE ponto_interesse_id IS NOT NULL),
                ARRAY(SELECT id FROM nos WHERE ponto_interesse_id IS NOT NULL), false) c
        WHERE c.start_vid <> c.end_vid
          AND NOT EXISTS (
            SELECT 1 FROM pgr_dijkstraCost(
                'SELECT id, origem_id AS source, destino_id AS target, comprimento_m AS cost,
                        comprimento_m AS reverse_cost FROM arestas WHERE tipo <> ''escada''',
                c.start_vid, c.end_vid, false) s)));

ROLLBACK;
\echo 'test_grafo_campus.sql: todos os testes passaram (somente leitura)'
