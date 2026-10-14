# CLAUDE.md — Navegação Acessível no Campus Mackenzie

Contexto permanente do projeto. Leia antes de qualquer tarefa neste repositório.

Última atualização: 14/10/2026

> **Mudança de escopo em 08/10/2026.** Este repositório começou como "Mackenzie sem
> Barreiras" (mapeamento colaborativo de barreiras urbanas via crowdsourcing). Em
> reunião com a orientadora, o projeto foi redirecionado para **navegação e orientação
> espacial acessível no campus**. A §15 lista o que foi aposentado e o que continua
> valendo. Código antigo que não está citado aqui como ativo não deve ser estendido —
> se precisar mexer nele, pergunte antes.

---

## 1. O que é este projeto

Software de **navegação e orientação espacial** para o campus da Universidade
Presbiteriana Mackenzie (Higienópolis, São Paulo/SP).

Público prioritário: **pessoas com deficiência visual** (cegas e com baixa visão).
Público complementar: estudantes, professores, funcionários e visitantes que não
conhecem o campus.

Duas formas de uso, complementares:

- **Visual** — mapa 2D do campus, seleção de destino, rota desenhada na tela.
- **Áudio** — orientações faladas durante o percurso, citando pontos de referência
  ("à sua direita há uma escada que dá acesso ao Prédio 31").

É um TCC de graduação (FCI/Mackenzie). TCC I entrega a base conceitual, os requisitos,
a arquitetura e um protótipo demonstrativo. TCC II entrega o software avaliado com
usuários.

Orientadora: Profa. Dra. Ana Graziela de Almeida Valiengo.
Consulta técnica de arquitetura: Prof. Jamilson.

### Escopo geográfico — DECIDIDO

**Apenas áreas externas do campus**: vias internas, praças, caminhos e acessos entre
prédios. **Não entra no interior dos prédios.**

Consequências que já valem como regra:

- Nada de beacons BLE, Wi-Fi fingerprinting ou QR code indoor. O projeto volta a ser
  custo zero (§14).
- Destino de uma rota é sempre a **entrada** de um prédio, nunca uma sala. Cada prédio
  precisa de um ou mais nós de entrada no grafo, com indicação de qual é acessível.
- Navegação termina ao chegar na entrada, com mensagem explícita de chegada.

### Contribuição técnica central

Roteamento e síntese de voz são problemas resolvidos; integrá-los não é contribuição.
O que diferencia este trabalho é o **módulo de orientação espacial**: decidir *o que*
falar, *quando* falar e *como* se comportar quando a localização está imprecisa.
Código em `backend/app/orientacao/` é o núcleo do trabalho — funções pequenas, nomes
explícitos, testes, docstrings explicando a decisão.

### Princípio de segurança (não negociável)

O sistema é **apoio à orientação**, nunca substituto de bengala, cão-guia ou das
técnicas de mobilidade do usuário. Uma orientação errada para uma pessoa cega tem
consequência física. Disso decorrem duas regras de código:

- **Silêncio é melhor que palpite.** Sem precisão suficiente, o sistema diz que não
  sabe — nunca arrisca uma direção.
- **Nenhuma orientação que empurre o usuário para a via, para uma escada não anunciada
  ou para um trecho não mapeado.**

Essa frase precisa aparecer também na interface e no texto do TCC, não só aqui.

---

## 2. Stack

| Camada | Tecnologia | Observação |
|---|---|---|
| Frontend | TypeScript + Leaflet | Mapa 2D; tiles OpenStreetMap |
| Áudio | Web Speech API (`SpeechSynthesis`) | Nativa do navegador, sem chave nem custo |
| Háptico | Vibration API | **Não funciona no iOS** — ver §13.2 |
| Backend | Python 3.11+ / FastAPI | Pydantic v2 para schemas |
| Banco | PostgreSQL 16 + PostGIS 3.4 | rodando via Docker |
| Roteamento | pgRouting | **autorizado neste escopo** (ver §6) |
| Infra local | Docker Compose | nada instalado direto na máquina |

**Não troque de stack sem autorização explícita.** Se algo parecer melhor resolvido com
outra ferramenta, sugira em texto e espere confirmação — não implemente.

