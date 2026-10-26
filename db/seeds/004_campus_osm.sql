-- 004: grafo PROVISÓRIO do campus, gerado do OpenStreetMap. NÃO EDITE À MÃO.
--
-- Regenerar:  python3 db/scripts/osm_para_seed.py > db/seeds/004_campus_osm.sql
--
-- Dados de mapa (c) contribuidores do OpenStreetMap, licença ODbL:
--   https://www.openstreetmap.org/copyright
-- Este arquivo é uma Base de Dados Derivada e continua sob a ODbL; quem a
-- redistribuir deve manter esta atribuição.
--
-- Baixado em 2026-10-26 da Overpass API, retângulo (sul, oeste, norte, leste) = -23.5483, -46.6535, -23.5456, -46.651.
-- 24 nós, 26 arestas (calcada: 24, escada: 2), 13 pontos de interesse.
--
-- PROVISÓRIO: não foi conferido a pé (fonte_verificacao = 'provisorio'). Vale só até o
-- mapeamento do campus (M2) chegar. Aresta sem etiqueta de acessibilidade fica como
-- 'não verificado' (NULL). Nenhuma mão única foi importada (tudo mão dupla).
--
-- Correções de campo (CORRECOES_DE_CAMPO no script) já aplicadas: escadaria da rua Piauí
-- (relato do Maurício, 26/10/2026; aresta 5 e ponto 13), trecho que o OSM traz como via comum.
--
-- Idempotente: apaga e reinsere o grafo do campus com ids fixos a cada `migrar`.
-- comprimento_m e custo são calculados AQUI, no banco, em SRID 31983 (metro).

DELETE FROM arestas;
DELETE FROM nos;
DELETE FROM pontos_interesse;

