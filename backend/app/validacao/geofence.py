"""Estágio 2 do pipeline de validação: geofence (CLAUDE.md §6, estágio 2)."""

from psycopg import Connection


def ponto_dentro_da_area(
    conexao: Connection, latitude: float, longitude: float, srid_armazenamento: int
) -> bool:
    """True se o ponto cai dentro de alguma linha de `area_estudo`.

    Usa `ST_Within(ponto, area)`, cuja semântica considera apenas o INTERIOR
    do polígono: um ponto exatamente sobre a borda da área de estudo conta
    como FORA. Sem nenhuma área cadastrada, não há contra o que validar e a
    função devolve `False` (por segurança: melhor descartar do que aceitar
    sem geofence nenhum).
    """
    linha = conexao.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM area_estudo
            WHERE ST_Within(
                ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), %(srid)s),
                geom
            )
        )
        """,
        {
            "longitude": longitude,
            "latitude": latitude,
            "srid": srid_armazenamento,
        },
    ).fetchone()
    return linha[0]
