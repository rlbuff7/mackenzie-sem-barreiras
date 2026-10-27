# Diário de campo

Registro cronológico das coletas reais de GPS nos pontos de controle (ver
[`medicao-gps.md`](medicao-gps.md)). Os dados daqui são **REAIS de campo, não
sintéticos**. Uma seção por data.

## 26/10/2026: Maurício, iPhone 17 Pro

**Status: parcial. A coleta está em andamento; os números valem até 20:15 (BRT).**

### Contexto

- 10 pontos de controle, P01 a P10, com 3 medições de 30 s por ponto.
- O trajeto é ligado entre os pontos: 175 posições até 20:15, com precisão
  informada pelo celular entre 6 e 14 m.
- A primeira tentativa, às 20:00, foi recusada: o código da equipe foi digitado
  errado (provável maiúscula automática do teclado do iPhone). Depois da
  correção, a fila reenviou sozinha e nada se perdeu.
- Nenhuma foto do iPhone chegou até 20:15.

### Medições até 20:15

`dist_m` é a distância até a coordenada de referência, calculada em SRID 31983.
`rumo` é o azimute da referência para a medição, em graus. `prec` é a precisão
informada pelo celular, em metros.

| Ponto | id | Hora (BRT) | dist_m | rumo (°) | prec (m) |
|---|---|---|---|---|---|
| P01 | 54 | 20:00:15 | 18,7 | 107 | 14 |
| P01 | 55 | 20:03:57 | 18,9 | 115 | 3 |
| P01 | 56 | 20:06:21 | 14,6 | 106 | 7 |
| P01 | 57 | 20:08:16 | 14,8 | 105 | 7 |
| P02 | 139 | 20:12:58 | 3,5 | 177 | 14 |
| P02 | 165 | 20:13:50 | 2,8 | 133 | 14 |
| P02 | 187 | 20:14:27 | 6,0 | 177 | 14 |
| P03 | | | 16,6 | 52 | |

P03 tinha só 1 medição até então.

### Resumo por ponto

| Ponto | Medições | Centroide a (m) | Rumo do centroide | Espalhamento máximo em torno do centroide |
|---|---|---|---|---|
| P01 | 4 | 16,7 | 108° (lés-sudeste) | 2,9 m |
| P02 | 3 | 3,9 | n/d | 2,3 m |

### Observação: P01 com desvio sistemático

O P01 é céu aberto ("Praça de convivência próxima ao Prédio 18", em frente ao
Auditório Ruy Barbosa), onde se esperaria erro pequeno. O erro foi de 15 a 19 m.

**Interpretação.** As 4 medições, ao longo de 8 minutos, ficaram a menos de 3 m
umas das outras e todas na mesma direção (105° a 115°). Ruído de GPS espalharia
as medições em direções diferentes. Um deslocamento constante na mesma direção
indica viés sistemático, não ruído.

**Hipóteses, da mais para a menos provável:**

1. A coordenada de referência do P01 está deslocada. Ela é estimativa por imagem
   de satélite, não topografia (campo `origem_referencia` em `pontos_controle`;
   seed `db/seeds/003_pontos_controle.sql`).
2. Quem mediu ficou num ponto físico diferente do marcador ◆. Num print do
   celular, o ponto azul aparecia à direita do ◆, e a descrição do P01 não
   identifica um lugar físico exato.
3. Multicaminho por reflexão nos prédios vizinhos. É a menos provável, porque
   causaria variação maior entre as medições.

**Achado secundário.** A precisão informada pelo celular não acompanhou o erro
real. No P01 ela dizia 3 m e o erro foi de 19 m. No P02 dizia 14 m e o erro foi
de 3 m. A precisão informada não deve ser tratada como erro real; isso é
argumento para a análise do TCC.

**Encaminhamento.** Conferir no local qual é o ponto físico do P01 (marco
identificável: banco, poste, tampa) e comparar com a coordenada. **Não alterar a
coordenada no seed antes de decidir:** mudar a referência recalcula o `erro_m` de
todas as medições (`vw_erro_medicoes`). Se houver correção, ela vai em
migration/seed novo, com o motivo registrado. Pendência registrada em
[`decisoes-pendentes.md`](decisoes-pendentes.md) (#9).

### Backup

Backup da produção feito em 26/10/2026 às 23:18 UTC
(`prod-mackenzie_sem_barreiras-20261026-231803.dump`), com cópia local fora do Git.
