/**
 * Recommendations API — aligns with /api/v1/recommendations/ routes.
 */

import apiClient from "./client";

export interface RecommendationSection {
  title: string;
  subtitle: string;
  strategy: string;
  products: any[];
}

export interface EngagementStats {
  total_likes: number;
  total_views: number;
  total_ratings: number;
  total_wishlist_items: number;
  avg_rating_given: number | null;
  top_categories: string[];
  engagement_score: number;
}

export const recommendationsApi = {
  /** Toggle like on a product */
  async toggleLike(productId: number): Promise<{ liked: boolean; product_id: number }> {
    const { data } = await apiClient.post("/recommendations/like/", { product_id: productId });
    return data;
  },

  /** List all liked products */
  async listLikes(): Promise<{ results: any[]; count: number }> {
    const { data } = await apiClient.get("/recommendations/likes/");
    return data;
  },

  /** Track a product view */
  async trackView(productId: number): Promise<{ tracked: boolean; view_count: number }> {
    const { data } = await apiClient.post("/recommendations/view/", { product_id: productId });
    return data;
  },

  /** Rate a product (1-5 stars) */
  async rate(productId: number, score: number, review?: string): Promise<any> {
    const { data } = await apiClient.post("/recommendations/rate/", {
      product_id: productId,
      score,
      review: review || "",
    });
    return data;
  },

  /** List user ratings */
  async listRatings(): Promise<{ results: any[]; count: number }> {
    const { data } = await apiClient.get("/recommendations/ratings/");
    return data;
  },

  /** Add to wishlist */
  async addToWishlist(
    productId: number,
    name?: string,
    note?: string
  ): Promise<any> {
    const { data } = await apiClient.post("/recommendations/wishlist/", {
      product_id: productId,
      name: name || "My Wishlist",
      note: note || "",
    });
    return data;
  },

  /** Remove from wishlist */
  async removeFromWishlist(itemId: number): Promise<void> {
    await apiClient.delete(`/recommendations/wishlist/${itemId}/`);
  },

  /** List wishlist items */
  async listWishlist(): Promise<{ results: any[]; count: number }> {
    const { data } = await apiClient.get("/recommendations/wishlist/");
    return data;
  },

  /** Get personalised 'For You' feed */
  async getForYou(limit?: number): Promise<{ success: boolean; data: RecommendationSection[] }> {
    const { data } = await apiClient.get("/recommendations/for-you/", {
      params: { limit: limit || 20 },
    });
    return data;
  },

  /** Get trending products */
  async getTrending(limit?: number): Promise<{ success: boolean; source: string; data: any[] }> {
    const { data } = await apiClient.get("/recommendations/trending/", {
      params: { limit: limit || 20 },
    });
    return data;
  },

  /** Get similar products */
  async getSimilar(productId: number, limit?: number): Promise<{ success: boolean; source: string; data: any[] }> {
    const { data } = await apiClient.get(`/recommendations/similar/${productId}/`, {
      params: { limit: limit || 10 },
    });
    return data;
  },

  /** Get engagement stats */
  async getStats(): Promise<EngagementStats> {
    const { data } = await apiClient.get("/recommendations/stats/");
    return data;
  },
};
