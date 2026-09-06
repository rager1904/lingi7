/**
 * Catalog enrichment workbench API.
 *
 * Uses the shared authenticated `apiClient` (JWT injection + silent refresh),
 * hitting the Django gateway at `/api/v1/products/enrichment-workbench/*`.
 * The Django gateway proxies to the internal enrichment FastAPI service,
 * verifies vendor product ownership, persists results, and triggers assistant
 * indexing — so all backend logic runs exactly as the standalone UI did.
 */

import apiClient from "./client";
import type {
  AIServiceHealthStatus,
  AugmentedData,
  ManualExtractResult,
  ManualKnowledge,
  PolicyDecision,
  PolicyDocument,
  PolicyUploadResult,
  ProductFields,
} from "../types/enrichment";

const ENRICHMENT_BASE = "/products/enrichment-workbench";

function parseErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message) || fallback;
  }
  return fallback;
}

interface AnalyzeParams {
  file: File;
  locale: string;
  productData?: Record<string, unknown> | null;
  brandInstructions?: string;
  productId?: string;
}

export async function analyzeImage({
  file,
  locale,
  productData,
  brandInstructions,
  productId,
}: AnalyzeParams): Promise<AugmentedData> {
  const formData = new FormData();
  formData.append("image", file);
  formData.append("locale", locale);
  if (productId && productId.trim()) {
    formData.append("product_id", productId.trim());
  }
  if (productData) {
    formData.append("product_data", JSON.stringify(productData));
  }
  if (brandInstructions) {
    formData.append("brand_instructions", brandInstructions);
  }

  try {
    const { data } = await apiClient.post<
      AugmentedData & { policy_decision?: PolicyDecision }
    >(`${ENRICHMENT_BASE}/analyze/`, formData);
    return {
      title: data.title ?? "",
      description: data.description ?? "",
      colors: data.colors ?? [],
      tags: data.tags ?? [],
      categories: data.categories,
      policyDecision: data.policy_decision,
    };
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to analyze image"));
  }
}

interface GenerateFaqsParams {
  title: string;
  description: string;
  categories: string[];
  tags: string[];
  colors: string[];
  locale: string;
  manualKnowledge?: ManualKnowledge;
}

export async function generateFaqs(
  params: GenerateFaqsParams
): Promise<{ question: string; answer: string }[]> {
  const formData = new FormData();
  formData.append("title", params.title);
  formData.append("description", params.description);
  formData.append("categories", JSON.stringify(params.categories));
  formData.append("tags", JSON.stringify(params.tags));
  formData.append("colors", JSON.stringify(params.colors));
  formData.append("locale", params.locale);
  if (params.manualKnowledge) {
    formData.append("manual_knowledge", JSON.stringify(params.manualKnowledge));
  }

  try {
    const { data } = await apiClient.post<{ faqs?: { question: string; answer: string }[] }>(
      `${ENRICHMENT_BASE}/faqs/`,
      formData
    );
    return data.faqs || [];
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to generate FAQs"));
  }
}

export async function extractManualKnowledge(
  file: File,
  title: string,
  categories: string[],
  locale: string
): Promise<ManualExtractResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  formData.append("categories", JSON.stringify(categories));
  formData.append("locale", locale);

  try {
    const { data } = await apiClient.post<ManualExtractResult>(
      `${ENRICHMENT_BASE}/manual/extract/`,
      formData
    );
    return data;
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to extract manual knowledge"));
  }
}

export async function listPolicies(): Promise<PolicyDocument[]> {
  try {
    const { data } = await apiClient.get<{ documents?: PolicyDocument[] }>(
      `${ENRICHMENT_BASE}/policies/`
    );
    return data.documents || [];
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to load policy library"));
  }
}

export async function uploadPolicies(
  files: File[],
  locale: string
): Promise<{ documents: PolicyDocument[]; results: PolicyUploadResult[] }> {
  const formData = new FormData();
  formData.append("locale", locale);
  for (const file of files) {
    formData.append("files", file);
  }

  try {
    const { data } = await apiClient.post<{
      documents: PolicyDocument[];
      results: PolicyUploadResult[];
    }>(`${ENRICHMENT_BASE}/policies/`, formData);
    return data;
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to upload policy PDFs"));
  }
}

export async function clearPolicies(): Promise<void> {
  try {
    await apiClient.delete(`${ENRICHMENT_BASE}/policies/`);
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to clear policy library"));
  }
}

