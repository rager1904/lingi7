import apiClient from "./client";

export interface PlatformStatus {
  platform: string;
  api_version: string;
  authentication: {
    provider: string;
    sso_source: string;
    duplicate_login_systems: boolean;
  };
  applications: Array<{
    id: string;
    name: string;
    status: string;
    api_base: string;
    dashboard_path: string;
  }>;
  ai: {
    orchestrator: string;
    llm: string;
    catalog_llm: string;
    vlm: string;
    text_embeddings: string;
    image_embeddings: string;
    vector_database: string;
    proprietary_model_required: boolean;
  };
}

export const platformApi = {
  status: async (): Promise<PlatformStatus> => {
    const { data } = await apiClient.get<PlatformStatus>("/platform/status/");
    return data;
  },
};
