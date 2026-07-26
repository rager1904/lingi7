/**
 * Lingi7 API — aligned with backend /api/v1/* routes
 */

export { authApi } from "./auth";
export { productsApi } from "./products";
export { storesApi } from "./stores";
export { ordersApi } from "./orders";
export type { CreateOrderPayload } from "./orders";
export { paymentsApi } from "./payments";
export { logisticsApi, trackingApi } from "./logistics";
export { disputesApi } from "./disputes";
export { usersApi } from "./users";
export { vendorApi } from "./vendor";
export { platformApi } from "./platform";
export { sendAssistantQuery } from "./assistant";
export type { AssistantProduct, AssistantResponse } from "./assistant";
export { recommendationsApi } from "./recommendations";
export type { RecommendationSection, EngagementStats } from "./recommendations";
export { default as apiClient, TokenStorage, normaliseError } from "./client";

// Backward-compatible barrel
export { ordersApi as ordersApiLegacy } from "./orders";
export { productsApi as productsApiLegacy } from "./products";
