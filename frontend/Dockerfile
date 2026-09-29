# Imagem do frontend do Mackenzie sem Barreiras (M5). Build a partir de
# ./frontend (docker-compose.yml, serviço `frontend`). Multi-stage: compila o
# Vite em node:22-alpine e serve só o `dist/` estático em nginx:alpine — a
# imagem final não carrega Node nem node_modules.
#
#   docker compose build frontend --build-arg VITE_API_URL=http://localhost:8000
#
# VITE_API_URL precisa estar disponível em tempo de BUILD (não de execução):
# `import.meta.env.VITE_API_URL` (frontend/src/api.ts) é substituído pelo Vite
# no bundle gerado, então a URL da API fica fixada na imagem.

FROM node:22-alpine AS build
WORKDIR /app

# Só os manifests primeiro: uma mudança em src/ não invalida esta camada.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json index.html ./
COPY src/ ./src/

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
