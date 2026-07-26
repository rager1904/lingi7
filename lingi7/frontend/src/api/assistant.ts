/**
 * Assistant API — delegates to Django /api/v1/ai/assistant/query/
 *
 * The Django view proxies to chain-server and falls back to DB search
 * when the assistant service is unavailable.
 */

import apiClient from "./client";

export interface AssistantProduct {
  name: string;
  price: string;
  image: string;
  pk: string;
}

export interface AssistantResponse {
  response: string;
  products: AssistantProduct[];
  timings: Record<string, number>;
}

interface AssistantQueryPayload {
  query: string;
  context?: string;
  image?: string;
  guardrails?: boolean;
}

export async function sendAssistantQuery(
  payload: AssistantQueryPayload
): Promise<AssistantResponse> {
  const { data } = await apiClient.post<{
    success: boolean;
    source: string;
    data: {
      response: string;
      products?: AssistantProduct[];
      timings?: Record<string, number>;
    };
  }>("ai/assistant/query/", {
    query: payload.query,
    context: payload.context ?? "",
    image: payload.image ?? "",
    guardrails: payload.guardrails ?? true,
  });

  return {
    response: data.data.response ?? "",
    products: data.data.products ?? [],
    timings: data.data.timings ?? {},
  };
}
