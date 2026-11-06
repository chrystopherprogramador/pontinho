FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PONTINHO_DB=/app/data/pontinho.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
EXPOSE 5000
CMD ["sh", "-c", "python -c 'from app import init_db; init_db()' && waitress-serve --listen=0.0.0.0:5000 app:app"]
