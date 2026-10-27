"""Rótulos de proveniência do dado de mapa (dado de pesquisa; grafo provisório sai rotulado)."""

ROTULO_PROVISORIO = (
    "PROVISÓRIO: caminhos do mapa aberto (OpenStreetMap), ainda não conferidos a pé. "
    "Só para demonstração."
)
ROTULO_IMAGEM = "Caminhos desenhados sobre mapa, ainda não conferidos a pé."
ROTULO_CONFERIDO = "Trecho conferido a pé pela equipe (dado de pesquisa)."
ATRIBUICAO_OSM = "Dados de mapa © contribuidores do OpenStreetMap (ODbL)."


def rotulo_das_fontes(fontes: set[str]) -> str:
    """Rótulo do pior caso: provisório > imagem > conferido a pé."""
    if "provisorio" in fontes:
        return ROTULO_PROVISORIO
    if fontes - {"conferido_a_pe"}:
        return ROTULO_IMAGEM
    return ROTULO_CONFERIDO
