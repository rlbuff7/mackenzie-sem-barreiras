# Frontend — Mackenzie sem Barreiras

Interface web do voluntário: mapa (Leaflet + OpenStreetMap) com a área de estudo e as
barreiras já validadas, e formulário para reportar uma nova barreira. TypeScript puro
(sem framework de UI), Vite.

## Como rodar

```bash
cd frontend
npm install
cp .env.example .env   # ajuste VITE_API_URL se a API não estiver em localhost:8000
npm run dev            # http://localhost:5173
```

A API (Task 2/3, FastAPI) precisa estar rodando e com CORS liberado para
`http://localhost:5173` (já é o padrão do backend em desenvolvimento).

Outros scripts:

- `npm run verificar` — só o type-check (`tsc --noEmit`).
- `npm run build` — type-check + build de produção (`dist/`).
- `npm run preview` — serve o build de produção localmente.

## Variáveis de ambiente

| Variável | Padrão usado no código | Descrição |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Base da API. Lida em `src/api.ts` via `import.meta.env.VITE_API_URL`. |

`.env` nunca é commitado; `.env.example` documenta a variável sem valor sensível (não há
segredo aqui, é só a URL da API).

## Estrutura

```
src/
├── main.ts        # ponto de entrada: liga mapa, formulário, botões de seleção de ponto e a lista acessível de barreiras
├── api.ts         # cliente HTTP tipado, um a um com o Contrato da API (docs/api.md)
├── sessao.ts       # sessao_id (UUID) em localStorage, com fallback em memória
├── mapa.ts         # mapa Leaflet: tiles OSM, área de estudo, barreiras por bbox, seleção de ponto
├── formulario.ts   # formulário de envio de alerta e mensagens de status
└── estilos.css     # todo o CSS da aplicação
```

## Decisões de acessibilidade

- **Nunca só cor.** Barreira confirmada é um círculo cheio; pendente é um losango
  tracejado. A legenda repete as mesmas formas. O popup de cada marcador sempre traz o
  tipo, o status por extenso e o número de confirmações em texto.
- **Ponto do alerta sem depender do mouse.** Além de tocar/clicar no mapa, há dois
  botões — "Usar minha localização" e "Usar o centro do mapa" — inteiramente operáveis
  por teclado, para quem não consegue mirar um clique preciso no mapa.
- **Foco visível** em toda a página (`:focus-visible`), com uma cor de contorno
  (laranja queimado) diferente da cor primária, para se destacar tanto sobre o fundo
  claro quanto sobre os próprios botões azuis.
- **Alvos de toque ≥ 44 px** em botões, campo de tipo, textarea e cada opção de
  severidade (rótulo inteiro clicável, não só o círculo do radio) — a coleta é feita
  no celular, em campo.
- **Mensagens em região `aria-live="polite"`.** Duas regiões: uma perto do mapa, para
  o ponto selecionado (e falhas de geolocalização); outra no formulário, para o
  resultado do envio (sucesso, descarte por estar fora da área, erro 422 por campo, ou
  falha de rede) — sempre reaproveitando o campo `mensagem` que a API devolve.
- **HTML semântico.** `<label>` em todo campo, `<fieldset>`/`<legend>` na severidade,
  `lang="pt-BR"`, hierarquia de `<h1>`/`<h2>`, link para pular para o conteúdo.
- **Contraste AA** conferido nas combinações de texto/fundo e nas cores dos marcadores
  contra o fundo branco do próprio marcador (não contra o mapa, cuja cor de fundo
  varia).
- **Marcadores fora do Tab, com alternativa em lista.** Os marcadores de barreira no
  mapa não entram na ordem de tabulação (`marker.options.keyboard = false`): com até
  `LIMITE_BARREIRAS_POR_CONSULTA` (1000) marcadores na mesma bbox, colocar todos no Tab
  tornaria a navegação por teclado impraticável. Em troca, a seção "Barreiras nesta área
  do mapa" mostra a mesma coleção como uma lista de botões reais — cada um focável,
  trazendo tipo, status por extenso e confirmações, e que ao ser ativado centraliza o
  mapa na barreira e abre o popup dela. A contagem da lista fica numa região
  `aria-live` própria, atualizada só quando o número muda (para não repetir o anúncio a
  cada recarga sem novidade); a lista em si não é `aria-live` (evita ler dezenas de
  itens inteiros a cada atualização).