Nota: pgRouting era proibido no escopo anterior. Com roteamento no centro do projeto,
passou a ser o caminho padrão.

---

## 3. Estrutura de pastas

```
campus-acessivel/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── CLAUDE.md
├── db/
│   ├── migrations/          # SQL numerado, aplicado em ordem (imutável)
│   └── seeds/               # pontos de interesse e grafo do campus
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py        # lê .env, nada hardcoded
│   │   ├── db.py            # pool de conexão
│   │   ├── schemas/         # modelos Pydantic
│   │   ├── routers/         # endpoints HTTP
│   │   ├── rotas/           # cálculo de caminho (pgRouting)
│   │   └── orientacao/      # NÚCLEO DO TCC
│   │       ├── posicao.py       # projeção na aresta, confiança da posição
│   │       ├── rumo.py          # bearing, esquerda/direita/frente
│   │       ├── referencias.py   # quais POIs citar
│   │       └── mensagens.py     # texto falado + política de disparo
│   ├── scripts/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
└── docs/
    ├── requisitos.md           # RF01–RF12, RNF01–RNF10
    ├── arquitetura.md
    ├── mapeamento-campus.md
    ├── medicao-gps.md          # resultado do teste de campo (§11)
    ├── protocolo-avaliacao.md  # teste com usuários (§12)
    ├── decisoes-pendentes.md
    └── academico/
```

---

## 4. Modelo de dados

Tudo em **SRID 4326** para armazenar; cálculo métrico em **31983** (ver §5).

**`pontos_interesse`** — prédios, entradas, escadas, rampas, quadras, portões,
qualquer coisa citável numa orientação.
```sql
id            BIGSERIAL PRIMARY KEY
geom          GEOMETRY(Point, 4326) NOT NULL
tipo          VARCHAR(32) NOT NULL      -- predio, entrada, escada, rampa, quadra, portao
nome          VARCHAR(120) NOT NULL     -- "Prédio 31"
descricao     TEXT                      -- texto para leitura em voz
acessivel     BOOLEAN                   -- NULL = não verificado
```

**`nos`** — vértices do grafo pedonal (cruzamentos, bifurcações, entradas de prédio).
```sql
id            BIGSERIAL PRIMARY KEY
geom          GEOMETRY(Point, 4326) NOT NULL
ponto_interesse_id BIGINT REFERENCES pontos_interesse(id)  -- quando o nó É uma entrada
```

**`arestas`** — trechos caminháveis entre dois nós. É o grafo que o pgRouting consome.
```sql
id            BIGSERIAL PRIMARY KEY
geom          GEOMETRY(LineString, 4326) NOT NULL
origem_id     BIGINT NOT NULL REFERENCES nos(id)
destino_id    BIGINT NOT NULL REFERENCES nos(id)
comprimento_m DOUBLE PRECISION NOT NULL   -- calculado em 31983
tipo          VARCHAR(32) NOT NULL        -- calcada, rampa, escada, travessia
acessivel_cadeirante BOOLEAN
custo         DOUBLE PRECISION NOT NULL   -- comprimento + penalidades (ver §6)
custo_inverso DOUBLE PRECISION NOT NULL   -- -1 quando o trecho é de mão única
```

### Índices obrigatórios

```sql
CREATE INDEX idx_poi_geom        ON pontos_interesse USING GIST (geom);
CREATE INDEX idx_nos_geom        ON nos              USING GIST (geom);
CREATE INDEX idx_arestas_geom    ON arestas          USING GIST (geom);
CREATE INDEX idx_arestas_origem  ON arestas (origem_id);
CREATE INDEX idx_arestas_destino ON arestas (destino_id);
```

Nomenclatura para o texto do TCC: o PostGIS indexa via **GiST**. Citar R-Tree como
conceito é aceitável no referencial; o código e a defesa dizem GiST.

---

## 5. Armadilha do SRID — leia antes de escrever qualquer query espacial

O banco armazena em **SRID 4326 (WGS84)**, cuja unidade é **grau**, não metro.
Neste projeto isso importa mais do que no anterior, porque praticamente toda consulta
mede distância ou ângulo.

