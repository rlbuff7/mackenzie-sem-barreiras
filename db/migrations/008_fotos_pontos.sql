-- 008: fotos dos pontos de controle (contrato de 22/10/2026).
--
-- Dado DA EQUIPE (nunca de quem navega): uma ou mais fotos por ponto x aparelho, para
-- registrar a marca física onde a equipe ficou parada e a condição do lugar. Sem
-- pessoas no enquadramento e sem metadados (EXIF/GPS) no arquivo: o app reprocessa a
-- imagem num canvas e a API recusa JPEG com EXIF.
--
-- id_cliente: UUID gerado no celular; o UNIQUE torna o reenvio idempotente
--             (a API usa ON CONFLICT (id_cliente) DO NOTHING).
-- conteudo:   JPEG em bytes (até 1 MiB). tamanho_bytes tem de bater com o conteúdo.
-- sha256:     hex do conteúdo, calculado pela API.

CREATE TABLE IF NOT EXISTS fotos_pontos (
    id            BIGSERIAL PRIMARY KEY,
    id_cliente    UUID NOT NULL
                  CONSTRAINT fotos_pontos_id_cliente_unico UNIQUE,
    ponto         SMALLINT NOT NULL,
    aparelho      TEXT NOT NULL,
    tirada_em     TIMESTAMPTZ NOT NULL,
    recebida_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    conteudo      BYTEA NOT NULL,
    tamanho_bytes INT NOT NULL,
    largura_px    SMALLINT,
    altura_px     SMALLINT,
    sha256        CHAR(64) NOT NULL,
    observacao    TEXT,
    CONSTRAINT fotos_pontos_ponto_valido CHECK (ponto BETWEEN 1 AND 12),
    CONSTRAINT fotos_pontos_aparelho_valido CHECK (char_length(aparelho) BETWEEN 1 AND 80),
    CONSTRAINT fotos_pontos_tamanho_valido CHECK (
        tamanho_bytes BETWEEN 1 AND 1048576 AND tamanho_bytes = octet_length(conteudo)),
    CONSTRAINT fotos_pontos_largura_valida CHECK (largura_px IS NULL OR largura_px BETWEEN 1 AND 2048),
    CONSTRAINT fotos_pontos_altura_valida CHECK (altura_px IS NULL OR altura_px BETWEEN 1 AND 2048),
    CONSTRAINT fotos_pontos_observacao_valida CHECK (observacao IS NULL OR char_length(observacao) <= 500)
);

CREATE INDEX IF NOT EXISTS idx_fotos_pontos_ponto_aparelho ON fotos_pontos (ponto, aparelho);
