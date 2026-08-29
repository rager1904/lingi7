"""
apps/users/views.py
-------------------
Thin DRF views for the users app. Zero business logic lives here.

All logic is delegated to UserService.
Views are responsible for:
  - Deserialising and validating input (via serializers)
  - Calling the appropriate service method
  - Serialising and returning output
  - Mapping service exceptions to HTTP error responses

Endpoint overview:
  POST   /api/users/register/          → RegisterView
  POST   /api/auth/token/              → LingiTokenObtainPairView (JWT)
  POST   /api/auth/token/refresh/      → TokenRefreshView (simplejwt)
  GET    /api/users/me/                → MeView
  PATCH  /api/users/me/                → MeView
  POST   /api/users/me/kyc/            → KYCSubmitView
  GET    /api/admin/users/             → AdminUserListView
  GET    /api/admin/users/{id}/        → AdminUserDetailView
  POST   /api/admin/users/{id}/kyc/review/  → AdminKYCReviewView
  POST   /api/admin/users/{id}/freeze/ → AdminFreezeView
  POST   /api/admin/users/{id}/unfreeze/ → AdminUnfreezeView
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User, VerificationPurpose
from .permissions import IsAdmin, IsKYCVerified, IsNotFrozen
from .serializers import (
    ChangePasswordSerializer as ChangePasswordInputSerializer,
    KYCReviewSerializer as AdminKYCReviewSerializer,
    AdminUserDetailSerializer,
    KYCUploadSerializer,
    LingiTokenObtainPairSerializer,
    OtpConfirmSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    PhoneVerifySerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)
from .services import (
    AccountFrozenError,
    ConsentNotGivenError,
    DuplicateNRCError,
    DuplicatePhoneError,
    InvalidKYCTransitionError,
    UserService,
    VerificationService,
)

logger = logging.getLogger(__name__)

# Shared service instance — stateless, safe to share.
_user_service = UserService()


def _service_error_to_drf(exc: Exception) -> Response:
    """
    Map known UserService exceptions to appropriate DRF error responses.

    Args:
        exc: A UserServiceError subclass instance.

    Returns:
        DRF Response with the correct HTTP status code and error body.
    """
    mapping = {
        ConsentNotGivenError: (status.HTTP_400_BAD_REQUEST, "consent_required"),
        DuplicatePhoneError: (status.HTTP_409_CONFLICT, "duplicate_phone"),
        DuplicateNRCError: (status.HTTP_409_CONFLICT, "duplicate_nrc"),
        InvalidKYCTransitionError: (status.HTTP_409_CONFLICT, "invalid_kyc_transition"),
        AccountFrozenError: (status.HTTP_403_FORBIDDEN, "account_frozen"),
    }
    for exc_class, (http_status, code) in mapping.items():
        if isinstance(exc, exc_class):
            return Response(
                {"detail": str(exc), "code": code},
                status=http_status,
            )
    # Unexpected error — re-raise so DRF's exception handler logs it
    raise exc


# ------------------------------------------------------------------ #
# Auth views                                                          #
# ------------------------------------------------------------------ #


class LingiTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/token/

    Customised JWT token endpoint. Uses LingiTokenObtainPairSerializer
    to embed role, kyc_status, and is_frozen into the token payload.
    Also blocks frozen accounts at issuance.
    """

    serializer_class = LingiTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


# ------------------------------------------------------------------ #
# Registration                                                        #
# ------------------------------------------------------------------ #


