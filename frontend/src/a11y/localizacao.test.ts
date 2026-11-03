import assert from "node:assert/strict";
import { test } from "node:test";
import type { FalaDeVoz, SinteseDeVoz } from "../rotas/voz.ts";
import { criarOrientacao, ligarBotaoDeVoz } from "./localizacao.ts";
import { CHAVE_VOZ_ATIVA } from "./orientacao.ts";

const TELA_A = { nome: "Rota traçada", acao: "Cerca de 182 metros." };
const TELA_B = { nome: "Escolher destino", acao: "Escolha os pontos." };

function armazemFalso(inicial: Record<string, string> = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    dados,
    getItem: (c: string) => dados.get(c) ?? null,
    setItem: (c: string, v: string) => void dados.set(c, v),
    removeItem: (c: string) => void dados.delete(c),
  };
}

/** Síntese de mentira: guarda o que foi falado; `falhar` dispara onerror na fala (como o navegador que exige um toque). */
function sinteseFalsa(opcoes: { falhar?: boolean } = {}) {
  const falas: FalaDeVoz[] = [];
  const textos: string[] = [];
  let cancelamentos = 0;
  const sintese: SinteseDeVoz = {
    speak(fala: never) {
      const f = fala as FalaDeVoz & { text: string };
      falas.push(f);
      textos.push(f.text);
      if (opcoes.falhar) f.onerror?.({ error: "not-allowed" });
    },
    cancel() {
      cancelamentos++;
    },
    getVoices: () => [{ lang: "pt-BR", name: "Voz de teste" }],
  };
  return { sintese, falas, textos, cancelamentos: () => cancelamentos };
}

function montar(opcoes: { sintese?: ReturnType<typeof sinteseFalsa> | null; armazem?: ReturnType<typeof armazemFalso> | null } = {}) {
  const documento = { title: "" };
  const regiao: { textContent: string | null } = { textContent: "" };
  const agenda: (() => void)[] = [];
  const sintese = opcoes.sintese === undefined ? sinteseFalsa() : opcoes.sintese;
  const armazem = opcoes.armazem === undefined ? armazemFalso() : opcoes.armazem;
  const orientacao = criarOrientacao({
    documento,
    regiao,
    sintese: sintese?.sintese ?? null,
    criarFala: (texto) => ({ text: texto, lang: "", voice: null, onend: null, onerror: null }) as unknown as FalaDeVoz,
    armazem,
    agendar: (fn) => agenda.push(fn) - 1,
    cancelarAgenda: (id) => {
      agenda[id as number] = () => {};
    },
  });
  const passarTempo = (): void => {
    while (agenda.length > 0) agenda.shift()!();
  };
  return { documento, regiao, orientacao, sintese, armazem, passarTempo };
}

test("definirTela põe o título e não anuncia nada", () => {
  const { documento, regiao, orientacao, passarTempo } = montar();
  orientacao.definirTela(TELA_A);
  passarTempo();
  assert.equal(documento.title, "Rota traçada · Navegação Acessível no Campus");
  assert.equal(regiao.textContent, "");
});

test("mudarDeTela: o título muda e a região aria-live recebe UMA frase 'Você está em: ...' (limpa e escreve depois)", () => {
  const { documento, regiao, orientacao, passarTempo } = montar();
  regiao.textContent = "frase velha";
  orientacao.mudarDeTela(TELA_A);
  assert.equal(documento.title, "Rota traçada · Navegação Acessível no Campus");
  assert.equal(regiao.textContent, "", "primeiro limpa, para repetir a mesma frase também ser lido");
  passarTempo();
  assert.equal(regiao.textContent, "Você está em: Rota traçada. Cerca de 182 metros.");
});

test("duas trocas seguidas: só a última frase chega à região", () => {
  const { regiao, orientacao, passarTempo } = montar();
  orientacao.mudarDeTela(TELA_A);
  orientacao.mudarDeTela(TELA_B);
  passarTempo();
  assert.equal(regiao.textContent, "Você está em: Escolher destino. Escolha os pontos.");
});

test("mudarDeTela com anunciar:false só troca o título (região vazia)", () => {
  const { documento, regiao, orientacao, passarTempo } = montar();
  orientacao.mudarDeTela(TELA_B, { anunciar: false });
  passarTempo();
  assert.equal(documento.title, "Escolher destino · Navegação Acessível no Campus");
  assert.equal(regiao.textContent, "");
});

test("nada fala sozinho: com a voz desligada, trocar de tela não chama a síntese", () => {
  const { sintese, orientacao, passarTempo } = montar();
  orientacao.mudarDeTela(TELA_A);
  passarTempo();
  assert.deepEqual(sintese!.textos, []);
  assert.equal(orientacao.vozAtiva(), false);
});

test("'Ativar voz': liga, guarda a preferência e fala a orientação da tela atual dentro do toque", () => {
  const { sintese, armazem, regiao, orientacao, passarTempo } = montar();
  orientacao.definirTela(TELA_A);
  const ligada = orientacao.alternarVoz();
  assert.equal(ligada, true);
  assert.deepEqual(sintese!.textos, ["Você está em: Rota traçada. Cerca de 182 metros."]);
  assert.equal(armazem!.dados.get(CHAVE_VOZ_ATIVA), "1");
  passarTempo();
  assert.equal(regiao.textContent, "", "falando com a voz do app, a região fica vazia (leitor de tela e voz não se atropelam)");
});

test("com a voz ligada, cada mudança de tela é falada e a região não repete a frase", () => {
  const { sintese, regiao, orientacao, passarTempo } = montar();
  orientacao.definirTela(TELA_A);
  orientacao.alternarVoz();
  orientacao.mudarDeTela(TELA_B);
  passarTempo();
  assert.equal(sintese!.textos.length, 2);
  assert.equal(sintese!.textos[1], "Você está em: Escolher destino. Escolha os pontos.");
  assert.equal(regiao.textContent, "");
});

