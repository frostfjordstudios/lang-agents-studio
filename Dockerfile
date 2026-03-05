FROM python:3.10-slim

WORKDIR /app

# System deps for sqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directory exists for SQLite checkpoints
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
