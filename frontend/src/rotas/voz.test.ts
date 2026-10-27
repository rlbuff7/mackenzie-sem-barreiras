import assert from "node:assert/strict";
import { test } from "node:test";
import { avisoDeVoz, escolherVoz, falar, type FalaDeVoz, type SinteseDeVoz, type VozDoAparelho } from "./voz.ts";

function sinteseFalsa(vozes: VozDoAparelho[] = []) {
  const registro = { falas: [] as FalaDeVoz[], textos: [] as string[], cancelamentos: 0 };
  let proximo = "";
  const sintese: SinteseDeVoz = {
    speak(fala: never) {
      registro.falas.push(fala as FalaDeVoz);
      registro.textos.push(proximo);
    },
    cancel() {
      registro.cancelamentos++;
    },
    getVoices: () => vozes,
  };
  const criarFala = (texto: string): FalaDeVoz => {
    proximo = texto;
    return { lang: "", voice: null, onend: null, onerror: null };
  };
  return { sintese, criarFala, registro };
}

test("sem speechSynthesis, falar devolve null (a tela mostra o aviso em texto)", () => {
  assert.equal(falar(["oi"], { sintese: null, criarFala: () => ({ lang: "", voice: null, onend: null, onerror: null }) }), null);
});

test("uma fala por texto, em ordem, sempre com lang pt-BR", () => {
  const { sintese, criarFala, registro } = sinteseFalsa();
  falar(["primeira", "segunda", "terceira"], { sintese, criarFala });
  assert.deepEqual(registro.textos, ["primeira", "segunda", "terceira"]);
  assert.ok(registro.falas.every((f) => f.lang === "pt-BR"));
});

test("usa a voz pt-BR quando existe; senão deixa sem voz (lang pt-BR basta)", () => {
  const pt = { lang: "pt-BR", name: "Luciana" };
  const com = sinteseFalsa([{ lang: "en-US" }, pt]);
  falar(["x"], com);
  assert.equal(com.registro.falas[0]?.voice, pt);
  const sem = sinteseFalsa([{ lang: "en-US" }]);
  falar(["x"], sem);
  assert.equal(sem.registro.falas[0]?.voice, null);
});

test("escolherVoz aceita pt_BR e outra variante de português, com pt-BR na frente", () => {
  assert.equal(escolherVoz([{ lang: "pt-PT" }, { lang: "pt_BR" }])?.lang, "pt_BR");
  assert.equal(escolherVoz([{ lang: "pt-PT" }])?.lang, "pt-PT");
  assert.equal(escolherVoz([{ lang: "es-ES" }]), null);
});

test("aviso de voz só quando há vozes carregadas e nenhuma é portuguesa", () => {
  assert.equal(avisoDeVoz([]), null);
  assert.equal(avisoDeVoz([{ lang: "pt-BR" }]), null);
  assert.match(avisoDeVoz([{ lang: "en-US" }]) ?? "", /voz em português/);
});

test("parar chama cancel e não dispara aoTerminar depois", () => {
  const { sintese, criarFala, registro } = sinteseFalsa();
  let terminou = 0;
  const leitura = falar(["a", "b"], { sintese, criarFala, aoTerminar: () => terminou++ });
  const antes = registro.cancelamentos;
  leitura?.parar();
  assert.equal(registro.cancelamentos, antes + 1);
  registro.falas[1]?.onend?.();
  assert.equal(terminou, 0);
});

test("o fim da última fala chama aoTerminar uma vez, sem falha", () => {
  const { sintese, criarFala, registro } = sinteseFalsa();
  const fins: boolean[] = [];
  falar(["a", "b"], { sintese, criarFala, aoTerminar: (f) => fins.push(f) });
  registro.falas[0]?.onend?.();
  assert.deepEqual(fins, []);
  registro.falas[1]?.onend?.();
  registro.falas[1]?.onend?.();
  assert.deepEqual(fins, [false]);
});

test("erro real da voz avisa falha; 'canceled' não", () => {
  const { sintese, criarFala, registro } = sinteseFalsa();
  const fins: boolean[] = [];
  falar(["a"], { sintese, criarFala, aoTerminar: (f) => fins.push(f) });
  registro.falas[0]?.onerror?.({ error: "canceled" });
  assert.deepEqual(fins, []);
  registro.falas[0]?.onerror?.({ error: "synthesis-failed" });
  assert.deepEqual(fins, [true]);
});

test("speak que lança não quebra: avisa falha e devolve algo que se pode parar", () => {
  const { criarFala } = sinteseFalsa();
  const quebrada: SinteseDeVoz = {
    speak() {
      throw new Error("sem voz");
    },
    cancel() {},
    getVoices: () => [],
  };
  const fins: boolean[] = [];
  const leitura = falar(["a"], { sintese: quebrada, criarFala, aoTerminar: (f) => fins.push(f) });
  assert.deepEqual(fins, [true]);
  assert.doesNotThrow(() => leitura?.parar());
});
