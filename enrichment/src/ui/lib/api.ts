import { ProductFields, AugmentedData, AIServiceHealthStatus, PolicyDocument, PolicyUploadResult, ManualKnowledge, ManualExtractResult } from '../types';

const LINGI7_API_BASE = process.env.NEXT_PUBLIC_LINGI7_API_BASE || '/api/v1';
const ENRICHMENT_BASE = `${LINGI7_API_BASE.replace(/\/$/, '')}/products/enrichment-workbench`;

function authHeaders(): HeadersInit {
  if (typeof window === 'undefined') {
    return {};
  }
  const token = window.sessionStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const error = await response.json();
    return new Error(error.detail || error.error?.message || fallback);
  } catch {
    return new Error(fallback);
  }
}

interface AnalyzeParams {
  file: File;
  locale: string;
  productData?: any;
  brandInstructions?: string;
  productId?: string;
}

export async function analyzeImage({ file, locale, productData, brandInstructions, productId }: AnalyzeParams): Promise<AugmentedData> {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('locale', locale);
  if (productId && productId.trim()) {
    formData.append('product_id', productId.trim());
  }
  if (productData) {
    formData.append('product_data', JSON.stringify(productData));
  }
  if (brandInstructions) {
    formData.append('brand_instructions', brandInstructions);
  }

  const response = await fetch(`${ENRICHMENT_BASE}/analyze/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to analyze image');
  }

  const data = await response.json();
  return {
    ...data,
    policyDecision: data.policy_decision
  };
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

export async function generateFaqs(params: GenerateFaqsParams): Promise<{ question: string; answer: string }[]> {
  const formData = new FormData();
  formData.append('title', params.title);
  formData.append('description', params.description);
  formData.append('categories', JSON.stringify(params.categories));
  formData.append('tags', JSON.stringify(params.tags));
  formData.append('colors', JSON.stringify(params.colors));
  formData.append('locale', params.locale);
  if (params.manualKnowledge) {
    formData.append('manual_knowledge', JSON.stringify(params.manualKnowledge));
  }

  const response = await fetch(`${ENRICHMENT_BASE}/faqs/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to generate FAQs');
  }

  const data = await response.json();
  return data.faqs || [];
}

export async function extractManualKnowledge(
  file: File,
  title: string,
  categories: string[],
  locale: string,
): Promise<ManualExtractResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', title);
  formData.append('categories', JSON.stringify(categories));
  formData.append('locale', locale);

  const response = await fetch(`${ENRICHMENT_BASE}/manual/extract/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to extract manual knowledge');
  }

  return response.json();
}

export async function listPolicies(): Promise<PolicyDocument[]> {
  const response = await fetch(`${ENRICHMENT_BASE}/policies/`, {
    method: 'GET',
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to load policy library');
  }

  const data = await response.json();
  return data.documents || [];
}

export async function uploadPolicies(files: File[], locale: string): Promise<{ documents: PolicyDocument[]; results: PolicyUploadResult[] }> {
  const formData = new FormData();
  formData.append('locale', locale);
  for (const file of files) {
    formData.append('files', file);
  }

  const response = await fetch(`${ENRICHMENT_BASE}/policies/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to upload policy PDFs');
  }

  return response.json();
}

export async function clearPolicies(): Promise<void> {
  const response = await fetch(`${ENRICHMENT_BASE}/policies/`, {
    method: 'DELETE',
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to clear policy library');
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
  enhancedProduct?: any;
}

export async function generateImageVariation(params: GenerateVariationParams): Promise<{ imageUrl: string | null, qualityScore: number | null, qualityIssues: string[] }> {
  const formData = new FormData();
  formData.append('image', params.file);
  formData.append('locale', params.locale);
  formData.append('title', params.title);
  formData.append('description', params.description);
  formData.append('categories', JSON.stringify(params.categories));
  formData.append('tags', JSON.stringify(params.tags));
  formData.append('colors', JSON.stringify(params.colors));
  if (params.enhancedProduct) {
    formData.append('enhanced_product', JSON.stringify(params.enhancedProduct));
  }

  const response = await fetch(`${ENRICHMENT_BASE}/generate/variation/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to generate variation');
  }

  const data = await response.json();

  return {
    imageUrl: data.generated_image_b64 ? `data:image/png;base64,${data.generated_image_b64}` : null,
    qualityScore: data.quality_score !== undefined && data.quality_score !== null ? data.quality_score : null,
    qualityIssues: data.quality_issues || []
  };
}

export async function generate3DModel(file: File): Promise<string | null> {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('return_json', 'true');

  const response = await fetch(`${ENRICHMENT_BASE}/generate/3d/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
    // Increase timeout for large responses (2 minutes)
    signal: AbortSignal.timeout(120000)
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to generate 3D model');
  }

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('Failed to parse 3D model response');
  }

  return data.glb_base64 ? `data:model/gltf-binary;base64,${data.glb_base64}` : null;
}

export function prepareProductData(fields: ProductFields) {
  const data: any = {};
  
  if (fields.title && fields.title.trim()) {
    data.title = fields.title.trim();
  }
  
  if (fields.description && fields.description.trim()) {
    data.description = fields.description.trim();
  }
  
  if (fields.categories && fields.categories.trim()) {
    const categories = fields.categories.split(',')
      .map(c => c.trim())
      .filter(c => c !== '');
    if (categories.length > 0) {
      data.categories = categories;
    }
  }
  
  if (fields.tags && fields.tags.trim()) {
    const tags = fields.tags.split(',')
      .map(t => t.trim())
      .filter(t => t !== '');
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

export async function generateProtocolSchemas(params: GenerateProtocolSchemasParams): Promise<ProtocolSchemas> {
  const formData = new FormData();
  formData.append('title', params.title);
  formData.append('description', params.description);
  formData.append('categories', JSON.stringify(params.categories));
  formData.append('tags', JSON.stringify(params.tags));
  formData.append('colors', JSON.stringify(params.colors));
  formData.append('locale', params.locale);
  if (params.faqs) {
    formData.append('faqs', JSON.stringify(params.faqs));
  }

  const response = await fetch(`${ENRICHMENT_BASE}/protocols/generate/`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw await parseError(response, 'Failed to generate protocol schemas');
  }

  return response.json();
}

export async function checkAIServiceHealth(): Promise<AIServiceHealthStatus> {
  try {
    const response = await fetch(`${ENRICHMENT_BASE}/health/services/`, {
      method: 'GET',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error('Failed to check AI service health');
    }

    return response.json();
  } catch (error) {
    console.error('Error checking AI service health:', error);
    return {
      vlm: 'unhealthy',
      llm: 'unhealthy',
      flux: 'unhealthy',
      trellis: 'unhealthy'
    };
  }
}