- **Armazenar** em 4326 (é o que o GPS e o Leaflet usam).
- **Calcular distância, comprimento de aresta e custo**: `ST_Transform(geom, 31983)`
  (SIRGAS 2000 / UTM 23S, cobre São Paulo, unidade = metro).
- `ST_DWithin` sobre `geometry` em 4326 compara **graus**. Para "POIs a até 20 m",
  use `geography` ou reprojete.
- `ST_Azimuth` devolve **radianos**, no sentido horário a partir do norte. Converta
  com `degrees()` antes de qualquer comparação.

Toda variável que carrega distância ou ângulo deixa a unidade explícita no nome
(`distancia_m`, `rumo_graus`) ou em comentário.

---

## 6. Roteamento

`pgr_dijkstra` sobre `arestas`, usando `custo` / `custo_inverso`.

**Custo não é só comprimento.** Um caminho mais curto por escada é pior que um desvio
por rampa. O custo de cada aresta é o comprimento em metros multiplicado por um fator
de penalidade do tipo, configurável no `.env`:

```
PENALIDADE_ESCADA=4.0
PENALIDADE_TRAVESSIA=2.0
PENALIDADE_TRECHO_NAO_VERIFICADO=1.5
```

Valores **provisórios**, a calibrar com a orientadora e com os testes. Por isso não
podem estar espalhados pelo código.

Perfis de usuário (cadeirante, deficiência visual, sem restrição) mudam as penalidades,
não o grafo. Um perfil que não pode usar escada recebe custo proibitivo, não exclusão
da aresta — assim a rota nunca fica sem solução silenciosamente.

---

## 7. Módulo de orientação espacial (`app/orientacao/`)

É onde está a contribuição do trabalho. Quatro responsabilidades separadas:

**`posicao.py`** — recebe lat/lon + precisão informada pelo navegador
(`GeolocationPosition.coords.accuracy`, em metros) e projeta o ponto na aresta mais
próxima da rota (*map matching*). Devolve também um **nível de confiança**. Se a
precisão for pior que `PRECISAO_MINIMA_METROS`, a posição é marcada como não confiável
e o sistema não emite orientação direcional.

O map matching é o que salva o projeto da imprecisão do GPS: como o campus tem poucos
caminhos possíveis, um erro de 15 m ainda permite afirmar "ele está no caminho entre o
31 e o 32" com boa confiança.

**`rumo.py`** — calcula o azimute do usuário (do histórico de posições ou da bússola) e
o azimute até o alvo; a diferença define frente / direita / esquerda / atrás. Faixas em
`.env` (`SETOR_FRENTE_GRAUS` etc.). Cuidado com o wrap em 0°/360°: a diferença é
`((a - b + 540) % 360) - 180`.

**`referencias.py`** — escolhe quais POIs citar: dentro de um raio, à frente do usuário,
no máximo N por mensagem. Citar tudo é tão ruim quanto não citar nada.

**`mensagens.py`** — monta o texto falado e decide **quando** falar. Regras: não repetir
a mesma mensagem antes de `INTERVALO_MINIMO_SEGUNDOS`; priorizar aviso de mudança de
direção sobre descrição de ambiente; frase curta, sem jargão, sem ler coordenada.

Anúncio de ponto de referência usa **raio generoso** (`RAIO_ANCORA_METROS`, provisório
15 m): "você está se aproximando do Prédio 31" continua verdadeiro mesmo com erro de
GPS, enquanto "a porta está a 3 metros à sua direita" não.

Toda função aqui tem teste. Casos de borda obrigatórios: precisão ruim, usuário parado
(rumo indefinido), usuário fora da rota, fim do percurso.

---

## 8. Padrão háptico

A vibração complementa o áudio porque som ambiente é a principal fonte de informação de
quem não enxerga — e o app compete com ela. Padrão proposto:

| Evento | Vibração |
|---|---|
| Ponto de referência próximo | 1 pulso curto |
| Mudança de direção | 2 pulsos curtos |
| Chegada ao destino | 1 pulso longo |
| Fora da rota | 3 pulsos |

Limitação a declarar no texto: `navigator.vibrate()` não é suportada no Safari/iOS.
Enquanto a plataforma não for decidida (§13.2), a vibração é **complemento opcional** —
nenhuma informação existe só no canal háptico.

---

