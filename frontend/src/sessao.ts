/**
 * Identificador de sessão do voluntário no navegador.
 *
 * É um UUID gerado localmente e persistido em localStorage, para que reports
 * feitos no mesmo aparelho usem o mesmo `sessao_id` (o servidor deriva
 * `sessao_hash` a partir dele — nunca guarda IP). Se localStorage não estiver
 * disponível (modo privado, política do navegador, etc.), cai para um UUID
 * em memória: a sessão ainda funciona, só não sobrevive a um recarregamento.
 */

const CHAVE_ARMAZENAMENTO = "msb.sessao_id";

let sessaoEmMemoria: string | null = null;

function gerarUuid(): string {
  return crypto.randomUUID();
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
