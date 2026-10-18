FROM node:22-bookworm-slim AS parser-runtime

WORKDIR /app/parser
COPY parser/package*.json ./
RUN npm ci --omit=dev

WORKDIR /app/sandbox-runtime
COPY sandbox-runtime/package*.json ./
RUN npm ci --omit=dev

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=parser-runtime /usr/local/bin/node /usr/local/bin/node
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY app /app/app
COPY parser /app/parser
COPY sandbox-runtime /app/sandbox-runtime
COPY --from=parser-runtime /app/parser/node_modules /app/parser/node_modules
COPY --from=parser-runtime /app/sandbox-runtime/node_modules /app/sandbox-runtime/node_modules
RUN node --experimental-strip-types /app/parser/parse.ts /app/parser/parse.ts > /dev/null

RUN groupadd --gid 10001 testforge && useradd --uid 10001 --gid testforge --system --create-home testforge \
    && mkdir -p /app/workspace && chown -R testforge:testforge /app
USER testforge

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