## 9. Contrato da API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/pontos-interesse?bbox=minLon,minLat,maxLon,maxLat` | POIs na área visível do mapa |
| `GET` | `/pontos-interesse/{id}` | Detalhe de um POI, com a descrição falada |
| `POST` | `/rotas` | Calcula rota: origem (lat/lon ou nó), destino (POI), perfil |
| `POST` | `/orientacoes` | Dada posição + precisão + rumo + rota, devolve a próxima orientação |

`bbox` é obrigatório em `/pontos-interesse`: o mapa nunca pede o banco inteiro — é a
consulta por bounding box que justifica o índice espacial.

`/orientacoes` é chamada repetidamente durante a navegação, então precisa ser barata.
Se virar gargalo, o caminho é cache no cliente, não query mais esperta.

---

## 10. Acessibilidade (RNF01, RNF02, RNF07)

Não é camada de acabamento; entra desde o primeiro componente.

- HTML semântico, foco visível, ordem de tabulação coerente.
- Todo controle alcançável por teclado e rotulado para leitor de tela.
- Alvos de toque grandes (mínimo ~44 px).
- Contraste mínimo WCAG AA; nunca cor como única forma de transmitir informação.
- O mapa não pode ser a única forma de completar uma tarefa: toda ação do mapa tem
  equivalente em lista ou busca textual.
- Testar com VoiceOver (iOS) e TalkBack (Android) de verdade, não só no emulador.

---

## 11. Medição de GPS no campus (fazer antes da arquitetura fechar)

Substitui chute por número medido. Alimenta a entrega E3 e a conversa com o Prof.
Jamilson. Resultado vai em `docs/medicao-gps.md`.

**Pontos de controle (8 a 12):** praça aberta, caminho estreito entre prédios altos,
entrada de 2–3 prédios, uma bifurcação, uma passagem coberta. Coordenada "verdadeira"
tirada de imagem de satélite com zoom máximo.

**Procedimento por ponto:** parar em cima, esperar 20–30 s, registrar lat, lon,
`accuracy`, horário, nº do ponto e modelo do aparelho. Três medições por ponto. Anotar
a condição (céu aberto, entre prédios, coberto). Levar dois aparelhos, de preferência um
Android e um iPhone — a diferença entre eles já é resultado.

**Trajeto em movimento:** caminhar uma rota típica gravando posição a cada 1–2 s. É o
que mostra se o map matching resolve o serrilhado.

**Aproveitar a ida para testar:** `DeviceOrientationEvent` nos dois aparelhos (o iOS
pede permissão por gesto e exige HTTPS; o valor é estável ou fica pulando?) e
`navigator.vibrate()` (confirmar que funciona no Android e falha no iOS).

**Analisar:** erro real em metros (reprojetando para 31983); comparar com o `accuracy`
reportado — **se o navegador reporta 10 m e o erro real é 25 m, esse campo não serve
como critério de segurança, e isso é achado forte para o texto**; erro mediano e
percentil 90 por tipo de zona; quantos pontos passam de 15 m.

Duas pessoas, ~2 horas. Repetir um ou dois pontos em horário diferente.

---

## 12. Avaliação com usuários

### 12.1 Teste com vendas (sugestão da orientadora)

**Vale como teste interno de desenvolvimento, não como avaliação.** Serve para calibrar
timing do áudio, conferir se "à sua direita" bate com a realidade, medir se a frase é
longa demais para quem está andando, verificar se o sistema cala a boca quando o GPS
piora e se a vibração é perceptível com o celular no bolso.

**Não vale como resultado de usabilidade.** Pessoa vendada não é pessoa cega: falta
ecolocalização, memória espacial treinada e técnica de bengala, e sobra ansiedade. Pior:
quem é cego costuma achar áudio excessivo, porque ele compete com a escuta do ambiente —
efeito que ninguém vendado sente, já que o áudio é a única informação que tem. Some-se o
viés de quem escreveu o sistema conhecer o campus de olhos fechados.

Regras quando fizer: alguém sempre ao lado pronto para segurar; campus vazio; quem venda
não é quem programou aquele trecho; rota desconhecida. **Registrar sempre como
simulação**, nunca como teste com usuário — mesma honestidade acadêmica da regra de dado
sintético do escopo antigo.

