"""
apps/users/urls.py
------------------
URL configuration for the users app.

Mounted at /api/ in config/urls.py.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminFreezeView,
    AdminKYCReviewView,
    AdminUnfreezeView,
    AdminUserDetailView,
    AdminUserListView,
    KYCSubmitView,
    LingiTokenObtainPairView,
    MeView,
    RegisterView,
)

app_name = "users"

urlpatterns = [
    # ---------------------------------------------------------------- #
    # Auth                                                              #
    # ---------------------------------------------------------------- #
    path("token/", LingiTokenObtainPairView.as_view(), name="token_obtain"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # ---------------------------------------------------------------- #
    # Registration                                                      #
    # ---------------------------------------------------------------- #
    path("register/", RegisterView.as_view(), name="user_register"),
    # ---------------------------------------------------------------- #
    # Authenticated user                                                #
    # ---------------------------------------------------------------- #
    path("me/", MeView.as_view(), name="user_me"),
    path("me/kyc/", KYCSubmitView.as_view(), name="kyc_submit"),
    # ---------------------------------------------------------------- #
    # Admin                                                             #
    # ---------------------------------------------------------------- #
    path("admin/users/", AdminUserListView.as_view(), name="admin_user_list"),
    path("admin/users/<uuid:user_id>/", AdminUserDetailView.as_view(), name="admin_user_detail"),
    path(
        "admin/users/<uuid:user_id>/kyc/review/",
        AdminKYCReviewView.as_view(),
        name="admin_kyc_review",
    ),
    path(
        "admin/users/<uuid:user_id>/freeze/",
        AdminFreezeView.as_view(),
        name="admin_freeze",
    ),
    path(
        "admin/users/<uuid:user_id>/unfreeze/",
        AdminUnfreezeView.as_view(),
        name="admin_unfreeze",
    ),
]
