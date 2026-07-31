FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY app /app/app

RUN addgroup --system testforge && adduser --system --ingroup testforge testforge \
    && mkdir -p /app/workspace && chown -R testforge:testforge /app
USER testforge

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
