import apiClient from "./client";
import type {
  InitiatePaymentPayload,
  PaymentAttempt,
  PaymentInitiateResponse,
  PaymentSimulateAction,
  PaymentSimulateResponse,
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

  /**
   * Sandbox-only: simulate the buyer approving/declining the USSD prompt.
   * Backend is DEBUG-gated and returns 403 in production.
   */
  simulate: async (
    paymentId: string,
    action: PaymentSimulateAction
  ): Promise<PaymentSimulateResponse> => {
    const { data } = await apiClient.post<PaymentSimulateResponse>(
      `/payments/${paymentId}/simulate/`,
      { action }
    );
    return data;
  },
};
