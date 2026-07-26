"""
apps/recommendations/urls.py
=============================
URL routes for the per-user recommendation system.

Mounted at /api/v1/recommendations/.
"""

from django.urls import path

from . import views

app_name = "recommendations"

urlpatterns = [
    # Likes
    path("like/", views.LikeToggleView.as_view(), name="like-toggle"),
    path("likes/", views.LikesListView.as_view(), name="likes-list"),

    # View tracking
    path("view/", views.TrackProductView.as_view(), name="track-view"),

    # Ratings
    path("rate/", views.RateProductView.as_view(), name="rate-product"),
    path("ratings/", views.RatingsListView.as_view(), name="ratings-list"),

    # Wishlist
    path("wishlist/", views.WishlistListCreateView.as_view(), name="wishlist-list-create"),
    path("wishlist/<int:pk>/", views.WishlistDeleteView.as_view(), name="wishlist-delete"),

    # Recommendations
    path("for-you/", views.ForYouView.as_view(), name="for-you"),
    path("trending/", views.TrendingView.as_view(), name="trending"),
    path("similar/<int:product_id>/", views.SimilarProductsView.as_view(), name="similar-products"),
    path("stats/", views.EngagementStatsView.as_view(), name="engagement-stats"),
]
