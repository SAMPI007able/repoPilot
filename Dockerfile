# Railway builds the repository root, so this Dockerfile explicitly packages
# the FastAPI backend and its Node-based repository parser from the monorepo.
FROM node:22-bookworm-slim AS parser-runtime

WORKDIR /app/parser
COPY backend/parser/package*.json ./
RUN npm ci --omit=dev

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=parser-runtime /usr/local/bin/node /usr/local/bin/node
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/app /app/app
COPY backend/parser /app/parser
COPY backend/migrations /app/migrations
COPY start.sh /usr/local/bin/start.sh
COPY --from=parser-runtime /app/parser/node_modules /app/parser/node_modules
RUN node --experimental-strip-types /app/parser/parse.ts /app/parser/parse.ts > /dev/null
RUN chmod +x /usr/local/bin/start.sh

RUN groupadd --gid 10001 testforge \
    && useradd --uid 10001 --gid testforge --system --create-home testforge \
    && mkdir -p /app/workspace \
    && chown -R testforge:testforge /app
USER testforge

EXPOSE 8000
CMD ["start.sh"]
