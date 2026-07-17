# syntax=docker/dockerfile:1.7

FROM node:24.14.0-bookworm-slim

ENV NODE_ENV=production

RUN groupadd --gid 10001 storyforge-gateway && \
    useradd --uid 10001 --gid storyforge-gateway --no-create-home storyforge-gateway

WORKDIR /app
COPY --chown=10001:10001 deploy/ingress.mjs ./ingress.mjs

USER 10001:10001
EXPOSE 3000 8000

CMD ["node", "ingress.mjs"]
