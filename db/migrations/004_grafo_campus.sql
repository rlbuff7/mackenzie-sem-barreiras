-- 004: grafo pedonal do campus (M1 do escopo novo, CLAUDE.md §4 e §6).
--
-- pontos_interesse: o que pode ser citado numa orientação (prédio, entrada...).
-- nos:              vértices do grafo.
-- arestas:          trechos caminháveis; é a tabela que o pgRouting consome
--                   (custo / custo_inverso).
--
-- Tudo armazenado em SRID 4326 (grau). Comprimento e custo são calculados em
-- 31983 (metro) por quem insere; ver §5 do CLAUDE.md. Sem dados aqui: o que for
-- do campus mapeado entra em db/seeds/.
--
-- ATENÇÃO: as listas de `tipo` abaixo são CHECK constraints (e não ENUM nem
-- tabela de referência). Mudar a lista exige uma migration nova que troque a
-- constraint; esta migration não pode ser editada depois de aplicada.

CREATE EXTENSION IF NOT EXISTS pgrouting;

CREATE TABLE IF NOT EXISTS pontos_interesse (
    id        BIGSERIAL PRIMARY KEY,
    geom      GEOMETRY(Point, 4326) NOT NULL,
    tipo      VARCHAR(32)  NOT NULL
              CONSTRAINT pontos_interesse_tipo_valido
              CHECK (tipo IN ('predio', 'entrada', 'escada', 'rampa', 'quadra', 'portao')),
    nome      VARCHAR(120) NOT NULL,
    descricao TEXT,              -- texto para leitura em voz
    acessivel BOOLEAN            -- NULL = não verificado
);

CREATE TABLE IF NOT EXISTS nos (
    id                 BIGSERIAL PRIMARY KEY,
    geom               GEOMETRY(Point, 4326) NOT NULL,
    ponto_interesse_id BIGINT REFERENCES pontos_interesse(id)  -- quando o nó É uma entrada
);

CREATE TABLE IF NOT EXISTS arestas (
    id                   BIGSERIAL PRIMARY KEY,
    geom                 GEOMETRY(LineString, 4326) NOT NULL,
    origem_id            BIGINT NOT NULL REFERENCES nos(id),
    destino_id           BIGINT NOT NULL REFERENCES nos(id),
    comprimento_m        DOUBLE PRECISION NOT NULL,   -- calculado em 31983 (metro)
    tipo                 VARCHAR(32) NOT NULL,
    acessivel_cadeirante BOOLEAN,                     -- NULL = não verificado
    custo                DOUBLE PRECISION NOT NULL,   -- comprimento + penalidades (§6)
    custo_inverso        DOUBLE PRECISION NOT NULL,   -- -1 quando o trecho é de mão única
    CONSTRAINT arestas_tipo_valido
        CHECK (tipo IN ('calcada', 'rampa', 'escada', 'travessia')),
    CONSTRAINT arestas_comprimento_positivo CHECK (comprimento_m > 0),
    CONSTRAINT arestas_custo_nao_negativo   CHECK (custo >= 0),
    CONSTRAINT arestas_custo_inverso_valido CHECK (custo_inverso = -1 OR custo_inverso >= 0),
    CONSTRAINT arestas_origem_diferente_destino CHECK (origem_id <> destino_id)
);

CREATE INDEX IF NOT EXISTS idx_poi_geom        ON pontos_interesse USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_nos_geom        ON nos              USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_arestas_geom    ON arestas          USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_arestas_origem  ON arestas (origem_id);
CREATE INDEX IF NOT EXISTS idx_arestas_destino ON arestas (destino_id);
