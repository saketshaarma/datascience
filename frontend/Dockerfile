# ---------- Build stage ----------
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY . .

# The app calls `${REACT_APP_BACKEND_URL}/api`. For self-hosting behind Nginx we
# leave this empty so requests go to the same origin (/api) and Nginx proxies them
# to the backend. Override with --build-arg REACT_APP_BACKEND_URL=https://api.example.com
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV DISABLE_HOT_RELOAD=true

RUN yarn build

# ---------- Serve stage ----------
FROM nginx:1.27-alpine

# Nginx official image renders templates with envsubst on startup.
# NGINX_ENVSUBST_FILTER ensures only BACKEND_HOST is substituted (not $host, $uri, ...).
ENV BACKEND_HOST=backend:8001 \
    NGINX_ENVSUBST_FILTER=BACKEND_HOST

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1
