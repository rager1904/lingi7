"""CLIP image embedding server — OpenAI-compatible embeddings API.

Serves openai/clip-vit-large-patch14 via HuggingFace transformers.
Provides the /v1/embeddings endpoint compatible with the catalog_retriever.
"""

import base64
import io
import logging
import os
import torch
import torch.nn.functional as F
from fastapi import FastAPI
from pydantic import BaseModel
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clip-server")

app = FastAPI()

class EmbeddingRequest(BaseModel):
    model: str = "openai/clip-vit-large-patch14"
    input: list | str

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list
    model: str
    usage: dict

device = "cuda" if torch.cuda.is_available() else "cpu"
processor = None
model = None

@app.on_event("startup")
def load():
    global processor, model
    from transformers import CLIPProcessor, CLIPModel
    model_id = os.environ.get("CLIP_MODEL_ID", "openai/clip-vit-large-patch14")
    logger.info(f"Loading {model_id} on {device}...")
    processor = CLIPProcessor.from_pretrained(model_id)
    model = CLIPModel.from_pretrained(model_id).to(device)
    model.eval()
    logger.info("CLIP model loaded")

@app.post("/v1/embeddings")
async def embed(req: EmbeddingRequest):
    if isinstance(req.input, str):
        req.input = [req.input]

    embeddings = []
    for item in req.input:
        # Handle image input (base64)
        if isinstance(item, str) and (item.startswith("data:image/") or len(item) > 1000):
            if item.startswith("data:image/"):
                _, b64data = item.split(",", 1)
            else:
                b64data = item
            img_bytes = base64.b64decode(b64data)
            pil_image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            inputs = processor(images=pil_image, return_tensors="pt").to(device)
            with torch.no_grad():
                emb = model.get_image_features(**inputs)
        else:
            # Text input
            inputs = processor(text=item, return_tensors="pt", padding=True).to(device)
            with torch.no_grad():
                emb = model.get_text_features(**inputs)

        emb = F.normalize(emb, p=2, dim=1)
        embeddings.append(emb[0].cpu().tolist())

    return EmbeddingResponse(
        data=[{"object": "embedding", "index": i, "embedding": e} for i, e in enumerate(embeddings)],
        model=req.model,
        usage={"prompt_tokens": 0, "total_tokens": 0},
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": model is not None}
