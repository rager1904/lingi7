"""BGE text embedding server — OpenAI-compatible embeddings API.

Serves BAAI/bge-large-en-v1.5 via HuggingFace transformers.
Provides the /v1/embeddings endpoint compatible with the catalog_retriever.
"""

import logging
import os
import torch
import torch.nn.functional as F
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bge-server")

app = FastAPI()

class EmbeddingRequest(BaseModel):
    model: str = "BAAI/bge-large-en-v1.5"
    input: list | str

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list
    model: str
    usage: dict

device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = None
model = None

@app.on_event("startup")
def load():
    global tokenizer, model
    model_id = os.environ.get("BGE_MODEL_ID", "BAAI/bge-large-en-v1.5")
    logger.info(f"Loading {model_id} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id).to(device)
    model.eval()
    logger.info("BGE model loaded")

def mean_pooling(last_hidden, attention_mask):
    """Mean pooling — take attention mask into account."""
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
    return torch.sum(last_hidden * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

@app.post("/v1/embeddings")
async def embed(req: EmbeddingRequest):
    if isinstance(req.input, str):
        req.input = [req.input]

    encoded = tokenizer(req.input, padding=True, truncation=True, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**encoded)
        emb = mean_pooling(outputs.last_hidden_state, encoded["attention_mask"])
    emb = F.normalize(emb, p=2, dim=1)

    return EmbeddingResponse(
        data=[{"object": "embedding", "index": i, "embedding": emb[i].cpu().tolist()} for i in range(len(req.input))],
        model=req.model,
        usage={"prompt_tokens": 0, "total_tokens": 0},
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": model is not None}
