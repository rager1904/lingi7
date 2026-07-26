# Search Architecture

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Unified Search Flow

1. Client calls `POST /api/v1/ai/search/`.
2. Django validates request and applies throttling.
3. Django calls `catalog-retriever /query/text` for semantic search.
4. Retriever searches Milvus text/image collections.
5. Django maps retriever IDs back to approved marketplace products.
6. If retriever is unavailable or returns no product IDs, Django uses PostgreSQL keyword search over name, description, SEO fields, keywords, and tags.

## Indexing Flow

1. Vendor creates product in Django.
2. Product is enriched through Django or enrichment FastAPI.
3. Product approval or enrichment completion triggers `AssistantCatalogIndexer.index_product`.
4. Indexer writes the product into the shared assistant catalog CSV and posts to `/index/products`.
5. Catalog retriever appends product records to Milvus collections.

## Recommendation Flow

- `GET /api/v1/ai/recommendations/` uses authenticated buyer order history.
- If purchase history exists, recommendations are based on previously purchased product categories.
- If no history exists, newest visible products are returned.
- `GET /api/v1/ai/similar-products/<id>/` uses category and enrichment tags.

## Performance Targets

- Product search target: under 2 seconds with retriever healthy.
- Database fallback target: under 2 seconds for normal catalog sizes with indexed product status/category fields.
- Future improvement: replace append-only Milvus indexing with product-ID upsert/delete semantics.
