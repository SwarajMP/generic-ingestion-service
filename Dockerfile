FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY sources_config sources_config

EXPOSE 8000

# $PORT is set by hosting platforms (e.g. Render); defaults to 8000 for
# docker-compose, which doesn't set it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
