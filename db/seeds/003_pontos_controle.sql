-- Pontos de controle P01..P10 escolhidos pelo Maurício (docs/medicao-gps.md, prazo
-- 19/10/2026). Coordenadas = estimativa por imagem de satélite, não topografia.
-- Condição: 'Entrada de prédio' (rótulo do documento) vira 'coberto' (valor do app);
-- o rótulo original fica em rotulo_condicao_original.
--
-- Idempotente: reaplicado a cada `./db/banco.sh migrar`, com ON CONFLICT DO UPDATE
-- (o documento é a fonte; corrigir o texto aqui corrige o banco, como nos outros
-- seeds). ATENÇÃO: mudar uma coordenada depois das medições muda o erro_m de todas
-- elas, então só mude com decisão registrada.
-- A observação é copiada do documento sem correção ortográfica.

INSERT INTO pontos_controle
    (numero, codigo, nome, condicao, rotulo_condicao_original, geom_referencia, observacao)
VALUES
    (1, 'P01', 'Praça de convivência próxima ao Prédio 18', 'ceu_aberto', 'Céu aberto',
     ST_SetSRID(ST_MakePoint(-46.65279158889783, -23.54667967656296), 4326), 'Praça em frente ao Auditório Ruy Barbosa'),
    (2, 'P02', 'Área aberta próxima à Biblioteca Central (Prédio 2)', 'ceu_aberto', 'Céu aberto',
     ST_SetSRID(ST_MakePoint(-46.65202165910552, -23.546013383953508), 4326), 'Próximo ao Bosque das Fadas e a Ultra Coffee Mackenzie'),
    (3, 'P03', 'Passagem entre os Prédios 6 e 24', 'entre_predios', 'Entre prédios',
     ST_SetSRID(ST_MakePoint(-46.65172517217903, -23.546915816255126), 4326), 'Próximo ao escadão que da acesso a frente do Starbucks'),
    (4, 'P04', 'Entrada principal do Prédio 29', 'coberto', 'Entrada de prédio',
     ST_SetSRID(ST_MakePoint(-46.6516827262256, -23.54757664389376), 4326), 'Em frente ao predio 31 e Colado ao Predio do MackGraphe'),
    (5, 'P05', 'Entrada principal do Prédio 31', 'coberto', 'Entrada de prédio',
     ST_SetSRID(ST_MakePoint(-46.65146814951144, -23.54744263607399), 4326), 'Em frente ao MackGraphe'),
    (6, 'P06', 'Entrada do Auditório da Escola Americana', 'coberto', 'Entrada de prédio',
     ST_SetSRID(ST_MakePoint(-46.652778943818376, -23.547747707942488), 4326), 'Próximo a entrada da rua Piauí'),
    (7, 'P07', 'Bifurcação de caminhos do campus', 'ceu_aberto', 'Céu aberto',
     ST_SetSRID(ST_MakePoint(-46.652032195907886, -23.5468504473735), 4326), 'Próximo ao Starbucks'),
    (8, 'P08', 'Início de uma escadaria externa do campus', 'entre_predios', 'Entre prédios',
     ST_SetSRID(ST_MakePoint(-46.65280467209573, -23.547931731633664), 4326), 'Escadaria de saída para a rua Piauí'),
    (9, 'P09', 'Caminho próximo às quadras poliesportivas', 'ceu_aberto', 'Céu aberto',
     ST_SetSRID(ST_MakePoint(-46.65230980453806, -23.547712278983497), 4326), 'Caminho entre as quadras poliesportivas e o prédio 45.'),
    (10, 'P10', 'Área de circulação próxima ao Auditório da Escola Americana', 'ceu_aberto', 'Céu aberto',
     ST_SetSRID(ST_MakePoint(-46.65275773344059, -23.547640357443996), 4326), 'Área externa próxima ao auditório onde ficam algumas vagas especiais para cadeirantes.')
ON CONFLICT (numero) DO UPDATE
    SET codigo                   = EXCLUDED.codigo,
        nome                     = EXCLUDED.nome,
        condicao                 = EXCLUDED.condicao,
        rotulo_condicao_original = EXCLUDED.rotulo_condicao_original,
        geom_referencia          = EXCLUDED.geom_referencia,
        observacao               = EXCLUDED.observacao;