### 12.2 Avaliação com 10 usuários (TCC II)

**Não começa sem aprovação do CEP.** Ver §13.8.

Composição: 5–6 pessoas com deficiência visual (misturar cegueira congênita e adquirida,
bengala e cão-guia) e 4–5 videntes que não conhecem o campus, para a parte visual e como
comparação. Inclusão: maior de 18 anos, usuário de smartphone com leitor de tela no grupo
prioritário, deslocamento autônomo. Recrutamento pelo núcleo de acessibilidade da
universidade.

Métricas:
- **Objetivas** — taxa de conclusão, tempo até o destino, nº de desvios, nº de paradas
  por confusão, **nº de orientações erradas emitidas** (crítica).
- **Subjetivas** — SUS (comparável com a literatura) e NASA-TLX reduzido para carga
  cognitiva.
- **Qualitativas** — think-aloud durante o percurso e entrevista curta no fim.

Sessão de ~40 min: consentimento lido em voz alta (cópia em áudio disponível),
familiarização parada, 2–3 tarefas de navegação, think-aloud, questionários, entrevista.
Gravar áudio e trajeto; vídeo só com consentimento específico e sem enquadrar rosto.

Segurança: participante usa bengala ou cão normalmente; pesquisador acompanha a poucos
passos; orientação perigosa = interrupção imediata registrada como falha grave;
interrupção livre a qualquer momento; horário de menor movimento.

Piloto com 1–2 pessoas antes, fora da amostra.

**Plano B**, se o CEP não sair a tempo: avaliação com especialistas (profissionais de
orientação e mobilidade, núcleo de acessibilidade) em vez de usuários finais. Vale menos,
mas salva a entrega e tem mais peso que o teste com vendas.

---

## 13. Decisões pendentes

Não implemente nada que dependa destes pontos sem confirmar antes.

**Resolvidas em 14/10/2026:**
- ~~Interno ou externo~~ → **somente externo** (§1). Beacons, Wi-Fi fingerprinting e QR
  code saem do escopo.

**Com a orientadora / Prof. Jamilson:**

1. **Precisão mínima aceitável** para emitir orientação direcional. Provisório
   `PRECISAO_MINIMA_METROS=15`; fechar com o resultado da §11.
2. **Plataforma:** web mobile (PWA) ou app nativo. Amarra a vibração: o iOS não suporta
   `navigator.vibrate()`. Provisório: web, pelo custo e pelo reaproveitamento do que
   existe. Se vibração for requisito firme, a decisão muda.
3. **Funciona offline?** Afeta a arquitetura inteira.
4. **Extensão do mapeamento** no TCC I — recorte do campus, não o campus inteiro.
5. **Calibração** das penalidades de custo e das faixas de setor angular.
6. **Como identificar caminhos acessíveis** para cada perfil, e quem valida essa
   classificação.
7. **Contribuição científica.** Fechar onde está a novidade: no módulo de orientação, na
   metodologia de avaliação, ou em ambos. Sem isso o TCC II vira "integramos bibliotecas
   existentes".
8. **Comitê de Ética.** Teste com pessoas com deficiência visual envolve população
   vulnerável — submissão ao CEP pela Plataforma Brasil é provável e leva de 2 a 4 meses.
   **É o item de maior risco de cronograma.** Levantar o prazo imediatamente e submeter
   antes de qualquer recrutamento. O protocolo da §12.2 serve de anexo da submissão.

Enquanto pendente: implemente com valor provisório, deixe configurável, e registre em
`docs/decisoes-pendentes.md`.

---

## 14. Custos

O projeto é desenhado para **custo zero**:

- Tiles do mapa: OpenStreetMap, sem chave, sem cartão.
- Roteamento: pgRouting no nosso próprio banco.
- Voz: Web Speech API, nativa do navegador.
- Localização, bússola e vibração: APIs do navegador.

O Google Maps Platform cobraria por tiles, roteamento e busca de lugar — justamente as
três coisas que não servem aqui: **o Google não conhece o caminho interno entre o Prédio
31 e o 32, nem onde ficam as escadas do campus**. O grafo tem que ser nosso de qualquer
jeito, então pagar por roteamento seria pagar por uma resposta errada. Além disso exige
conta de faturamento com cartão mesmo dentro da camada gratuita, e muda o termo de
consentimento (entra um terceiro recebendo IP dos participantes). **Não adotar sem
decisão explícita da equipe.**

