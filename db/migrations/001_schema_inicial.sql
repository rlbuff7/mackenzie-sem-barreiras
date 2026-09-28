-- 001: schema inicial do Mackenzie sem Barreiras (M1).
--
-- Aplicada por ./db/banco.sh migrar, dentro de uma transação.
-- IMUTÁVEL depois de aplicada: qualquer correção vira uma migration nova.
--
-- Unidades: toda geometria é armazenada em SRID 4326 (graus). Distâncias em
-- metros são calculadas no código reprojetando para 31983 (CLAUDE.md §5).

-- Já habilitada por db/init/ no container local; repetida aqui para que o
-- schema seja reproduzível num Postgres que não passe por aquele init.
CREATE EXTENSION IF NOT EXISTS postgis;


-- ---------------------------------------------------------------------------
-- Referência
-- ---------------------------------------------------------------------------

-- Taxonomia em tabela, não em ENUM: a lista ainda será fechada com a orientadora
-- e ENUM exigiria migration a cada mudança.
CREATE TABLE IF NOT EXISTS tipos_barreira (
    id          SERIAL      PRIMARY KEY,
    codigo      VARCHAR(40) NOT NULL UNIQUE,   -- identificador estável usado pelos seeds e pelo frontend
    nome        VARCHAR(80) NOT NULL,
    descricao   TEXT,
    -- Tipo aposentado continua na tabela porque alertas antigos o referenciam.
    ativo       BOOLEAN     NOT NULL DEFAULT true
);

-- Polígono contra o qual o geofence (estágio 2) roda.
CREATE TABLE IF NOT EXISTS area_estudo (
    id          SERIAL      PRIMARY KEY,
    nome        VARCHAR(80) NOT NULL UNIQUE,
    descricao   TEXT,
    geom        GEOMETRY(Polygon, 4326) NOT NULL,
    -- Polígono inválido (auto-interseção) faz ST_Within responder errado sem erro.
    CONSTRAINT area_estudo_geom_valida CHECK (ST_IsValid(geom))
);


-- ---------------------------------------------------------------------------
-- Barreiras: o que sobreviveu à validação
-- ---------------------------------------------------------------------------

-- Criada antes de `alertas`, que a referencia.
CREATE TABLE IF NOT EXISTS barreiras (
    id              BIGSERIAL   PRIMARY KEY,
    geom            GEOMETRY(Point, 4326) NOT NULL,   -- centroide do cluster
    tipo_id         INT         NOT NULL REFERENCES tipos_barreira (id),
    -- Número de SESSÕES DISTINTAS no cluster (não de alertas): é o que impede
    -- uma pessoa sozinha de "confirmar" uma barreira (CLAUDE.md §6, estágio 4).
    confirmacoes    INT         NOT NULL CHECK (confirmacoes >= 1),
    status          VARCHAR(16) NOT NULL DEFAULT 'pendente'
                    CHECK (status IN ('pendente', 'confirmada')),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- Alertas: tudo o que chega com formato válido, inclusive o que é descartado
-- ---------------------------------------------------------------------------

-- Ciclo de vida (status):
--   bruto          chegou, passou do schema e do geofence; aguarda o pipeline
--   descartado     final; o motivo fica em motivo_descarte (ex.: fora_da_area)
--   ruido_isolado  sem vizinhos no DBSCAN; NÃO é final: volta a ser avaliado
--                  quando chegarem alertas novos (docs/decisoes-pendentes.md, T4)
--   agrupado       pertence a um cluster, ligado a uma barreira via barreira_id
CREATE TABLE IF NOT EXISTS alertas (
    id              BIGSERIAL   PRIMARY KEY,
    geom            GEOMETRY(Point, 4326) NOT NULL,
    -- NOT NULL: o DBSCAN particiona por tipo; tipo nulo viraria uma partição fantasma.
    tipo_id         INT         NOT NULL REFERENCES tipos_barreira (id),
    severidade      SMALLINT    CHECK (severidade BETWEEN 1 AND 3),
    descricao       TEXT,
    -- NOT NULL: COUNT(DISTINCT sessao_hash) ignora NULL em silêncio, e um alerta
    -- sem sessão nunca contaria como confirmação.
    sessao_hash     VARCHAR(64) NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          VARCHAR(24) NOT NULL DEFAULT 'bruto'
                    CHECK (status IN ('bruto', 'descartado', 'ruido_isolado', 'agrupado')),
    -- Sem CHECK de valores: motivos novos não devem exigir migration.
    motivo_descarte VARCHAR(48),
    barreira_id     BIGINT      REFERENCES barreiras (id),

    CONSTRAINT alertas_motivo_sse_descartado
        CHECK ((status = 'descartado') = (motivo_descarte IS NOT NULL)),
    CONSTRAINT alertas_barreira_sse_agrupado
        CHECK ((status = 'agrupado') = (barreira_id IS NOT NULL))
);

-- Payloads reprovados no estágio 1 (schema). Ficam fora de `alertas` porque um
-- lat=200 ou um tipo inexistente não passariam pelas constraints acima.
-- Decidido em 28/09/2026 (docs/decisoes-pendentes.md, T1).
CREATE TABLE IF NOT EXISTS alertas_rejeitados (
    id          BIGSERIAL   PRIMARY KEY,
    payload     JSONB       NOT NULL,   -- corpo recebido, como chegou
    erros       JSONB       NOT NULL,   -- erros de validação do schema
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- Índices
-- ---------------------------------------------------------------------------

-- Índices espaciais GiST (o artigo fala em R-Tree; o PostGIS implementa R-Tree
-- sobre GiST). Atendem a consulta por bbox de GET /barreiras (operador &&).
CREATE INDEX IF NOT EXISTS idx_alertas_geom   ON alertas   USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_barreiras_geom ON barreiras USING GIST (geom);

-- O Postgres não indexa FKs sozinho; as contagens por barreira usam este join.
CREATE INDEX IF NOT EXISTS idx_alertas_barreira_id ON alertas (barreira_id);