interface GenerateVariationParams {
  file: File;
  locale: string;
  title: string;
  description: string;
  categories: string[];
  tags: string[];
  colors: string[];
  enhancedProduct?: unknown;
}

export async function generateImageVariation(
  params: GenerateVariationParams
): Promise<{ imageUrl: string | null; qualityScore: number | null; qualityIssues: string[] }> {
  const formData = new FormData();
  formData.append("image", params.file);
  formData.append("locale", params.locale);
  formData.append("title", params.title);
  formData.append("description", params.description);
  formData.append("categories", JSON.stringify(params.categories));
  formData.append("tags", JSON.stringify(params.tags));
  formData.append("colors", JSON.stringify(params.colors));
  if (params.enhancedProduct) {
    formData.append("enhanced_product", JSON.stringify(params.enhancedProduct));
  }

  try {
    const { data } = await apiClient.post<{
      generated_image_b64?: string | null;
      quality_score?: number | null;
      quality_issues?: string[];
    }>(`${ENRICHMENT_BASE}/generate/variation/`, formData);

    return {
      imageUrl: data.generated_image_b64
        ? `data:image/png;base64,${data.generated_image_b64}`
        : null,
      qualityScore:
        data.quality_score !== undefined && data.quality_score !== null
          ? data.quality_score
          : null,
      qualityIssues: data.quality_issues || [],
    };
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to generate variation"));
  }
}

export async function generate3DModel(file: File): Promise<string | null> {
  const formData = new FormData();
  formData.append("image", file);
  formData.append("return_json", "true");

  try {
    const { data } = await apiClient.post<{ glb_base64?: string | null }>(
      `${ENRICHMENT_BASE}/generate/3d/`,
      formData,
      { timeout: 120_000 }
    );
    return data.glb_base64 ? `data:model/gltf-binary;base64,${data.glb_base64}` : null;
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to generate 3D model"));
  }
}

export function prepareProductData(fields: ProductFields): Record<string, unknown> | null {
  const data: Record<string, unknown> = {};

  if (fields.title && fields.title.trim()) {
    data.title = fields.title.trim();
  }

  if (fields.description && fields.description.trim()) {
    data.description = fields.description.trim();
  }

  if (fields.categories && fields.categories.trim()) {
    const categories = fields.categories
      .split(",")
      .map((c) => c.trim())
      .filter((c) => c !== "");
    if (categories.length > 0) {
      data.categories = categories;
    }
  }

  if (fields.tags && fields.tags.trim()) {
    const tags = fields.tags
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t !== "");
    if (tags.length > 0) {
      data.tags = tags;
    }
  }

  if (fields.price && fields.price.trim()) {
    const price = parseFloat(fields.price);
    if (!isNaN(price)) {
      data.price = price;
    }
  }

  return Object.keys(data).length > 0 ? data : null;
}

interface GenerateProtocolSchemasParams {
  title: string;
  description: string;
  categories: string[];
  tags: string[];
  colors: string[];
  faqs?: { question: string; answer: string }[];
  locale: string;
}

export interface ProtocolSchemas {
  acp: object;
  ucp: object;
}

export async function generateProtocolSchemas(
  params: GenerateProtocolSchemasParams
): Promise<ProtocolSchemas> {
  const formData = new FormData();
  formData.append("title", params.title);
  formData.append("description", params.description);
  formData.append("categories", JSON.stringify(params.categories));
  formData.append("tags", JSON.stringify(params.tags));
  formData.append("colors", JSON.stringify(params.colors));
  formData.append("locale", params.locale);
  if (params.faqs) {
    formData.append("faqs", JSON.stringify(params.faqs));
  }

  try {
    const { data } = await apiClient.post<ProtocolSchemas>(
      `${ENRICHMENT_BASE}/protocols/generate/`,
      formData
    );
    return data;
  } catch (err) {
    throw new Error(parseErrorMessage(err, "Failed to generate protocol schemas"));
  }
}

export async function checkAIServiceHealth(): Promise<AIServiceHealthStatus> {
  try {
    const { data } = await apiClient.get<AIServiceHealthStatus>(
      `${ENRICHMENT_BASE}/health/services/`
    );
    return data;
  } catch (err) {
    console.error("Error checking AI service health:", err);
    return {
      vlm: "unhealthy",
      llm: "unhealthy",
      flux: "unhealthy",
      trellis: "unhealthy",
    };
  }
}