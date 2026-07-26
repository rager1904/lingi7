# Docker Deployment Guide

This guide explains how to deploy the Catalog Enrichment application using Docker and Docker Compose.

## Architecture

The application consists of the following services:

- **Frontend** (Port 3000): Next.js UI for product catalog enrichment
- **Backend** (Port 8000): FastAPI backend for orchestrating enrichment workflows
- **Ollama VLM** (Port 8001): Vision-Language Model for image analysis (LLaVA)
- **Ollama LLM** (Port 8002): Large Language Model for text generation (Qwen2.5)
- **Flux** (Port 8003): Image generation model for product variations
- **Trellis** (Port 8004): 3D asset generation model
- **Embeddings Server** (Port 8005): BGE-small-en-v1.5 embeddings for policy compliance
- **Milvus Stack** (Ports 19530, 9091, 9001): Persistent vector search for loaded policy PDFs

## Prerequisites

- Docker 24.0+ with Docker Compose
- Python 3.11+ (for local development)
- HuggingFace Token (for Flux model, optional)
- 512GB disk space

## Setup

### 1. Environment Variables

Create a `.env` file in the project root:

```bash
# Ollama API Key (use any value or 'ollama' for local)
API_KEY=ollama

# HuggingFace Token (required for Flux image generation)
HF_TOKEN=your_huggingface_token_here
```

### 2. Create Shared Docker Network

```bash
docker network create catalog-network || true
```

## Running the Application

### Start All Services

```bash
docker-compose up -d
docker compose -f docker-compose.rag.yml up -d
```

### Start Specific Services

```bash
# Start only backend and frontend (without AI models)
docker-compose up -d backend frontend

# Start specific Ollama models
docker-compose up -d ollama-vlm ollama-llm

# Start all services
docker-compose up -d

# Start the persistent policy RAG stack
docker compose -f docker-compose.rag.yml up -d
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker compose -f docker-compose.rag.yml logs -f milvus-standalone
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
docker compose -f docker-compose.rag.yml down -v
```

## Building Images

### Build Backend

```bash
docker build -f src/backend/Dockerfile -t catalog-enrichment-backend .
```

### Build Frontend

```bash
docker build -f src/ui/Dockerfile -t catalog-enrichment-frontend ./src/ui
```

### Rebuild All Services

```bash
docker-compose build
docker-compose up -d
```

## Accessing the Application

Once all services are running:

- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Health Check**: http://localhost:8000/health
- **Milvus gRPC**: localhost:19530
- **Milvus health**: localhost:9091
- **MinIO Console**: http://localhost:9001

## Troubleshooting

### Check Service Status

```bash
docker-compose ps
```

### Inspect Service Logs

```bash
docker-compose logs backend
docker-compose logs ollama-vlm
docker compose -f docker-compose.rag.yml logs milvus-standalone
```

### Restart a Service

```bash
docker-compose restart backend
```

### Remove and Rebuild

```bash
docker-compose down
docker-compose build --no-cache backend
docker-compose up -d
```

## Cleanup

### Remove All Containers and Images

```bash
docker-compose down --rmi all
docker compose -f docker-compose.rag.yml down -v
```

### Clean Up Ollama Models

```bash
docker volume rm enrichment_ollama-vlm-data enrichment_ollama-llm-data
```
