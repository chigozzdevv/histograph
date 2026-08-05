FROM node:22-alpine AS dependencies

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY client/package.json ./client/package.json

RUN pnpm install --frozen-lockfile

FROM dependencies AS build

COPY client ./client

RUN pnpm --dir client build

FROM node:22-alpine AS runtime

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY --from=build --chown=node:node /app/client/.next/standalone ./
COPY --from=build --chown=node:node /app/client/.next/static ./client/.next/static

USER node

EXPOSE 3000

CMD ["node", "client/server.js"]