class RegisterView(APIView):
    """
    POST /api/users/register/

    Open endpoint — no authentication required.
    Creates a new BUYER or VENDOR account.
    """

    permission_classes = []  # Public endpoint
    throttle_scope = "registration"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = _user_service.register(
                phone_number=data["phone_number"],
                password=data["password"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                role=data["role"],
                email=data.get("email", ""),
                consent_given=data["consent_given"],
            )
        except (ConsentNotGivenError, DuplicatePhoneError) as exc:
            return _service_error_to_drf(exc)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict)

        return Response(
            {
                "detail": "Registration successful. Please verify your phone number.",
                "user_id": str(result.user.id),
            },
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------ #
# Authenticated user — /me/                                           #
# ------------------------------------------------------------------ #


class MeView(APIView):
    """
    GET  /api/users/me/    → return authenticated user profile
    PATCH /api/users/me/   → update safe fields (name, email)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request: Request) -> Response:
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserProfileSerializer(request.user).data)


# ------------------------------------------------------------------ #
# KYC submission                                                      #
# ------------------------------------------------------------------ #


class KYCSubmitView(APIView):
    """
    POST /api/users/me/kyc/

    Submit KYC documents. The user must already have uploaded NRC images
    and selfie to S3/R2 and received object keys from the presigned URL
    endpoint. Only those keys are passed here.

    Allowed from: UNVERIFIED or REJECTED states.
    Transitions to: PENDING.
    """

    permission_classes = [IsAuthenticated, IsNotFrozen]

    def post(self, request: Request) -> Response:
        serializer = KYCUploadSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user_id = str(request.user.id)
        try:
            user = _user_service.kyc_submit(
                user_id=user_id,
                nrc_number=data["nrc_number"],
                physical_address=data["physical_address"],
                province=data["province"],
                nrc_front_key=data["nrc_front_key"],
                nrc_back_key=data["nrc_back_key"],
                selfie_key=data["selfie_key"],
            )
        except (DuplicateNRCError, InvalidKYCTransitionError, AccountFrozenError) as exc:
            return _service_error_to_drf(exc)
        except User.DoesNotExist:
            logger.warning("kyc.submit.user_not_found", extra={"user_id": user_id})
            return Response(
                {"detail": "User not found.", "code": "user_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:  # unexpected errors
            # Log full traceback for debugging; return a safe 500 to client
            logger.exception("kyc.submit.unexpected_error", extra={"user_id": user_id})
            return Response(
                {"detail": "Request could not be completed.", "code": "server_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "detail": "KYC documents submitted successfully. Review typically takes 1-2 business days.",
                "kyc_status": user.kyc_status,
            },
            status=status.HTTP_200_OK,
        )


class KYCUploadFileView(APIView):
    """
    POST /api/v1/auth/kyc/upload/

    Dev-friendly KYC upload endpoint that accepts multipart form-data with
    binary images and stores them in Django's default storage (local FS in dev).

    This bridges the frontend implementation (direct file upload) with the
    backend KYC service layer (which stores object keys).
    """

    permission_classes = [IsAuthenticated, IsNotFrozen]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        # Expect binary files
        nrc_front = request.FILES.get("nrc_front")
        nrc_back = request.FILES.get("nrc_back")
        selfie = request.FILES.get("selfie")

        if not nrc_front or not nrc_back or not selfie:
            raise DRFValidationError(
                {
                    "detail": "Missing required files. Provide nrc_front, nrc_back, and selfie.",
                }
            )

        from apps.core.upload_validators import (
            KYC_EXTENSIONS,
            MAX_KYC_BYTES,
            validate_upload_file,
        )

        for label, f in (
            ("nrc_front", nrc_front),
            ("nrc_back", nrc_back),
            ("selfie", selfie),
        ):
            validate_upload_file(
                f,
                allowed_extensions=KYC_EXTENSIONS,
                max_bytes=MAX_KYC_BYTES,
                label=label,
            )

        # Expect required KYC text fields
        payload = {
            "nrc_number": request.data.get("nrc_number", ""),
            "physical_address": request.data.get("physical_address", ""),
            "province": request.data.get("province", ""),
        }
        ser = KYCUploadSerializer(data=payload, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # Save files and generate storage keys
        user_id = str(request.user.id)
        base = os.path.join("kyc", user_id)

        def _save(file_obj, suffix: str) -> str:
            ext = os.path.splitext(getattr(file_obj, "name", ""))[1] or ".jpg"
            name = f"{suffix}_{uuid4().hex}{ext}"
            key = os.path.join(base, name).replace("\\", "/")
            return default_storage.save(key, file_obj)

        nrc_front_key = _save(nrc_front, "nrc_front")
        nrc_back_key = _save(nrc_back, "nrc_back")
        selfie_key = _save(selfie, "selfie")
        try:
            user = _user_service.kyc_submit(
                user_id=user_id,
                nrc_number=data["nrc_number"],
                physical_address=data["physical_address"],
                province=data["province"],
                nrc_front_key=nrc_front_key,
                nrc_back_key=nrc_back_key,
                selfie_key=selfie_key,
            )
        except (DuplicateNRCError, InvalidKYCTransitionError, AccountFrozenError) as exc:
            return _service_error_to_drf(exc)
        except User.DoesNotExist:
            logger.warning("kyc.upload_file.user_not_found", extra={"user_id": user_id})
            return Response(
                {"detail": "User not found.", "code": "user_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("kyc.upload_file.failed", extra={"user_id": user_id})
            return Response(
                {"detail": "Request could not be completed.", "code": "server_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "detail": "KYC documents submitted successfully. Review typically takes 1-2 business days.",
                "kyc_status": user.kyc_status,
            },
            status=status.HTTP_200_OK,
        )


# ------------------------------------------------------------------ #
# Admin views                                                         #
# ------------------------------------------------------------------ #


class AdminUserListView(APIView):
    """
    GET /api/admin/users/

    List all users with optional kyc_status and role filters.
    Admin only.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request: Request) -> Response:
        qs = User.objects.select_related("kyc_reviewed_by").order_by("-date_joined")

        kyc_status = request.query_params.get("kyc_status")
        role = request.query_params.get("role")
        is_frozen = request.query_params.get("is_frozen")

        if kyc_status:
            qs = qs.filter(kyc_status=kyc_status)
        if role:
            qs = qs.filter(role=role)
        if is_frozen is not None:
            qs = qs.filter(is_frozen=is_frozen.lower() == "true")

        serializer = AdminUserDetailSerializer(qs, many=True)
        return Response(serializer.data)


