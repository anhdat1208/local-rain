# syntax=docker/dockerfile:1

FROM node:22-alpine AS deps
WORKDIR /app

COPY packages/shared ./packages/shared
COPY apps/web/package.json apps/web/.npmrc ./apps/web/

WORKDIR /app/apps/web
RUN npm install

FROM node:22-alpine AS build
WORKDIR /app

COPY packages/shared ./packages/shared
COPY apps/web ./apps/web
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules

WORKDIR /app/apps/web
ARG NUXT_PUBLIC_API_BASE=http://localhost:8000
ENV NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000 \
    NUXT_HOST=0.0.0.0 \
    NUXT_PORT=3000

COPY --from=build /app/apps/web/.output ./.output
COPY --from=build /app/apps/web/package.json ./package.json

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]
