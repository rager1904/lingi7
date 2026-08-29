"""
apps/users/urls.py
------------------
URL configuration for the users app.

Mounted at /api/ in config/urls.py.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from .views import (
    AdminFreezeView,
    AdminKYCReviewView,
    AdminUnfreezeView,
    AdminUserDetailView,
    AdminUserListView,
    ChangePasswordView,
    KYCSubmitView,
    KYCUploadFileView,
    LingiTokenObtainPairView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetView,
    PhoneVerifyConfirmView,
    PhoneVerifyView,
    RegisterView,
)

app_name = "users"

urlpatterns = [
    # ---------------------------------------------------------------- #
    # Auth                                                              #
    # ---------------------------------------------------------------- #
    path("token/", LingiTokenObtainPairView.as_view(), name="token_obtain"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/blacklist/", TokenBlacklistView.as_view(), name="token_blacklist"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    # ---------------------------------------------------------------- #
    # Phone verification                                                #
    # ---------------------------------------------------------------- #
    path("verify-phone/", PhoneVerifyView.as_view(), name="verify_phone"),
    path(
        "verify-phone/confirm/",
        PhoneVerifyConfirmView.as_view(),
        name="verify_phone_confirm",
    ),
    # ---------------------------------------------------------------- #
    # Password reset                                                    #
    # ---------------------------------------------------------------- #
    path("password/reset/", PasswordResetView.as_view(), name="password_reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    # ---------------------------------------------------------------- #
    # Registration                                                      #
    # ---------------------------------------------------------------- #
    path("register/", RegisterView.as_view(), name="user_register"),
    # ---------------------------------------------------------------- #
    # Authenticated user                                                #
    # ---------------------------------------------------------------- #
    path("me/", MeView.as_view(), name="user_me"),
    path("me/kyc/", KYCSubmitView.as_view(), name="kyc_submit"),
    # Dev-friendly: accept multipart file uploads (no S3/R2 presigned flow)
    path("kyc/upload/", KYCUploadFileView.as_view(), name="kyc_upload_files"),
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
