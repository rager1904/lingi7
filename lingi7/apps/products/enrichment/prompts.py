"""Prompt templates for catalog enrichment LLM calls."""

SYSTEM_PROMPT = (
    "You are a retail catalog assistant for Lingi7, a Zambian e-commerce marketplace. "
    "Respond with valid JSON only — no markdown fences or extra commentary."
)

DESCRIPTION_PROMPT = """Enhance this product listing for an online store in Zambia.

Product name: {name}
Category: {category}
Condition: {condition}
Current description: {description}
Price (ZMW): {price}

Return JSON with these keys:
- "enhanced_title": string (max 200 chars, clear and buyer-friendly)
- "description_en": string (2-4 sentences, professional, mentions key benefits)
- "description_fr": string (French translation of description_en)
- "description_sw": string (Swahili translation of description_en)
- "features": list of 3-6 short feature strings
- "specs": object with relevant key-value specs (strings)
- "meta_title": string (max 60 chars, SEO-friendly)
- "meta_description": string (max 155 chars, SEO-friendly)
- "search_keywords": list of 5-10 lowercase search terms
- "tags": list of 3-8 short tag strings
"""

CATEGORY_PROMPT = """Suggest the best category for this product from the list below.

Product name: {name}
Description: {description}

Available categories (id: name):
{categories}

Return JSON with:
- "category_id": integer id from the list, or null if none fit
- "confidence": float 0-1
- "reason": short string explaining the choice
"""

VISION_PROMPT = """Describe this product image for a catalog listing.

Product name: {name}

Return JSON with:
- "visible_features": list of visible product attributes
- "suggested_alt_text": string (max 200 chars, accessibility-friendly)
- "quality_notes": list of any issues (blur, poor lighting, clutter) or empty list
"""