INSERT INTO pontos_interesse (id, geom, tipo, nome, descricao, acessivel, fonte_verificacao, mapeado_por, mapeado_em) VALUES
(1, ST_SetSRID(ST_MakePoint(-46.6519239, -23.5469161), 4326), 'escada', 'Escadão perto do Starbucks', 'Escada com corrimão entre os Prédios 6 e 24, de concreto.', FALSE, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(2, ST_SetSRID(ST_MakePoint(-46.6517252, -23.5469158), 4326), 'portao', 'Passagem entre os Prédios 6 e 24', 'Passagem entre os Prédios 6 e 24, no alto do escadão perto do Starbucks.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(3, ST_SetSRID(ST_MakePoint(-46.6516827, -23.5475766), 4326), 'entrada', 'Entrada do Prédio 29', 'Entrada principal do Prédio 29, em frente ao Prédio 31.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(4, ST_SetSRID(ST_MakePoint(-46.6514681, -23.5474426), 4326), 'entrada', 'Entrada do Prédio 31', 'Entrada principal do Prédio 31, em frente ao MackGraphe.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(5, ST_SetSRID(ST_MakePoint(-46.6527789, -23.5477477), 4326), 'entrada', 'Entrada do Auditório da Escola Americana', 'Entrada do Auditório da Escola Americana, perto da entrada da rua Piauí.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(6, ST_SetSRID(ST_MakePoint(-46.6520217, -23.5460134), 4326), 'entrada', 'Entrada da Biblioteca Central', 'Área aberta junto à Biblioteca Central (Prédio 2), perto do Bosque das Fadas.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(7, ST_SetSRID(ST_MakePoint(-46.6524078, -23.5470198), 4326), 'predio', 'Prédio 19', 'Prédio mapeado no OpenStreetMap (sem entrada marcada).', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(8, ST_SetSRID(ST_MakePoint(-46.6515922, -23.5465390), 4326), 'predio', 'Escola de Engenharia Mackenzie', 'Prédio mapeado no OpenStreetMap (sem entrada marcada).', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(9, ST_SetSRID(ST_MakePoint(-46.6534448, -23.5478304), 4326), 'predio', 'Clinicas-CCBS', 'Prédio mapeado no OpenStreetMap (sem entrada marcada).', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(10, ST_SetSRID(ST_MakePoint(-46.6532222, -23.5480390), 4326), 'predio', 'Auditorio Reverendo Wilson De Souza Lopes', 'Prédio mapeado no OpenStreetMap (sem entrada marcada).', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(11, ST_SetSRID(ST_MakePoint(-46.6515899, -23.5464276), 4326), 'entrada', 'Entrada aproximada: Escola de Engenharia Mackenzie', 'Ponto do caminho mais próximo deste prédio; a porta exata ainda não está no mapa aberto.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(12, ST_SetSRID(ST_MakePoint(-46.6529368, -23.5480156), 4326), 'entrada', 'Entrada aproximada: Auditorio Reverendo Wilson De Souza Lopes', 'Ponto do caminho mais próximo deste prédio; a porta exata ainda não está no mapa aberto.', NULL, 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
(13, ST_SetSRID(ST_MakePoint(-46.6527957, -23.5479377), 4326), 'escada', 'Escadaria da rua Piauí', 'Escadaria externa na saída para a rua Piauí, perto do Auditório. Não há rota sem degraus por aqui.', FALSE, 'provisorio', 'Maurício (relato de campo)', DATE '2026-10-26');

INSERT INTO nos (id, geom, ponto_interesse_id) VALUES
(1, ST_SetSRID(ST_MakePoint(-46.6518550, -23.5469724), 4326), 2),
(2, ST_SetSRID(ST_MakePoint(-46.6519928, -23.5468597), 4326), NULL),
(3, ST_SetSRID(ST_MakePoint(-46.6518618, -23.5471691), 4326), NULL),
(4, ST_SetSRID(ST_MakePoint(-46.6526546, -23.5478597), 4326), NULL),
(5, ST_SetSRID(ST_MakePoint(-46.6522857, -23.5466707), 4326), NULL),
(6, ST_SetSRID(ST_MakePoint(-46.6518536, -23.5462085), 4326), NULL),
(7, ST_SetSRID(ST_MakePoint(-46.6523289, -23.5458506), 4326), NULL),
(8, ST_SetSRID(ST_MakePoint(-46.6512036, -23.5463611), 4326), NULL),
(9, ST_SetSRID(ST_MakePoint(-46.6517554, -23.5470481), 4326), NULL),
(10, ST_SetSRID(ST_MakePoint(-46.6515598, -23.5473969), 4326), 4),
(11, ST_SetSRID(ST_MakePoint(-46.6521843, -23.5459594), 4326), 6),
(12, ST_SetSRID(ST_MakePoint(-46.6520284, -23.5463989), 4326), NULL),
(13, ST_SetSRID(ST_MakePoint(-46.6515899, -23.5464276), 4326), 11),
(14, ST_SetSRID(ST_MakePoint(-46.6513907, -23.5462141), 4326), NULL),
(15, ST_SetSRID(ST_MakePoint(-46.6513204, -23.5462696), 4326), NULL),
(16, ST_SetSRID(ST_MakePoint(-46.6517352, -23.5475012), 4326), 3),
(17, ST_SetSRID(ST_MakePoint(-46.6512382, -23.5461776), 4326), NULL),
(18, ST_SetSRID(ST_MakePoint(-46.6529368, -23.5480156), 4326), 12),
(19, ST_SetSRID(ST_MakePoint(-46.6520491, -23.5476249), 4326), NULL),
(20, ST_SetSRID(ST_MakePoint(-46.6527490, -23.5476958), 4326), 5),
(21, ST_SetSRID(ST_MakePoint(-46.6525182, -23.5466704), 4326), NULL),
(22, ST_SetSRID(ST_MakePoint(-46.6528168, -23.5464485), 4326), NULL),
(23, ST_SetSRID(ST_MakePoint(-46.6530988, -23.5464713), 4326), NULL),
(24, ST_SetSRID(ST_MakePoint(-46.6524635, -23.5457494), 4326), NULL);

INSERT INTO arestas (id, geom, origem_id, destino_id, comprimento_m, tipo, acessivel_cadeirante, custo, custo_inverso, fonte_verificacao, mapeado_por, mapeado_em)
SELECT id, geom, origem_id, destino_id, len, tipo, acessivel_cadeirante, len, len,
       fonte_verificacao, mapeado_por, mapeado_em
FROM (
    SELECT v.id, v.origem_id, v.destino_id, v.tipo, v.acessivel_cadeirante,
           v.fonte_verificacao, v.mapeado_por, v.mapeado_em, g.geom,
           ST_Length(ST_Transform(g.geom, 31983)) AS len
    FROM (VALUES
        (1, 1, 2, 'escada', FALSE, 'LINESTRING(-46.6518550 -23.5469724, -46.6519928 -23.5468597)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (2, 2, 5, 'calcada', NULL, 'LINESTRING(-46.6519928 -23.5468597, -46.6522857 -23.5466707)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (3, 4, 20, 'calcada', NULL, 'LINESTRING(-46.6526546 -23.5478597, -46.6527490 -23.5476958)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (4, 5, 21, 'calcada', NULL, 'LINESTRING(-46.6522857 -23.5466707, -46.6523919 -23.5465929, -46.6524191 -23.5465794, -46.6524451 -23.5465883, -46.6525182 -23.5466704)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (5, 18, 4, 'escada', FALSE, 'LINESTRING(-46.6529368 -23.5480156, -46.6526546 -23.5478597)', 'provisorio', 'Maurício (relato de campo)', DATE '2026-10-26'),
        (6, 20, 2, 'calcada', NULL, 'LINESTRING(-46.6527490 -23.5476958, -46.6527464 -23.5476228, -46.6519928 -23.5468597)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (7, 21, 23, 'calcada', NULL, 'LINESTRING(-46.6525182 -23.5466704, -46.6526421 -23.5468093, -46.6530166 -23.5465303, -46.6530456 -23.5465084, -46.6530988 -23.5464713)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (8, 5, 12, 'calcada', NULL, 'LINESTRING(-46.6522857 -23.5466707, -46.6520284 -23.5463989)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (9, 6, 11, 'calcada', NULL, 'LINESTRING(-46.6518536 -23.5462085, -46.6521843 -23.5459594)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (10, 7, 24, 'calcada', NULL, 'LINESTRING(-46.6523289 -23.5458506, -46.6523635 -23.5458221, -46.6523996 -23.5457973, -46.6524635 -23.5457494)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (11, 11, 7, 'calcada', NULL, 'LINESTRING(-46.6521843 -23.5459594, -46.6523289 -23.5458506)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (12, 12, 6, 'calcada', NULL, 'LINESTRING(-46.6520284 -23.5463989, -46.6518536 -23.5462085)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (13, 7, 14, 'calcada', NULL, 'LINESTRING(-46.6523289 -23.5458506, -46.6521459 -23.5456555, -46.6521251 -23.5456432, -46.6521055 -23.5456445, -46.6513907 -23.5462141)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (14, 14, 15, 'calcada', NULL, 'LINESTRING(-46.6513907 -23.5462141, -46.6513204 -23.5462696)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (15, 15, 8, 'calcada', NULL, 'LINESTRING(-46.6513204 -23.5462696, -46.6512036 -23.5463611)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (16, 2, 13, 'calcada', NULL, 'LINESTRING(-46.6519928 -23.5468597, -46.6515899 -23.5464276)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (17, 13, 14, 'calcada', NULL, 'LINESTRING(-46.6515899 -23.5464276, -46.6513907 -23.5462141)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (18, 1, 9, 'calcada', NULL, 'LINESTRING(-46.6518550 -23.5469724, -46.6517554 -23.5470481)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (19, 11, 12, 'calcada', NULL, 'LINESTRING(-46.6521843 -23.5459594, -46.6523525 -23.5461495, -46.6520284 -23.5463989)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (20, 6, 13, 'calcada', NULL, 'LINESTRING(-46.6518536 -23.5462085, -46.6515899 -23.5464276)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (21, 15, 17, 'calcada', NULL, 'LINESTRING(-46.6513204 -23.5462696, -46.6512382 -23.5461776)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (22, 3, 19, 'calcada', NULL, 'LINESTRING(-46.6518618 -23.5471691, -46.6519826 -23.5471850, -46.6521218 -23.5473356, -46.6521201 -23.5473595, -46.6520859 -23.5473946, -46.6520854 -23.5474188, -46.6520927 -23.5474936, -46.6520780 -23.5475519, -46.6520491 -23.5476249)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (23, 4, 19, 'calcada', NULL, 'LINESTRING(-46.6526546 -23.5478597, -46.6520491 -23.5476249)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (24, 16, 10, 'calcada', NULL, 'LINESTRING(-46.6517352 -23.5475012, -46.6515598 -23.5473969)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (25, 19, 16, 'calcada', NULL, 'LINESTRING(-46.6520491 -23.5476249, -46.6517352 -23.5475012)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26'),
        (26, 22, 21, 'calcada', NULL, 'LINESTRING(-46.6528168 -23.5464485, -46.6525182 -23.5466704)', 'provisorio', 'OpenStreetMap (contribuidores)', DATE '2026-10-26')
    ) AS v(id, origem_id, destino_id, tipo, acessivel_cadeirante, wkt, fonte_verificacao, mapeado_por, mapeado_em)
    CROSS JOIN LATERAL (SELECT ST_GeomFromText(v.wkt, 4326) AS geom) AS g
) AS t;

SELECT setval(pg_get_serial_sequence('pontos_interesse', 'id'), GREATEST((SELECT max(id) FROM pontos_interesse), 1));
SELECT setval(pg_get_serial_sequence('nos', 'id'), GREATEST((SELECT max(id) FROM nos), 1));
SELECT setval(pg_get_serial_sequence('arestas', 'id'), GREATEST((SELECT max(id) FROM arestas), 1));
