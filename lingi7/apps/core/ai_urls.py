"""
Unified AI API routes.

The endpoints in this module expose search, recommendations, similar products,
and assistant access under /api/v1/ai/.
"""

from django.urls import path

from . import ai_views

urlpatterns = [
    path("search/", ai_views.SemanticProductSearchView.as_view(), name="ai-search"),
    path(
        "recommendations/",
        ai_views.ProductRecommendationView.as_view(),
        name="ai-recommendations",
    ),
    path(
        "similar-products/<int:product_id>/",
        ai_views.SimilarProductView.as_view(),
        name="ai-similar-products",
    ),
    path("assistant/query/", ai_views.AssistantQueryView.as_view(), name="ai-assistant-query"),
]
