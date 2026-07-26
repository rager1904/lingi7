import apiClient from "./client";
import type {
  InitiatePaymentPayload,
  PaymentAttempt,
  PaymentInitiateResponse,
} from "../types";

export const paymentsApi = {
  initiate: async (
    payload: InitiatePaymentPayload
  ): Promise<PaymentInitiateResponse> => {
    const { data } = await apiClient.post<PaymentInitiateResponse>(
      "/payments/initiate/",
      payload
    );
    return data;
  },

  pollStatus: async (paymentId: string): Promise<PaymentAttempt> => {
    const { data } = await apiClient.get<PaymentAttempt>(
      `/payments/${paymentId}/status/`
    );
    return data;
  },
};
