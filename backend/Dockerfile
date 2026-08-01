FROM node:22-bookworm-slim AS parser-runtime

WORKDIR /app/parser
COPY parser/package*.json ./
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
COPY --from=parser-runtime /app/parser/node_modules /app/parser/node_modules
RUN node --experimental-strip-types /app/parser/parse.ts /app/parser/parse.ts > /dev/null

RUN addgroup --system testforge && adduser --system --ingroup testforge testforge \
    && mkdir -p /app/workspace && chown -R testforge:testforge /app
USER testforge

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
