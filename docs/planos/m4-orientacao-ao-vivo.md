# Plano do M4: orientação ao vivo pelo GPS

> Plano de 03/11/2026. Implementados: `posicao` (branch `m4/posicao`) e, em `m4/rumo-mensagens`, `rumo`, `mensagens` e `POST /orientacoes` (ver §7). O resto é desenho. Todo limiar abaixo é **PROVISÓRIO**. Requisitos: RF08, RF09, RF12, RNF03, RNF04, RNF05 (`docs/texto-tcc/rascunhos/e2-requisitos.md`).

## 1. Regras que não mudam

- **A posição de quem navega nunca é gravada** (RNF04): sem tabela, sem log com lat/lon, sem arquivo. O servidor usa e descarta. Os módulos são funções puras, sem banco.
- **Silêncio é melhor que palpite** (RNF05): precisão ruim, rota inválida ou dúvida resultam em "não sei onde você está", nunca em direção.
- Armazenamento em 4326, distância em metros. Hoje a rota vira plano local em metros (mesma aproximação de `rotas/instrucoes.py`, sem pyproj); vale para centenas de metros.
- Parâmetros no `.env`; nenhum número solto no código.

## 2. Módulos (`backend/app/orientacao/`)

| Módulo | Faz | Estado |
|---|---|---|
| `posicao.py` | `projetar_na_rota` (map matching por trecho: ponto projetado, desvio, distância percorrida/restante, índice do trecho) e `avaliar_posicao` (estado e confiança) | **feito** (RF08, RF12) |
| `rumo.py` | Rumo do usuário e a posição relativa do alvo (frente, direita, esquerda, atrás); giro 0°/360°; parado = sem seta. Espelha `frontend/src/mapa/rumo.ts` | **feito** (RF09), rumo híbrido, movimento andando e bússola parado (decisão de 03/11/2026, a validar com a orientadora); faixas angulares provisórias **[DECIDIR com a orientadora]** |
| `mensagens.py` | Estado + confiança + rumo viram frase curta em português, no mesmo estilo de `rotas/instrucoes.py`; "não sei onde você está" quando silêncio | **feito** (RF12) |

## 3. API (ainda NÃO criada)

`POST /orientacoes` (sem token, como `/rotas`; corpo limitado em bytes, como `POST /alertas`).

```json
{
  "rota": { "geometria": [[-46.6514681, -23.5474426], [-46.6520217, -23.5460134]] },
  "posicao": { "lat": -23.5470, "lon": -46.6517, "precisao_m": 8.0,
               "trilha": [ { "lat": ..., "lon": ..., "precisao_m": 6.0, "ha_segundos": 12.0 } ] }
}
```

- `rota`: a geometria `[lon, lat]` devolvida por `POST /rotas` (o cliente a guarda e reenvia, então o servidor não precisa de sessão nem de banco). Alternativa: ids de arestas; adiar até haver necessidade. Limite de vértices no schema.
- `posicao`: lat, lon, precisão e, opcionais, `rumo_bussola_graus`/`rumo_bussola_oscilacao_graus` (só valem parado). `trilha` (opcional, até 10 posições anteriores com `ha_segundos`) não é gravada e só serve ao rumo pelo movimento; `rumo_graus`, `rumo_oscilacao_graus` e `velocidade_ms` foram removidos. A resposta traz `fonte_rumo` ("movimento", "bussola" ou null).
- Pydantic estrito (`StrictFloat`, `extra="forbid"`), erros 422 em português, unidades no nome.

Resposta:

```json
{ "estado": "na_rota", "mensagem": "Siga em frente por 70 metros.", "confianca": "alta",
  "distancia_restante_m": 70, "distancia_ate_proxima_instrucao_m": 35 }
```

Estados: `na_rota`, `fora_da_rota`, `precisao_insuficiente`, `chegou` (já em `posicao.py`) e `parado` (derivado da trilha em `rumo.py`: sem deslocamento suficiente, porque não é propriedade da projeção). Sem projeção quando `precisao_insuficiente`: a resposta traz só a mensagem de silêncio. O log da API não pode registrar o corpo desta rota (RNF04; revisar o log de acesso do uvicorn/nginx). RNF03: a função é barata (O(vértices)); valor-alvo de tempo ainda sem número.

## 4. Regras do `posicao.py` (provisórias)

