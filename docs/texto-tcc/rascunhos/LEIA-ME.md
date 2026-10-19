# Rascunhos para a equipe revisar (19/10/2026)

> **RASCUNHO para revisão da equipe — gerado em 19/10/2026; nada aqui foi aprovado pela orientadora.**

Quatro textos em português acadêmico para as entregas do Kanban "Navegação Acessível no Campus". Fonte: `CLAUDE.md` do escopo novo (14/10/2026), os cartões E1, E2, E4 e E5 e o código da branch. Nada foi inventado: citação bibliográfica nova está como **[REF?]**; dado do IBGE como **[CONFERIR IBGE]**; decisão da orientadora como **[DECIDIR COM A ORIENTADORA]**.

| Arquivo | Cartão (prazo) | O que cobre |
|---|---|---|
| [`e1-escopo.md`](e1-escopo.md) | E1 (20/10) | Problema, público-alvo (cegos e baixa visão; complementar), objetivos geral e específicos, princípio de segurança, recorte (só caminhos externos até a entrada dos prédios) e o que fica fora. |
| [`e2-requisitos.md`](e2-requisitos.md) | E2 (22/10) | RF01–RF12 e RNF01–RNF10 em tabela, cada um com componente real (arquivo ou rota existente) ou previsto (M3–M5) e critério de verificação; matriz de rastreabilidade. |
| [`e4-plano-mapeamento.md`](e4-plano-mapeamento.md) | E4 (20/10) | O que mapear (tipos reais da migration 004), como (OSM + caminhada), ordem (trecho do banner até 29/10, M2 até 11/12), responsáveis e entrada no banco (`pontos_interesse`, `nos`, `arestas`). |
| [`e5-cronograma-responsaveis.md`](e5-cronograma-responsaveis.md) | E5 (20/10) | Tabela A S O N D J F M A M, marcos com datas do Kanban, divisão Rodrigo / Victor / Maurício, riscos (CEP, campo apertado). |

## Marcações abertas

**[DECIDIR COM A ORIENTADORA]**

- Contribuição científica (pendência #7): E1, E5.
- Recorte do mapeamento no TCC I (#4): E1, E4.
- Precisão mínima para orientar (#1), plataforma web ou nativo (#2), offline (#3): E1, E2.
- Calibração de penalidades e setores angulares (#5): E2.
- Como classificar caminhos acessíveis por perfil e quem valida (#6): E2, E4.
- Submissão ao CEP (#8): E5.

**[CONFERIR IBGE]**: número de pessoas com deficiência visual (14,4 × 18,6 milhões; ver `docs/decisoes-pendentes.md`): E1.

**[REF?]**: literatura de navegação assistiva e orientação espacial (E1); WCAG 2.2 (E2); OpenStreetMap e ferramenta de digitalização (E4).

## Pendências técnicas e de equipe que os rascunhos expõem (sem marcação)

- Os enunciados RF/RNF são proposta: só a quantidade e três RNF de acessibilidade vêm do CLAUDE.md (E2).
- Meta numérica de desempenho de `/orientacoes` não existe em nenhum documento (E2).
- A migration 004 não tem colunas de autoria do mapeamento nem de "trecho verificado" (E4).
- Lista de autores (dois no TCC I; três pessoas na divisão) e prazos "~" a confirmar com a universidade (E1, E5).
- Os arquivos `docs/requisitos.md`, `docs/mapeamento-campus.md` e `docs/arquitetura.md` ainda não existem: estes rascunhos são a matéria-prima, mas não os substituem.