Com a decisão de ficar só nas áreas externas, não sobra nenhum item com custo real.

---

## 15. O que foi aposentado na mudança de escopo

Continua no repositório e no histórico, mas **não é mais desenvolvido**:

- Camada de validação de crowdsourcing (`validacao/`): geofence, DBSCAN, promoção por
  sessões distintas, `sessao_hash`
- Tabelas `alertas`, `barreiras`, `alertas_rejeitados`, `area_estudo`
- Gerador de dados sintéticos, análise de sensibilidade, figura do funil
- Protocolo de coleta colaborativa em campo

**Continua válido e em uso:** Docker Compose, PostGIS, sistema de migrations
(`db/banco.sh`), FastAPI e sua estrutura, frontend Leaflet com proxy same-origin no
nginx, CI/CD no GitHub Actions, pilha de produção com `TOKEN_ADMIN`, HTTPS via túnel
(necessário para geolocalização e bússola), e a disciplina de SRID da §5.

Material teórico de VGI (Goodchild, Haklay, Liu, Miyata) sai do referencial. Entra
literatura de navegação assistiva e orientação espacial para pessoas cegas.

---

## 16. Marcos

Trabalhe **um marco por vez**. Não antecipe marcos futuros sem pedido explícito.

**TCC I — entrega conceitual (próxima reunião: ~2 a 3 semanas após 08/10/2026)**
- **E1** — escopo atualizado: problema, público-alvo, objetivos
- **E2** — requisitos RF/RNF revisados, com critério de verificação por item
- **E3** — diagrama de arquitetura + estudo das tecnologias de localização e áudio,
  sustentado pela medição da §11
- **E4** — plano de mapeamento do campus
- **E5** — cronograma e divisão de responsabilidades
- **E6** — protótipo demonstrativo (mapa 2D + rota + uma orientação falada), se der tempo

**Código, em paralelo**
- **M1** — migrations novas: `pontos_interesse`, `nos`, `arestas`, pgRouting habilitado
- **M2** — recorte do campus digitalizado (não o campus todo)
- **M3** — `GET /pontos-interesse` e `POST /rotas` funcionando
- **M4** — `app/orientacao/` com testes; `POST /orientacoes`
- **M5** — frontend: seleção de destino, rota desenhada, voz e vibração
- **M6** — avaliação com usuários (depende do CEP, §13.8)

---

## 17. Convenções de código

- Código, nomes de variáveis e comentários em **português**, seguindo o domínio
  (`rota`, `aresta`, `orientacao`, `ponto_interesse`). Termos técnicos consagrados ficam
  em inglês (`bbox`, `commit`, `bearing` quando for jargão).
- SQL de migration é **idempotente sempre que possível** (`IF NOT EXISTS`).
- Migrations são **imutáveis** depois de aplicadas. Correção vira migration nova. Isso
  inclui as migrations do escopo antigo: não edite, não apague.
- Nenhuma credencial ou string de conexão no código ou no Git. Tudo via `.env`, com
  `.env.example` versionado sem valores reais.
- Toda função em `orientacao/` e `rotas/` tem teste.
- Commits pequenos, mensagem em português, escopo claro.
- Dado de campus mapeado manualmente é **dado de pesquisa**: versionado em `db/seeds/`,
  com registro de quem mapeou e quando.

---

## 18. Como trabalhar comigo neste repositório

- Antes de criar arquivo novo, verifique se já existe algo equivalente.
- Mudanças em schema do banco: **sempre** via migration, nunca `ALTER` manual.
- Se uma tarefa exigir decisão listada na §13, **pare e pergunte**.
- Qualquer coisa que gere orientação para o usuário passa pelo princípio de segurança da
  §1: na dúvida, o sistema cala a boca.
- Dado de simulação (teste com vendas, GPS sintético) sai sempre rotulado como simulação.
- Ao concluir um marco, rode os testes e resuma em uma frase o que passou a funcionar.
- Prefira a solução mais simples que resolve. Este é um TCC de graduação com prazo, não
  um sistema de produção.
