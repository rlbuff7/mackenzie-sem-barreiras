# Plano do M4: orientação ao vivo pelo GPS

> Plano de 03/11/2026. Só o módulo `posicao` está implementado (branch `m4/posicao`). O resto é desenho. Todo limiar abaixo é **PROVISÓRIO**. Requisitos: RF08, RF09, RF12, RNF03, RNF04, RNF05 (`docs/texto-tcc/rascunhos/e2-requisitos.md`).

## 1. Regras que não mudam

- **A posição de quem navega nunca é gravada** (RNF04): sem tabela, sem log com lat/lon, sem arquivo. O servidor usa e descarta. Os módulos são funções puras, sem banco.
- **Silêncio é melhor que palpite** (RNF05): precisão ruim, rota inválida ou dúvida resultam em "não sei onde você está", nunca em direção.
- Armazenamento em 4326, distância em metros. Hoje a rota vira plano local em metros (mesma aproximação de `rotas/instrucoes.py`, sem pyproj); vale para centenas de metros.
- Parâmetros no `.env`; nenhum número solto no código.

## 2. Módulos (`backend/app/orientacao/`)

| Módulo | Faz | Estado |
|---|---|---|
| `posicao.py` | `projetar_na_rota` (map matching por trecho: ponto projetado, desvio, distância percorrida/restante, índice do trecho) e `avaliar_posicao` (estado e confiança) | **feito** (RF08, RF12) |
| `rumo.py` | Rumo do usuário e a posição relativa do alvo (frente, direita, esquerda, atrás); giro 0°/360°; parado = sem seta. Espelha `frontend/src/mapa/rumo.ts` | a fazer (RF09); faixas angulares **[DECIDIR com a orientadora]** |
| `mensagens.py` | Estado + confiança + rumo viram frase curta em português, no mesmo estilo de `rotas/instrucoes.py`; "não sei onde você está" quando silêncio | a fazer (RF12) |

## 3. API (ainda NÃO criada)

`POST /orientacoes` (sem token, como `/rotas`; corpo limitado em bytes, como `POST /alertas`).

```json
{
  "rota": { "geometria": [[-46.6514681, -23.5474426], [-46.6520217, -23.5460134]] },
  "posicao": { "lat": -23.5470, "lon": -46.6517, "precisao_m": 8.0,
               "rumo_graus": 312.0, "velocidade_ms": 1.1 }
}
```

- `rota`: a geometria `[lon, lat]` devolvida por `POST /rotas` (o cliente a guarda e reenvia, então o servidor não precisa de sessão nem de banco). Alternativa: ids de arestas; adiar até haver necessidade. Limite de vértices no schema.
- `posicao.rumo_graus` e `velocidade_ms` são opcionais (o celular nem sempre informa).
- Pydantic estrito (`StrictFloat`, `extra="forbid"`), erros 422 em português, unidades no nome.

Resposta:

```json
{ "estado": "na_rota", "mensagem": "Siga em frente por 70 metros.", "confianca": "alta",
  "distancia_restante_m": 70, "distancia_ate_proxima_instrucao_m": 35 }
```

Estados: `na_rota`, `fora_da_rota`, `precisao_insuficiente`, `chegou` (já em `posicao.py`) e `parado` (decidido em `rumo.py`/`mensagens.py` com `velocidade_ms`, porque não é propriedade da projeção). Sem projeção quando `precisao_insuficiente`: a resposta traz só a mensagem de silêncio. O log da API não pode registrar o corpo desta rota (RNF04; revisar o log de acesso do uvicorn/nginx). RNF03: a função é barata (O(vértices)); valor-alvo de tempo ainda sem número.

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

- **Rumo pela bússola** (`rumo_graus` do aparelho): a análise ainda não diz se a bússola é estável (pergunta P6 do plano de análise). Até lá `rumo.py` usa o rumo derivado do movimento, e só se a pessoa estiver andando.
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
