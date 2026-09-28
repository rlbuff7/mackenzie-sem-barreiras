# Imagem da API do Mackenzie sem Barreiras (M2). Build a partir de ./backend
# (docker-compose.yml, serviço `api`).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Só os manifests primeiro: uma mudança em app/ não invalida o cache desta
# camada, então `uv sync` não roda de novo a cada alteração de código.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/

# Usuário não-root: a API não precisa de privilégios dentro do container.
RUN useradd --create-home --shell /usr/sbin/nologin msb \
    && chown -R msb:msb /app
USER msb

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