test("a fala usa a voz e a velocidade escolhidas em Ajustes (msb-voz, msb-voz-velocidade)", () => {
  const armazem = armazemFalso({ "msb-voz": "Voz de teste", "msb-voz-velocidade": "1.2" });
  const { sintese, orientacao } = montar({ armazem });
  orientacao.definirTela(TELA_A);
  orientacao.alternarVoz();
  const fala = sintese!.falas[0]!;
  assert.equal(fala.lang, "pt-BR");
  assert.equal(fala.rate, 1.2);
  assert.deepEqual(fala.voice, { lang: "pt-BR", name: "Voz de teste" });
});

test("'Desativar voz': desliga, apaga a preferência, para a fala e volta ao anúncio no leitor de tela", () => {
  const { sintese, armazem, regiao, orientacao, passarTempo } = montar();
  orientacao.definirTela(TELA_A);
  orientacao.alternarVoz();
  const antes = sintese!.cancelamentos();
  assert.equal(orientacao.alternarVoz(), false);
  assert.equal(armazem!.dados.has(CHAVE_VOZ_ATIVA), false);
  assert.ok(sintese!.cancelamentos() > antes, "cancela a fala em curso");
  orientacao.mudarDeTela(TELA_B);
  passarTempo();
  assert.equal(sintese!.textos.length, 1, "não fala mais");
  assert.equal(regiao.textContent, "Você está em: Escolher destino. Escolha os pontos.");
});

test("voz já ligada de visitas anteriores: continua ligada e fala a cada mudança de tela", () => {
  const armazem = armazemFalso({ [CHAVE_VOZ_ATIVA]: "1" });
  const { sintese, orientacao } = montar({ armazem });
  assert.equal(orientacao.vozAtiva(), true);
  orientacao.definirTela(TELA_A); // carregar a página não fala
  assert.deepEqual(sintese!.textos, []);
  orientacao.mudarDeTela(TELA_B);
  assert.equal(sintese!.textos.length, 1);
});

test("fala bloqueada pelo navegador (precisa de um toque): a frase cai na região aria-live", () => {
  const { regiao, orientacao, passarTempo } = montar({ sintese: sinteseFalsa({ falhar: true }) });
  orientacao.definirTela(TELA_A);
  orientacao.alternarVoz();
  passarTempo();
  assert.equal(regiao.textContent, "Você está em: Rota traçada. Cerca de 182 metros.");
});

test("sem síntese de voz: não liga, não guarda nada e o anúncio segue na região", () => {
  const { regiao, orientacao, armazem, passarTempo } = montar({ sintese: null });
  assert.equal(orientacao.temVoz(), false);
  assert.equal(orientacao.alternarVoz(), false);
  assert.equal(armazem!.dados.has(CHAVE_VOZ_ATIVA), false);
  orientacao.mudarDeTela(TELA_A);
  passarTempo();
  assert.equal(regiao.textContent, "Você está em: Rota traçada. Cerca de 182 metros.");
});

test("sem localStorage (null) funciona: vale só nesta visita", () => {
  const { orientacao, sintese } = montar({ armazem: null });
  orientacao.definirTela(TELA_A);
  assert.equal(orientacao.alternarVoz(), true);
  assert.equal(sintese!.textos.length, 1);
});

// ---------- o botão ----------

function botaoFalso() {
  const atributos = new Map<string, string>();
  let ouvinte: (() => void) | null = null;
  return {
    hidden: false as boolean | string,
    textContent: "Ativar voz" as string | null,
    setAttribute: (n: string, v: string) => void atributos.set(n, v),
    addEventListener: (_t: "click", fn: () => void) => {
      ouvinte = fn;
    },
    atributos,
    tocar: () => ouvinte?.(),
  };
}

test("botão: começa 'Ativar voz' com aria-pressed=false; ao tocar vira 'Desativar voz' com aria-pressed=true e volta", () => {
  const { orientacao } = montar();
  const botao = botaoFalso();
  const nota = { hidden: false as boolean | string, textContent: "" as string | null };
  ligarBotaoDeVoz(botao, nota, orientacao);
  assert.equal(botao.textContent, "Ativar voz");
  assert.equal(botao.atributos.get("aria-pressed"), "false");
  botao.tocar();
  assert.equal(botao.textContent, "Desativar voz");
  assert.equal(botao.atributos.get("aria-pressed"), "true");
  assert.match(nota.textContent ?? "", /Voz ligada/);
  botao.tocar();
  assert.equal(botao.textContent, "Ativar voz");
  assert.equal(botao.atributos.get("aria-pressed"), "false");
});

test("botão: com a preferência salva, a página já abre 'Desativar voz' e aria-pressed=true", () => {
  const { orientacao } = montar({ armazem: armazemFalso({ [CHAVE_VOZ_ATIVA]: "1" }) });
  const botao = botaoFalso();
  ligarBotaoDeVoz(botao, null, orientacao);
  assert.equal(botao.textContent, "Desativar voz");
  assert.equal(botao.atributos.get("aria-pressed"), "true");
});

test("botão: sem voz no navegador ele some e a nota explica que o leitor de tela continua valendo", () => {
  const { orientacao } = montar({ sintese: null });
  const botao = botaoFalso();
  const nota = { hidden: true as boolean | string, textContent: "" as string | null };
  ligarBotaoDeVoz(botao, nota, orientacao);
  assert.equal(botao.hidden, true);
  assert.equal(nota.hidden, false);
  assert.match(nota.textContent ?? "", /leitor de tela/);
});
