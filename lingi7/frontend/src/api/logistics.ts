import apiClient from "./client";
import { mapApiShipment } from "./logisticsMappers";
import type { Shipment } from "../types";

export const logisticsApi = {
  /** Public — GET /api/v1/logistics/track/{token}/ */
  trackByToken: async (token: string): Promise<Shipment> => {
    const { data } = await apiClient.get<unknown>(`/logistics/track/${token}/`);
    return mapApiShipment(data as Parameters<typeof mapApiShipment>[0]);
  },
};

/** @deprecated Use logisticsApi.trackByToken */
export const trackingApi = {
  byToken: (token: string) => logisticsApi.trackByToken(token),
};
