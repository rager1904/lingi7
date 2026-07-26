FROM python:3.11-slim

RUN pip install --no-cache-dir \
    torch --extra-index-url https://download.pytorch.org/whl/cpu \
    fastapi uvicorn \
    transformers accelerate \
    pillow

COPY docker/bge_server.py /app/server.py

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
