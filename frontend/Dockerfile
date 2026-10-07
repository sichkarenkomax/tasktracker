# syntax=docker/dockerfile:1

# Stage 1 - build the SPA. This never runs on the production host: the
# resulting image only contains static files (docs/architecture.md, section 47).
FROM node:22-alpine AS build

WORKDIR /app

# Node tries AAAA records first; on networks where IPv6 stalls, npm hangs
# until its fetch timeout and the build dies with EIDLETIMEOUT. IPv4-first
# still uses IPv6 when a name has no A records.
ENV NODE_OPTIONS=--dns-result-order=ipv4first

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
# Vite copies `public/` verbatim into the bundle, which is where the self-hosted
# fonts live: the product runs without a CDN, so nothing may be fetched from one.
COPY public ./public
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]