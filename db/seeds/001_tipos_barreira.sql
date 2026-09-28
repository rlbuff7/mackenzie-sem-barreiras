-- Taxonomia PROVISÓRIA de tipos de barreira: os quatro tipos citados no pôster
-- do TCC I. A lista final depende da orientadora (docs/decisoes-pendentes.md, #2).
--
-- Idempotente: reaplicado a cada `./db/banco.sh migrar`. Para aposentar um tipo,
-- marque ativo = false (alertas antigos continuam apontando para ele); não apague.

INSERT INTO tipos_barreira (codigo, nome, descricao) VALUES
    ('calcada_irregular', 'Calçada irregular',
     'Piso quebrado, desnivelado, com buracos ou raízes expostas.'),
    ('ausencia_rampa',    'Ausência de rampa',
     'Travessia ou desnível sem rampa de acesso ou rebaixamento de guia.'),
    ('degrau',            'Degrau',
     'Degrau isolado ou escada sem alternativa acessível.'),
    ('obstaculo',         'Obstáculo',
     'Objeto que bloqueia a faixa livre: poste, lixeira, mesa, veículo, entulho.')
ON CONFLICT (codigo) DO UPDATE
    SET nome      = EXCLUDED.nome,
        descricao = EXCLUDED.descricao;
