-- 005: medições de GPS em tempo real (página /medicao.html, contrato de 14/10/2026).
--
-- Dado DA EQUIPE: os celulares dela nos pontos de controle do campus, enviados na
-- hora (com fila no celular quando falta sinal). Não é dado de quem navega: a
-- posição de quem NAVEGA continua nunca sendo gravada (regra do M4). Sem nome de
-- pessoa: só o modelo do aparelho, em texto livre ("Galaxy A54").
--
-- id_cliente:  UUID gerado no celular; o UNIQUE torna o reenvio idempotente
--              (a API usa ON CONFLICT (id_cliente) DO NOTHING).
-- medido_em:   horário no celular. recebido_em: horário no servidor.
-- geom:        SRID 4326 (grau). A distância se calcula em 31983 (metro) por quem
--              consulta; precisao_m é a incerteza que o navegador informa, em metro.
--
-- ATENÇÃO: as listas (tipo, condicao, bussola_fonte) são CHECK constraints, como
-- na 004. Mudar a lista exige migration nova que troque a constraint; esta não
-- pode ser editada depois de aplicada. Sem dados aqui.

CREATE TABLE IF NOT EXISTS medicoes_gps (
    id                      BIGSERIAL PRIMARY KEY,
    id_cliente              UUID NOT NULL
                            CONSTRAINT medicoes_gps_id_cliente_unico UNIQUE,
    tipo                    VARCHAR(16) NOT NULL,
    medido_em               TIMESTAMPTZ NOT NULL,
    recebido_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    aparelho                VARCHAR(80) NOT NULL,
    ponto                   SMALLINT,
    condicao                VARCHAR(20),
    geom                    GEOMETRY(Point, 4326),
    precisao_m              DOUBLE PRECISION,
    altitude_m              DOUBLE PRECISION,
    altitude_precisao_m     DOUBLE PRECISION,
    velocidade_ms           DOUBLE PRECISION,
    rumo_gps_graus          DOUBLE PRECISION,
    bussola_graus           DOUBLE PRECISION,
    bussola_fonte           VARCHAR(24),
    bussola_oscilacao_graus DOUBLE PRECISION,
    vibracao_suportada      BOOLEAN,
    observacao              VARCHAR(500),
    user_agent              VARCHAR(300),
    CONSTRAINT medicoes_gps_tipo_valido
        CHECK (tipo IN ('ponto', 'trajeto', 'bussola', 'vibracao')),
    CONSTRAINT medicoes_gps_aparelho_nao_vazio
        CHECK (char_length(btrim(aparelho)) > 0),
    CONSTRAINT medicoes_gps_ponto_na_faixa
        CHECK (ponto BETWEEN 1 AND 12),
    CONSTRAINT medicoes_gps_ponto_obrigatorio_no_tipo_ponto
        CHECK (tipo <> 'ponto' OR ponto IS NOT NULL),
    CONSTRAINT medicoes_gps_condicao_valida
        CHECK (condicao IN ('ceu_aberto', 'entre_predios', 'coberto')),
    CONSTRAINT medicoes_gps_geom_e_precisao_obrigatorias
        CHECK (tipo NOT IN ('ponto', 'trajeto')
               OR (geom IS NOT NULL AND precisao_m IS NOT NULL)),
    CONSTRAINT medicoes_gps_precisao_obrigatoria_com_geom
        CHECK (geom IS NULL OR precisao_m IS NOT NULL),
    CONSTRAINT medicoes_gps_precisao_nao_negativa
        CHECK (precisao_m >= 0),
    CONSTRAINT medicoes_gps_bussola_na_faixa
        CHECK (bussola_graus >= 0 AND bussola_graus < 360),
    CONSTRAINT medicoes_gps_bussola_fonte_valida
        CHECK (bussola_fonte IN ('webkitCompassHeading', 'alpha_absoluto', 'alpha_relativo')),
    CONSTRAINT medicoes_gps_bussola_oscilacao_nao_negativa
        CHECK (bussola_oscilacao_graus >= 0)
);

CREATE INDEX IF NOT EXISTS idx_medicoes_gps_geom
    ON medicoes_gps USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_medicoes_gps_medido_em
    ON medicoes_gps (medido_em);
CREATE INDEX IF NOT EXISTS idx_medicoes_gps_aparelho_ponto
    ON medicoes_gps (aparelho, ponto);
