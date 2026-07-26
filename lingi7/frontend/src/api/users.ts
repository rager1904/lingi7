import apiClient from "./client";
import type { User } from "../types";
import { mapProfileToUser } from "./auth";

export const usersApi = {
  updateProfile: async (payload: {
    first_name?: string;
    last_name?: string;
    email?: string;
  }): Promise<User> => {
    const { data } = await apiClient.patch<Record<string, unknown>>(
      "/auth/me/",
      payload
    );
    return mapProfileToUser(data);
  },
};
