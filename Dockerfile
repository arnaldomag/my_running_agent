# Usa un'immagine Python ufficiale e leggera
FROM python:3.11-slim

# Evita la creazione di file .pyc e assicura log immediati
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Copia e installa le dipendenze
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del codice
COPY . .

# Comando per avviare l'agente
CMD ["python", "main.py"]