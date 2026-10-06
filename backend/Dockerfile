FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Migrations (avec reprise d'une base V0.2) + données de démo, puis l'API
CMD ["sh", "-c", "python -m app.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
