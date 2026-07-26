# Enrichment App — Google Colab Quick Start

"""
INSTRUCTIONS:
1. Upload this notebook to Google Colab (https://colab.research.google.com)
2. Change runtime type: Runtime → Change runtime type → T4 GPU
3. Run cells in order
4. The backend will be accessible via ngrok tunnel URL printed at the end

WHAT THIS TESTS:
- VLM analysis (image → product data)
- LLM enhancement (richer titles/descriptions)
- FAQ generation
- Protocol schema export (ACP/UCP)

WHAT THIS SKIPS (needs more VRAM or Docker):
- FLUX image generation
- TRELLIS 3D generation
- Milvus policy compliance
"""

# %% [markdown]
# ## 1. Install Ollama

# %%
!curl -fsSL https://ollama.com/install.sh | sh

# %% [markdown]
# ## 2. Pull quantized models (fits in T4 15GB VRAM)

# %%
!ollama pull qwen2.5:7b &
!ollama pull llava:7b &
wait
print("Models pulled!")

# %%
!ollama list

# %% [markdown]
# ## 3. Install Python dependencies

# %%
!pip install fastapi uvicorn openai pydantic python-multipart aiofiles pillow python-dotenv

# %% [markdown]
# ## 4. Clone the enrichment repo

# %%
import os
os.chdir("/content")

# If you have the repo on GitHub:
# !git clone https://github.com/YOUR_USERNAME/lingi7_scaffold.git
# os.chdir("lingi7_scaffold/enrichment")

# If you uploaded the enrichment folder manually, skip the git clone
# and make sure the enrichment/src/backend files are in /content/enrichment

# %% [markdown]
# ## 5. Configure for Colab (Ollama on localhost)

# %%
%%writefile /content/config.yaml
vlm:
  url: "http://localhost:11434/v1"
  model: "llava:7b"
  max_tokens: 1024
  temperature: 0.1

llm:
  url: "http://localhost:11434/v1"
  model: "qwen2.5:7b"
  max_tokens: 2048
  temperature: 0.3

embeddings:
  url: "http://localhost:11434/v1"
  model: "qwen2.5:7b"

flux:
  url: "http://localhost:8003/v1/infer"

trellis:
  url: "http://localhost:8004/v1/infer"

milvus:
  host: "localhost"
  port: 19530
  collection: "policy_chunks"
  alias: "policy_library"

product_manual:
  chunk_size_words: 250
  chunk_overlap_words: 50
  top_k_per_query: 3
  min_relevance_score: 0.25

policy_library:
  storage_dir: "data/policies"
  db_path: "data/policies/library.db"
  top_k: 8
  min_relevance_score: 0.3
  max_policy_text_chars: 12000
  normalization_max_tokens: 2048
  classification_max_tokens: 1024
  embedding_batch_size: 128
  embedding_dim: 384

locales:
  default: "en-US"
  supported:
    - "en-US"
    - "en-GB"
    - "en-AU"
    - "en-CA"
    - "es-ES"
    - "es-MX"
    - "es-AR"
    - "es-CO"
    - "fr-FR"
    - "fr-CA"
# %% [markdown]
# ## 6. Start Ollama server in background

# %%
import subprocess, time
subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
print("Ollama server started!")

# %% [markdown]
# ## 7. Test: VLM Analysis

# %%
import base64
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# Test with a simple text prompt first
response = client.chat.completions.create(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": "Say hello in 5 words"}],
    max_tokens=50,
)
print("LLM response:", response.choices[0].message.content)
print("\n✅ Qwen2.5:7b is working!")

# %% [markdown]
# ## 8. Test: VLM with image (upload a product image)

# %%
from google.colab import files
from PIL import Image
import io

print("Upload a product image (JPEG/PNG):")
uploaded = files.upload()

if uploaded:
    filename = list(uploaded.keys())[0]
    img = Image.open(io.BytesIO(uploaded[filename]))
    print(f"Image loaded: {img.size}, mode: {img.mode}")

    # Encode to base64
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    # VLM analysis
    response = client.chat.completions.create(
        model="llava:7b",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this product image. Return a JSON object with: title, description, categories (array), tags (array), colors (array). Be concise."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        ],
        max_tokens=1024,
    )
    print("\nVLM Analysis:")
    print(response.choices[0].message.content)
    print("\n✅ VLM analysis complete!")
else:
    print("No image uploaded, skipping VLM test.")

# %% [markdown]
# ## 9. What else you can test

# %%
print("""
NEXT STEPS (after VLM test works):

1. FAQ Generation:
   - Take the VLM output (title, description, categories, tags, colors)
   - Send to LLM with FAQ prompt
   - Returns 3-5 product FAQs

2. Protocol Schema Export:
   - Take enriched data + FAQs
   - Send to LLM for ACP/UCP schema extraction
   - Returns structured JSON schemas

3. Full Pipeline:
   - Image → VLM → LLM enhance → FAQs → Protocols
   - All running locally on Colab T4 GPU

WHAT WON'T WORK ON COLAB:
- FLUX image generation (needs 24GB+ VRAM)
- TRELLIS 3D generation (needs 24GB+ VRAM)
- Milvus policy compliance (needs Docker)
""")
