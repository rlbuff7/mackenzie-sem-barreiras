-- Executado UMA vez pelo entrypoint do Postgres, quando o volume está vazio.
--
-- Substitui o script padrão da imagem postgis/postgis, que também instalaria
-- postgis_tiger_geocoder (geocodificador do censo dos EUA), postgis_topology
-- e fuzzystrmatch. Nenhum deles é usado aqui.
--
-- Tabelas e dados NÃO entram aqui: isso é trabalho das migrations (db/migrations/).
CREATE EXTENSION IF NOT EXISTS postgis;