class AdminUserDetailView(APIView):
    """
    GET /api/admin/users/{id}/

    Retrieve full admin-level user detail including KYC metadata.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request: Request, user_id: str) -> Response:
        try:
            user = User.objects.select_related("kyc_reviewed_by").get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(AdminUserDetailSerializer(user).data)


class AdminKYCReviewView(APIView):
    """
    POST /api/admin/users/{id}/kyc/review/

    Approve or reject a pending KYC submission.
    Body: {"action": "approve"} or {"action": "reject", "rejection_reason": "..."}
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request: Request, user_id: str) -> Response:
        serializer = AdminKYCReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            if data["action"] == "approve":
                user = _user_service.kyc_approve(
                    user_id=user_id, reviewed_by=request.user
                )
                detail = "KYC approved. User can now transact on the platform."
            else:
                user = _user_service.kyc_reject(
                    user_id=user_id,
                    reviewed_by=request.user,
                    rejection_reason=data["rejection_reason"],
                )
                detail = "KYC rejected. User has been notified."

        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        except InvalidKYCTransitionError as exc:
            return _service_error_to_drf(exc)

        return Response({"detail": detail, "kyc_status": user.kyc_status})


class AdminFreezeView(APIView):
    """
    POST /api/admin/users/{id}/freeze/

    Freeze an account. Body: {"reason": "..."}
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request: Request, user_id: str) -> Response:
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response(
                {"detail": "A freeze reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            _user_service.freeze_account(
                user_id=user_id, reason=reason, frozen_by=request.user
            )
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"detail": "Account frozen successfully."})


class AdminUnfreezeView(APIView):
    """
    POST /api/admin/users/{id}/unfreeze/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request: Request, user_id: str) -> Response:
        try:
            _user_service.unfreeze_account(user_id=user_id, unfrozen_by=request.user)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"detail": "Account unfrozen successfully."})


