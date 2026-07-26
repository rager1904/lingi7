FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN pip install --no-cache-dir \
    fastapi uvicorn httpx \
    diffusers transformers accelerate \
    pillow

COPY docker/flux_server.py /app/server.py

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
