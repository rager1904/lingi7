"""TRELLIS 3D asset generation server — OpenAI-compatible API.

Endpoints:
  POST /v1/infer  — generate 3D GLB from image (used by enrichment backend)

Runs Microsoft TRELLIS for image-to-3D generation.
"""

import base64
import io
import json
import logging
import os
import torch
from fastapi import FastAPI, Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trellis")

app = FastAPI()

class InferRequest(BaseModel):
    image: str
    slat_cfg_scale: float = 5.0
    ss_cfg_scale: float = 10.0
    slat_sampling_steps: int = 50
    ss_sampling_steps: int = 50
    seed: int = 0
    disable_safety_checker: bool = True

device = "cuda" if torch.cuda.is_available() else "cpu"
pipeline = None

@app.on_event("startup")
def load_model():
    global pipeline
    model_id = os.environ.get("TRELLIS_MODEL_ID", "microsoft/TRELLIS-image-to-3d")
    logger.info(f"Loading {model_id} on {device}...")
    try:
        from trellis.pipelines import TrellisImageTo3DPipeline
        pipeline = TrellisImageTo3DPipeline.from_pretrained(model_id)
        pipeline.to(device)
        logger.info("TRELLIS model loaded")
    except Exception as e:
        logger.error(f"Failed to load TRELLIS: {e}")

@app.post("/v1/infer")
async def infer(req: InferRequest):
    logger.info("Generating 3D asset from image...")

    # Decode base64 image
    if req.image.startswith("data:image/"):
        _, b64data = req.image.split(",", 1)
    else:
        b64data = req.image

    image_bytes = base64.b64decode(b64data)
    from PIL import Image
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Run TRELLIS
    outputs = pipeline.run(
        pil_image,
        seed=req.seed,
        slat_cfg_scale=req.slat_cfg_scale,
        ss_cfg_scale=req.ss_cfg_scale,
        slat_sampling_steps=req.slat_sampling_steps,
        ss_sampling_steps=req.ss_sampling_steps,
    )

    # Export to GLB
    glb_path = f"/tmp/trellis_{req.seed}.glb"
    outputs["gaussian"].save(glb_path)

    with open(glb_path, "rb") as f:
        glb_bytes = f.read()

    glb_b64 = base64.b64encode(glb_bytes).decode()
    logger.info(f"Generated GLB: {len(glb_bytes)} bytes")

    return {
        "artifacts": [{"base64": glb_b64}],
        "id": f"trellis_{req.seed}",
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": pipeline is not None}