1. `precisao_m` ausente, não finita, <= 0 ou > `PRECISAO_MINIMA_METROS`: `precisao_insuficiente`, confiança baixa, **sem projeção**.
2. Desvio da rota > `DISTANCIA_FORA_DA_ROTA_METROS` + `precisao_m`: `fora_da_rota` (a margem cresce com a imprecisão, para ruído não acusar saída).
3. Distância restante **pela rota** <= `RAIO_CHEGADA_METROS`: `chegou` (fora da rota vem antes: perto do fim em linha reta, mas do outro lado de um muro, não é chegada).
4. Senão `na_rota`.

Confiança: **baixa** se fora da rota ou desvio > `DISTANCIA_FORA_DA_ROTA_METROS`; **alta** se `precisao_m` <= metade do mínimo **e** desvio <= `precisao_m`; **média** no resto. O segundo critério da "alta" existe porque a precisão do celular não é confiável (ver §6).

| Variável `.env` | Provisório | Observação |
|---|---|---|
| `PRECISAO_MINIMA_METROS` | 15 | Valor do pedido do M4; final é pendência #1 |
| `DISTANCIA_FORA_DA_ROTA_METROS` | 15 | Sem dado que o sustente ainda; é chute para calibrar |
| `RAIO_CHEGADA_METROS` | 10 | P02 (referência sem viés) ficou a 3 a 6 m; entradas próximas (P05/P06) pedem confirmação por referência física |

## 5. Fica para depois

- **Rumo híbrido (decisão de 03/11/2026, a validar com a orientadora):** andando, pelo movimento (azimute do ponto mais antigo da trilha, janela `JANELA_TRILHA_SEGUNDOS=15`, a pelo menos `DESLOCAMENTO_MINIMO_RUMO_METROS=8` da posição atual; escolhido em vez da média antigas-vs-recentes: maior base, menos erro angular, mais simples); parado (trilha sem deslocamento suficiente), pela bússola do celular, com `RUMO_OSCILACAO_MAXIMA_GRAUS=30` (instável ou ausente = silêncio). Andando a bússola é ignorada. Trilha vazia = silêncio (não vira bússola); deslocamento menor que a soma das precisões = silêncio. Parâmetros provisórios.
- **Referências não visuais** ("cheguei na rampa", método 3): confirmação do usuário em vez de posição, onde o erro é do tamanho da distância entre marcos.
- Filtro/suavização e histerese (método 2): evitar anunciar e desanunciar a chegada.
- Rota que volta sobre si mesma: a projeção por menor distância pode pular de trecho; exigir continuidade com a posição anterior (que o cliente teria de enviar, sem o servidor guardar).
- Reprojeção em 31983 de verdade, se a rota passar de poucos quilômetros.
- Endpoint, schema, `docs/api.md` e E2E.

## 6. Como calibrar com a medição de GPS

Fonte: `vw_erro_medicoes` e o diário (`docs/diario-de-campo.md`). Cuidados já conhecidos:

