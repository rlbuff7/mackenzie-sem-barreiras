-- Área de estudo PROVISÓRIA: círculo de 500 m em torno do centroide do campus
-- Higienópolis do Mackenzie (OpenStreetMap, consultado em 28/09/2026). O polígono
-- definitivo depende da orientadora (docs/decisoes-pendentes.md, #3).
--
-- O buffer é calculado em `geography` para que os 500 sejam METROS. Em `geometry`
-- 4326 seriam 500 GRAUS (CLAUDE.md §5). O resultado volta para geometry 4326,
-- como um polígono de 32 lados.
--
-- Idempotente: reaplicado a cada `./db/banco.sh migrar`.

INSERT INTO area_estudo (nome, descricao, geom) VALUES (
    'entorno_mackenzie_provisorio',
    'PROVISÓRIO: raio de 500 m em torno do centroide do campus Higienópolis (OSM).',
    ST_Buffer(
        ST_SetSRID(ST_MakePoint(-46.6524631, -23.5471938), 4326)::geography,
        500  -- metros
    )::geometry
)
ON CONFLICT (nome) DO UPDATE
    SET descricao = EXCLUDED.descricao,
        geom      = EXCLUDED.geom;
