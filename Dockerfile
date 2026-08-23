FROM python:3.12-slim
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')"

COPY . .

CMD ["/bin/sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port $PORT"]