- **P01, P03 e P08 têm referência deslocada** (estimada por imagem de satélite; P01 a 15 a 19 m, sempre na mesma direção, P03 a 16,6 m). O `erro_m` desses pontos mistura erro do GPS com erro da referência: **não** usá-los para fixar `RAIO_CHEGADA_METROS` ou `DISTANCIA_FORA_DA_ROTA_METROS` até a referência ser conferida no local (decisão #9). Usar P02 e os pontos sem viés aparente.
- **A precisão informada não serve como confiança.** No P01 dizia 3 m e o erro foi 19 m; no P02 dizia 14 m e o erro foi 3 m; o iPhone 17 Pro aparece **fixo em 14,25 m**. Por isso o plano usa `precisao_m` só como gatilho de silêncio (teto) e como margem do `fora_da_rota`, e exige que o desvio em relação à rota concorde com ela para dar confiança alta.
- Passos: (1) tabela de erro por condição (céu aberto, entre prédios, entrada) sem os pontos deslocados; (2) fixar o raio de chegada acima do erro típico da pior condição do ponto de chegada; (3) com o trajeto andando do iPhone (175 posições em 26/10), reprojetar sobre a rota provisória 4 para 6 e contar falsos `fora_da_rota` e falsos `precisao_insuficiente`; (4) o `DISTANCIA_FORA_DA_ROTA_METROS` sai da dispersão da posição andando contra a largura real das calçadas; (5) decisão final com a orientadora.
- O trajeto real e a rota 4 para 6 ficam na produção; o banco de dev não os tem. Os testes atuais usam trajeto **sintético** (rotulado como tal); o teste com o trajeto real fica para quando o dado for exportado localmente, sem acessar a produção a partir do código.

## 7. O que ficou pronto (03/11/2026, branch `m4/rumo-mensagens`)

- `orientacao/rumo.py`: rumo híbrido (0 a 360: movimento pela trilha se andando, bússola se parado), ponto da rota
  `ALVO_A_FRENTE_METROS` adiante, diferença normalizada em (-180, 180], setores (frente
  +-30, lados 30 a 150, atrás > 150). Silêncio (`None`) se sem rumo (trilha vazia, GPS ruidoso, parado com bússola ausente ou instável).
- `orientacao/mensagens.py`: uma mensagem ou nenhuma (perigo > fora da rota/sem posição >
  curva > chegada > "Siga em frente."), anti-repetição por `chave` com o histórico enviado
  pelo cliente.
- `POST /orientacoes` (`routers/orientacoes.py`, `schemas/orientacao.py`): **mudou o
  desenho do §3**: em vez de o cliente enviar a geometria, envia `origem_id`, `destino_id`,
  `perfil`, `posicao` e `recentes`, e o servidor recalcula a rota com `_montar_rota` (uma
  lógica só, sem duplicar), ao custo de uma consulta ao banco por chamada. Contrato e nota de
  privacidade em `docs/api.md`.
- Decisões desta etapa: perigo só vale com `na_rota` (fora da rota o progresso não é
  confiável); escada e travessia vêm dos `trechos` da rota (soma de `comprimento_m`, a mesma
  medida das instruções); mensagem suprimida pela anti-repetição não cede lugar a outra de
  menor prioridade (silêncio); as mensagens `direita`/`esquerda`/`atras` ainda não têm frase
  (só o campo `direcao`): **decididas em 03/11 (frases abaixo, §7b)**.
- Falta: teste com o trajeto real do iPhone, histerese, continuidade para rota que volta
  sobre si, frontend (M4 no app), validar o rumo híbrido com a orientadora.

## 7b. Rumo híbrido e frases de direção (03/11/2026, branch `m4/rumo-movimento`)

- `posicao.rumo_bussola_graus` e `rumo_bussola_oscilacao_graus` (opcionais, só parado); `trilha` até 10 pontos; resposta com `fonte_rumo`.
- Frases (chave por setor, intervalo normal de repetição): "O caminho está à sua frente." (`direcao_frente`, baixa, a confirmação), "...à sua direita." / "...à sua esquerda." / "O caminho está atrás de você." (`direcao_*`, media), abaixo de perigo, fora da rota e curva iminente.
- Ângulos e distâncias seguem provisórios (sem resposta da orientadora).

## 7c. Tela "Orientação ao vivo" no app (03/11/2026, branch `m4/tela-ao-vivo`)

- Botão "Iniciar orientação ao vivo" aparece depois da rota traçada (não na simulação). O toque pede GPS (`watchPosition`, alta precisão, `maximumAge: 0`), permissão e leitura da bússola (iPhone: `webkitCompassHeading`; Android: `alpha` só do evento absoluto; relativo é descartado) e Wake Lock.
- A cada ~2,5 s (uma requisição em voo no máximo) vai `POST /api/orientacoes` com `posicao`, `trilha` (<= 10 pontos, janela de 15 s, amostra ~1,5 s) e `recentes` (<= 20). Campo ausente é omitido. Posição com mais de 10 s não é enviada (o GPS sumiu): fica "Sem GPS confiável" no app, sem fala.
- Código: lógica pura em `frontend/src/orientacao/` (`trilha.ts`, `requisicao.ts`, `apresentacao.ts`); DOM em `frontend/src/inicio/orientacao-tela.ts`.
- **Privacidade:** posição, trilha e recentes só na memória; `encerrarRecursos()` apaga tudo ao parar ou sair da página; `orientacao-html.test.ts` varre os módulos atrás de `localStorage`, `sessionStorage`, IndexedDB, cookie, `console`, beacon etc. e confere que o único `fetch` é o de `/api/orientacoes`.
- **Silêncio:** o app só mostra e fala o `mensagem.texto` da API; o campo `direcao` não é lido; resposta torta vira "orientação pausada".
- **Decisão do app (a confirmar):** o mapa só acompanha a pessoa dentro do campus (`dentroDoCampus`), porque os blocos de mapa pedidos ao OpenStreetMap revelam a região mostrada; fora do campus não há marcador nem o mapa se move.
- Voz: com "Voz do site" ligada a mensagem é falada E vai para a região aria-live (pedido do Rodrigo); pode haver fala dupla com leitor de tela ligado. Testar em aparelho.

