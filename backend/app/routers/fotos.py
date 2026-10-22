"""Fotos dos pontos de controle: `POST /medicoes/fotos`, `GET /medicoes/fotos/resumo`
e `GET /medicoes/fotos/{id}` (contrato de 22/10/2026).

Dado DA EQUIPE, nunca de quem navega. A foto chega como corpo bruto `image/jpeg`
(sem `python-multipart`), com os parâmetros na query string. A API recusa JPEG com
metadados EXIF (que podem trazer GPS e quem fotografou): o app reprocessa a imagem
num canvas, que os descarta, e aqui conferimos que foi isso que chegou.

Protegida pelo mesmo código da equipe de `POST /medicoes` (503 desligada, 401 errado).
Idempotente por `id_cliente` (`ON CONFLICT DO NOTHING`): reenvio devolve
`gravada=false`. Rota `async` pelo mesmo motivo de `POST /medicoes`: lê o corpo em
fluxo, com teto de `LIMITE_FOTO_BYTES`, antes de qualquer outra coisa.
"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg import Connection
from pydantic import ValidationError

from app.db import ConexaoDaRequisicao
from app.routers.alertas import _ler_corpo_limitado
from app.routers.medicoes import exigir_codigo_equipe
from app.routers.validacao import exigir_token_admin
from app.schemas.foto import FotoParametros
from app.validacao.mensagens import traduzir_erros_da_requisicao

router = APIRouter(prefix="/medicoes/fotos")

LIMITE_FOTO_BYTES = 1_048_576  # 1 MiB, igual à CHECK do banco
_ASSINATURA_JPEG = b"\xff\xd8\xff"
_MARCA_EXIF = b"Exif\x00\x00"
_JANELA_EXIF_BYTES = 64 * 1024

_SQL_INSERIR = """
    INSERT INTO fotos_pontos (
        id_cliente, ponto, aparelho, tirada_em, conteudo, tamanho_bytes,
        largura_px, altura_px, sha256, observacao
    ) VALUES (
        %(id_cliente)s, %(ponto)s, %(aparelho)s, %(tirada_em)s, %(conteudo)s,
        %(tamanho_bytes)s, %(largura_px)s, %(altura_px)s, %(sha256)s, %(observacao)s
    )
    ON CONFLICT (id_cliente) DO NOTHING
"""


def _erro(status: int, mensagem: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"mensagem": mensagem})


def _gravar(conexao: Connection, parametros: FotoParametros, conteudo: bytes) -> bool:
    with conexao.cursor() as cursor:
        cursor.execute(
            _SQL_INSERIR,
            {
                **parametros.model_dump(),
                "conteudo": conteudo,
                "tamanho_bytes": len(conteudo),
                "sha256": hashlib.sha256(conteudo).hexdigest(),
            },
        )
        return cursor.rowcount == 1


@router.post("", dependencies=[Depends(exigir_codigo_equipe)])
async def gravar_foto(request: Request, conexao: ConexaoDaRequisicao) -> JSONResponse:
    try:
        parametros = FotoParametros.model_validate(dict(request.query_params))
    except ValidationError as erro:
        return JSONResponse(
            status_code=422,
            content={
                "mensagem": "Foto inválida.",
                "erros": traduzir_erros_da_requisicao(erro.errors()),
            },
        )
    tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if tipo != "image/jpeg":
        return _erro(415, "Envie a foto como image/jpeg.")
    corpo = await _ler_corpo_limitado(request, LIMITE_FOTO_BYTES)
    if corpo is None or not corpo:
        return _erro(413, "A foto está vazia ou passa de 1 MiB.")
    if not corpo.startswith(_ASSINATURA_JPEG):
        return _erro(415, "O arquivo não é um JPEG.")
    if _MARCA_EXIF in corpo[:_JANELA_EXIF_BYTES]:
        return _erro(422, "A foto tem metadados (EXIF); envie pelo app, que remove.")
    gravada = await run_in_threadpool(_gravar, conexao, parametros, corpo)
    return JSONResponse(content={"gravada": gravada})


@router.get("/resumo", dependencies=[Depends(exigir_token_admin)])
def resumo(conexao: ConexaoDaRequisicao) -> list[dict[str, object]]:
    """Fotos por ponto x aparelho, sem os bytes. Ponto sem referência (11, 12) usa
    `P11`/`P12` como código."""
    linhas = conexao.execute(
        """
        SELECT coalesce(p.codigo, 'P' || lpad(f.ponto::text, 2, '0')), f.ponto, f.aparelho,
               count(*), max(f.recebida_em)
        FROM fotos_pontos f
        LEFT JOIN pontos_controle p ON p.numero = f.ponto
        GROUP BY p.codigo, f.ponto, f.aparelho
        ORDER BY f.ponto, f.aparelho
        """
    ).fetchall()
    return [
        {
            "ponto_codigo": codigo,
            "ponto": ponto,
            "aparelho": aparelho,
            "fotos": fotos,
            "ultima_em": ultima.isoformat(),
        }
        for codigo, ponto, aparelho, fotos, ultima in linhas
    ]


@router.get("/{foto_id}", dependencies=[Depends(exigir_token_admin)])
def baixar(foto_id: int, conexao: ConexaoDaRequisicao) -> Response:
    linha = conexao.execute(
        "SELECT conteudo FROM fotos_pontos WHERE id = %s", (foto_id,)
    ).fetchone()
    if linha is None:
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return Response(
        content=bytes(linha[0]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
