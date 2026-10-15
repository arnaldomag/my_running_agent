FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Installiamo prima le dipendenze per sfruttare la layer cache di Docker
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamo solo il codice applicativo necessario in produzione
COPY app/ ./app/
COPY main.py webhook.py ./

EXPOSE 8080

# 1 worker con 8 thread (gthread): massimizza la condivisione della cache MCP in RAM
# e gestisce fino a 8 richieste HTTP concorrenti senza blocchi.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "webhook:app"]