class PhoneVerifyView(APIView):
    """
    POST /api/v1/auth/verify-phone/

    Open endpoint. Sends (or re-sends) a phone-verification OTP by SMS.
    Always returns success so callers cannot probe for registered numbers.
    """

    permission_classes = []
    throttle_scope = "registration"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = PhoneVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone_number"]

        user = VerificationService.find_by_phone(phone)
        if user is not None and not user.is_frozen:
            try:
                VerificationService.send_phone_verify(user)
            except Exception:
                logger.exception("verify_phone.send_failed", extra={"phone": phone})

        return Response(
            {
                "detail": (
                    "If this phone number is registered, a verification code "
                    "has been sent by SMS."
                )
            }
        )


class PhoneVerifyConfirmView(APIView):
    """
    POST /api/v1/auth/verify-phone/confirm/

    Open endpoint. Confirms the OTP and marks the phone verified.
    """

    permission_classes = []
    throttle_scope = "auth"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = OtpConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = VerificationService.find_by_phone(data["phone_number"])
        if user is None:
            return Response(
                {"detail": "Invalid verification attempt.", "code": "invalid_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok = VerificationService.confirm_code(
            user=user,
            purpose=VerificationPurpose.PHONE_VERIFY,
            code=data["otp"],
            target=user.phone_number,
        )
        if not ok:
            return Response(
                {"detail": "Invalid or expired code.", "code": "invalid_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Phone number verified successfully.", "phone_verified": True}
        )


class PasswordResetView(APIView):
    """
    POST /api/v1/auth/password/reset/

    Open endpoint. Sends a password-reset code by email (if the user has
    one) or SMS. Always returns success to avoid user enumeration.
    """

    permission_classes = []
    throttle_scope = "registration"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone_number"]

        user = VerificationService.find_by_phone(phone)
        if user is not None and user.is_active and not user.is_frozen:
            try:
                VerificationService.send_password_reset(user)
            except Exception:
                logger.exception("password_reset.send_failed", extra={"phone": phone})

        return Response(
            {
                "detail": (
                    "If this phone number is registered, a password reset code "
                    "has been sent to your email or phone."
                )
            }
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password/reset/confirm/

    Open endpoint. Confirms the reset OTP and sets a new password.
    Body: {"phone_number", "otp", "new_password", "new_password_confirm"}
    """

    permission_classes = []
    throttle_scope = "auth"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = VerificationService.find_by_phone(data["phone_number"])
        if user is None:
            return Response(
                {"detail": "Invalid reset code.", "code": "invalid_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active or user.is_frozen:
            return Response(
                {"detail": "This account cannot reset its password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok = VerificationService.confirm_code(
            user=user,
            purpose=VerificationPurpose.PASSWORD_RESET,
            code=data["otp"],
        )
        if not ok:
            return Response(
                {"detail": "Invalid or expired code.", "code": "invalid_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(data["new_password"])
        user.save(update_fields=["password"])

        from apps.notifications.tasks import dispatch_password_changed

        dispatch_password_changed(user_pk=str(user.id))

        return Response({"detail": "Password reset successfully."})


class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/

    Authenticated. Changes the password after verifying the current one.
    Body: {"old_password", "new_password", "new_password_confirm"}
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.check_password(data["old_password"]):
            return Response(
                {"detail": "Your current password is incorrect.", "code": "invalid_password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(data["new_password"])
        request.user.save(update_fields=["password"])

        from apps.notifications.tasks import dispatch_password_changed

        dispatch_password_changed(user_pk=str(request.user.id))

        return Response({"detail": "Password changed successfully."})
