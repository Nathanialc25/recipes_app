
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sets $PORT. Default to 8080 if not set (for local testing).
ENV PORT=8080

# Expose the port. Purely documentation — Cloud Run doesn't need this,
EXPOSE 8080

# The command to run when the container starts.
# Exec form (JSON array) — the process runs directly, not through a shell.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app