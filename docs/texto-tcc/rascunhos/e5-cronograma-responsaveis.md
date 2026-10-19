# E5 — Cronograma e divisão de responsabilidades

> **RASCUNHO para revisão da equipe — gerado em 19/10/2026; nada aqui foi aprovado pela orientadora.**
>
> Marcações abertas: **[REF?]** citação nova a localizar; **[CONFERIR IBGE]** dado a conferir na fonte; **[DECIDIR COM A ORIENTADORA]** decisão que não é da equipe. Fonte do escopo: `CLAUDE.md` do escopo novo (14/10/2026) e cartões do Kanban no Notion (lidos em 19/10/2026).

Cartão do Kanban: E5 (prazo 20/10/2026). A tabela de fases é a **proposta de 14/10/2026** do cartão, no formato do cronograma oficial: cada coluna é um mês, de agosto/2026 a maio/2027 (A S O N D J F M A M). O cronograma oficial é: TCC I até novembro (banner com protótipo no começo de novembro, Projeto Parcial em novembro), desenvolvimento de dezembro a fevereiro, TCC II de fevereiro a maio, avaliação com usuários em abril, defesa em maio/2027. As datas finais do TCC II e a data exata do banner devem ser **confirmadas com a universidade** (passo 1 do cartão).

## 1 Cronograma por mês

`X` = a atividade acontece no mês. Itálico no Notion marca o que mudou com o escopo novo.

| Etapas e atividades | A | S | O | N | D | J | F | M | A | M |
|---|---|---|---|---|---|---|---|---|---|---|
| **Fase 1 — Fundamentação e planejamento (TCC I)** | | | | | | | | | | |
| Levantamento bibliográfico (refeito em outubro: navegação assistiva e orientação espacial) | X | X | X | | | | | | | |
| Escopo e requisitos RF/RNF (E1, E2) | | X | X | | | | | | | |
| Medição de GPS no campus e estudo de localização e áudio (E3) | | | X | | | | | | | |
| Design da arquitetura, seleção de APIs e modelagem do grafo (PostGIS + pgRouting) | | | X | X | | | | | | |
| Protótipo funcional e banner (E6) | | | X | X | | | | | | |
| Protocolo de avaliação e submissão ao CEP | | | X | X | | | | | | |
| Redação, revisão e entrega do Projeto Parcial (TCC I) | | | | X | | | | | | |
| **Fase 2 — Desenvolvimento tecnológico (férias e retorno)** | | | | | | | | | | |
| Configuração de infraestrutura: AWS e banco com pgRouting (sem chaves pagas) | | | X | X | X | | | | | |
| Mapeamento do recorte do campus (M2) | | | | X | X | | | | | |
| Codificação do backend: rotas (M3) e módulo de orientação (M4) | | | | | X | X | X | | | |
| Codificação do frontend: navegação acessível com voz e vibração (M5) | | | | | | X | X | | | |
| **Fase 3 — Validação e conclusão (TCC II)** | | | | | | | | | | |
| Integração e refatoração (contingência) | | | | | | | X | X | | |
| Testes em ambiente controlado: teste interno com vendas (**simulação**) e calibração | | | | | | | | X | X | |
| Avaliação com usuários (depois do CEP; plano B com especialistas) | | | | | | | | | X | |
| Análise dos resultados e validação da hipótese | | | | | | | | | X | X |
| Redação do documento final, adequações e defesa (TCC II) | | | | | | | | | | X |

Saíram do cronograma antigo: chaves do Google Maps (custo zero), frontend de coleta, filtros estatísticos e coleta por crowdsourcing.

**Observação para revisão.** O M5 (prazo 26/02/2027) termina no mesmo mês em que começa a "integração e refatoração (contingência)" da Fase 3, então a folga entre desenvolvimento e TCC II é praticamente nula. A equipe deve conferir se isso é aceitável.

## 2 Marcos e datas do Kanban (outubro a dezembro)

