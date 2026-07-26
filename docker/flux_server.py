"""FLUX.1 image generation server — OpenAI-compatible API.

Endpoints:
  POST /v1/infer  — generate image variation (used by enrichment backend)

Runs FLUX.1-schnell via HuggingFace diffusers.
"""

import base64
import io
import logging
import os
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from diffusers import FluxPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("flux")

app = FastAPI()

class InferRequest(BaseModel):
    prompt: str
    image: str = ""
    aspect_ratio: str = "match_input_image"
    disable_safety_checker: int = 1
    steps: int = 30
    cfg_scale: float = 3.5
    seed: int = 0

device = "cuda" if torch.cuda.is_available() else "cpu"
pipe = None

@app.on_event("startup")
def load_model():
    global pipe
    model_id = os.environ.get("FLUX_MODEL_ID", "black-forest-labs/FLUX.1-schnell")
    logger.info(f"Loading {model_id} on {device}...")
    pipe = FluxPipeline.from_pretrained(model_id, torch_dtype=torch.bfloat16)
    pipe.to(device)
    pipe.enable_model_cpu_offload()
    logger.info("FLUX model loaded")

@app.post("/v1/infer")
async def infer(req: InferRequest):
    logger.info(f"Generating: prompt={req.prompt[:60]}... steps={req.steps}")
    generator = torch.Generator(device="cpu").manual_seed(req.seed)
    image = pipe(
        prompt=req.prompt,
        num_inference_steps=req.steps,
        guidance_scale=req.cfg_scale,
        generator=generator,
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    logger.info(f"Generated image: {len(b64)} base64 chars")
    return {"image": b64}

@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": pipe is not None}
