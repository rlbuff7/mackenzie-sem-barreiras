-- 006: pontos de controle do campus e o erro das medições de GPS (card "Análise
-- da medição de GPS"). Fonte dos pontos: docs/medicao-gps.md (Maurício, TCC 1).
--
-- pontos_controle: onde ficam os pontos P01..P10. As coordenadas de referência são
--   ESTIMATIVAS por imagem de satélite, não topografia (origem_referencia). O erro
--   calculado nas views é, portanto, "distância até a referência estimada": inclui
--   a incerteza da própria referência.
-- condicao: usa os MESMOS valores de medicoes_gps.condicao (005; é o que o app envia:
--   ceu_aberto, entre_predios, coberto). O rótulo do Maurício "Entrada de prédio" não
--   existe no app: foi mapeado para 'coberto' e o rótulo original fica em
--   rotulo_condicao_original, para não perder a informação.
-- Sem FK de medicoes_gps.ponto para esta tabela: o app aceita ponto 1..12 e só há 10
--   pontos de controle; uma FK faria o servidor rejeitar medições dos pontos 11 e 12
--   (e mudaria o contrato da API). As views fazem o JOIN; medição de ponto sem
--   referência simplesmente não entra na análise de erro.
-- Distância SEMPRE em SRID 31983 (metro), nunca em 4326 (grau): CLAUDE.md §5.
-- Os dados dos pontos ficam em db/seeds/003_pontos_controle.sql.

CREATE TABLE IF NOT EXISTS pontos_controle (
    numero                   SMALLINT PRIMARY KEY
                             CONSTRAINT pontos_controle_numero_na_faixa
                             CHECK (numero BETWEEN 1 AND 12),
    codigo                   VARCHAR(3) NOT NULL
                             CONSTRAINT pontos_controle_codigo_unico UNIQUE,
    nome                     VARCHAR(120) NOT NULL,
    condicao                 VARCHAR(20) NOT NULL
                             CONSTRAINT pontos_controle_condicao_valida
                             CHECK (condicao IN ('ceu_aberto', 'entre_predios', 'coberto')),
    rotulo_condicao_original VARCHAR(40),
    geom_referencia          GEOMETRY(Point, 4326) NOT NULL,
    origem_referencia        TEXT NOT NULL
                             DEFAULT 'imagem de satélite (estimativa, não topografia)',
    observacao               TEXT,
    CONSTRAINT pontos_controle_codigo_confere_numero
        CHECK (codigo = 'P' || lpad(numero::text, 2, '0')),
    CONSTRAINT pontos_controle_nome_nao_vazio
        CHECK (char_length(btrim(nome)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_pontos_controle_geom
    ON pontos_controle USING GIST (geom_referencia);

-- Uma linha por medição tipo 'ponto' que tem referência: erro_m é a distância,
-- em METROS, entre a posição medida e a referência (31983).
CREATE OR REPLACE VIEW vw_erro_medicoes AS
SELECT m.id,
       m.id_cliente,
       m.medido_em,
       m.aparelho,
       p.numero AS ponto,
       p.codigo AS ponto_codigo,
       p.nome   AS ponto_nome,
       m.condicao,
       m.precisao_m,
       ST_Distance(ST_Transform(m.geom, 31983),
                   ST_Transform(p.geom_referencia, 31983)) AS erro_m
FROM medicoes_gps m
JOIN pontos_controle p ON p.numero = m.ponto
WHERE m.tipo = 'ponto'
  AND m.geom IS NOT NULL;

-- Resumo por ponto x aparelho: n, mediana e p90 do erro (metros) e a fração das
-- medições em que o erro ficou dentro da precisão que o celular reportou
-- (fracao_erro_dentro_precisao: 1,0 = o aparelho "dizia a verdade" sempre).
CREATE OR REPLACE VIEW vw_erro_por_ponto_aparelho AS
SELECT ponto,
       ponto_codigo,
       aparelho,
       count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY erro_m) AS erro_mediana_m,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY erro_m) AS erro_p90_m,
       avg((erro_m <= precisao_m)::int)::double precision AS fracao_erro_dentro_precisao
FROM vw_erro_medicoes
GROUP BY ponto, ponto_codigo, aparelho;