| Data | Marco | Responsável |
|---|---|---|
| 20/10 | E1 (escopo), E4 (plano de mapeamento), E5 (este cronograma); plano B de produção local; `TOKEN_ADMIN`/`EXPOR_DOCS` na infra | Equipe; Victor |
| 21/10 | Levantar o prazo e os documentos do CEP | Maurício |
| 22/10 | E2 (requisitos); **medição de GPS no campus** (duas pessoas, ~2 h, um Android e um iPhone) | Equipe; Maurício |
| 23/10 | Primeiro trecho do campus mapeado; conferir a lista de autores | Maurício; Rodrigo |
| 26/10 | Análise da medição de GPS | Maurício |
| ~27/10 | Reunião com a orientadora (pendências 1 a 8); E3 (arquitetura e estudo de localização e áudio); corrigir o texto do TCC I | Orientadora; Equipe |
| 28/10 | Protocolo de avaliação e termo de consentimento (CEP); deploy automático na AWS | Maurício; Rodrigo |
| 29/10 | E6: protótipo funcional (mapa, destino, rota, uma orientação falada) | Rodrigo |
| 30/10 | Banner pronto para imprimir; decidir o nome do repositório | Equipe |
| ~03/11 | Apresentação do banner com o protótipo | Equipe |
| 20/11 | Submeter o projeto ao CEP pela Plataforma Brasil | Maurício |
| 27/11 | Entrega do Projeto Parcial (TCC I) | Equipe |
| 11/12 | M2: recorte completo do campus mapeado | Maurício |
| 15/01/2027 | M3: `/pontos-interesse` e `/rotas` | Rodrigo |
| 12/02/2027 | M4: módulo de orientação e `/orientacoes` | Rodrigo |
| 26/02/2027 | M5: frontend acessível (destino, rota, voz, vibração) | Rodrigo |
| Abril/2027 | Avaliação com usuários, se o CEP aprovar | Equipe, Maurício |
| Maio/2027 | Defesa | Equipe |

Datas "~" e as do TCC II dependem de confirmação da universidade e da orientadora.

## 3 Divisão de responsabilidades (14/10/2026)

| Pessoa | Responsabilidade |
|---|---|
| **Rodrigo** | Código (backend, frontend, banco no código), AWS (conta e créditos dele), deploy automático, M3, M4, M5 e protótipo E6 |
| **Victor** | Infra: banco com pgRouting, plano B de produção local com túnel HTTPS, `TOKEN_ADMIN` e `EXPOR_DOCS=false`, acompanhamento do CI/CD |
| **Maurício** | Dados e campo: pontos de controle e medição de GPS, análise da medição, mapeamento (primeiro trecho e M2), diário de campo, e CEP (prazo, protocolo, termo, submissão) |
| **Equipe** | E1 a E5, banner, correção do texto do TCC I, Projeto Parcial |
| **Orientadora** | Decidir as pendências 1 a 8 |

A divisão de **trabalho** em três pessoas não coincide com a lista de **autores** (dois no TCC I): conferir com a equipe e a orientadora (cartão de 23/10). A divisão acima ainda não foi aprovada pela equipe (critério "pronto quando" do E5). Divisão de responsabilidades com a orientadora: **[DECIDIR COM A ORIENTADORA]** apenas no que ela precisar ratificar.

## 4 Caminho crítico e riscos

1. **CEP (maior risco).** Teste com pessoas com deficiência visual envolve população vulnerável. A submissão pela Plataforma Brasil é provável e a aprovação leva de 2 a 4 meses (informação do CLAUDE.md; o prazo real deve ser levantado em 21/10). Submetendo em 20/11, a aprovação cairia entre 20/01 e 20/03/2027, antes da avaliação de abril, mas com pouca folga no pior caso. **Mitigação:** submeter em novembro, antes de qualquer recrutamento; **plano B:** avaliação com especialistas em orientação e mobilidade (vale menos que a de usuários, mas salva a entrega). Se a submissão atrasar, o plano B entra no mesmo mês de abril. Decisão sobre a submissão: **[DECIDIR COM A ORIENTADORA]** (pendência #8).
2. **Coleta e campo apertados.** Três atividades de campo concorrem em outubro: a medição de GPS (22/10), o primeiro trecho (23/10) e o diário. O protótipo do banner (29/10) depende do trecho mapeado, da AWS no ar e da migration 004. **Mitigação:** protótipo mínimo (um trecho, um destino, uma orientação); repetir medições só depois da análise. Qualquer atraso do mapeamento empurra o E6.
3. **Infraestrutura para HTTPS.** A localização e a bússola exigem HTTPS; a AWS é o caminho (conta do Rodrigo) e o túnel local é o plano B se a AWS não estiver pronta em 22/10.
4. **Dependência de decisões da orientadora** (pendências 1 a 8, reunião de ~27/10): recorte do mapeamento (M2), precisão mínima (M4), plataforma (M5). **Mitigação:** valores provisórios configuráveis.
5. **Concentração do código em uma pessoa.** M3, M4 e M5 somam 70 horas estimadas no Kanban (16 + 30 + 24), todas com o Rodrigo, no período de férias e retorno. Redistribuir é decisão da equipe.
6. **Teste interno com vendas** só vale como desenvolvimento e deve ser registrado como **simulação**, nunca como teste com usuário.
7. **Contribuição científica indefinida** (pendência #7): sem fechá-la, o TCC II corre o risco de ser lido como integração de bibliotecas existentes.

## 5 Para a equipe decidir ao revisar

- Conferir os prazos do Kanban contra o cronograma (passo 4 do cartão).
- Confirmar com a universidade a data do banner (~03/11) e a do Projeto Parcial.
- Aprovar a divisão de responsabilidades.
