/**
 * Identificador de sessão do voluntário no navegador.
 *
 * É um UUID gerado localmente e persistido em localStorage, para que reports
 * feitos no mesmo aparelho usem o mesmo `sessao_id` (o servidor deriva
 * `sessao_hash` a partir dele — nunca guarda IP). Se localStorage não estiver
 * disponível (modo privado, política do navegador, etc.), cai para um UUID
 * em memória: a sessão ainda funciona, só não sobrevive a um recarregamento.
 *
 * `crypto.randomUUID` só existe em contexto seguro (HTTPS ou localhost). Numa
 * URL http:// (ex.: um teste pelo IP do notebook na rede local) ele não existe,
 * e o envio quebraria; `gerarUuid` cai então para `crypto.getRandomValues`, que
 * existe em qualquer contexto.
 */

const CHAVE_ARMAZENAMENTO = "msb.sessao_id";

let sessaoEmMemoria: string | null = null;

/**
 * UUID versão 4 (RFC 9562): 122 bits aleatórios. Usa `crypto.randomUUID` quando
 * ele existe; senão monta o mesmo formato a partir de 16 bytes de
 * `crypto.getRandomValues`, marcando os bits de versão (4) e de variante (10).
 */
export function gerarUuid(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40; // versão 4
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80; // variante RFC 9562
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join("-");
}

export function obterSessaoId(): string {
  try {
    const existente = localStorage.getItem(CHAVE_ARMAZENAMENTO);
    if (existente) {
      return existente;
    }
    const novo = gerarUuid();
    localStorage.setItem(CHAVE_ARMAZENAMENTO, novo);
    return novo;
  } catch {
    if (!sessaoEmMemoria) {
      sessaoEmMemoria = gerarUuid();
    }
    return sessaoEmMemoria;
  }
}
