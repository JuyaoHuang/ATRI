FROM node:22-alpine AS build

WORKDIR /app/frontend

ARG VITE_API_BASE_URL=/
ARG VITE_WS_URL=/ws

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_URL=${VITE_WS_URL}

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine

COPY docker/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
