"""
apps/users/serializers.py
-------------------------
DRF serializers for the users app.

Rules:
- Serializers handle validation and I/O shaping only.
- No business logic — all logic lives in UserService.
- KYC document fields accept S3/R2 presigned upload keys (not raw files).
- Passwords are write-only and never appear in any output.
- NRC numbers are write-only in output — never returned in list/retrieve
  endpoints to minimise PII exposure (DPA 2021).
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import KYCStatus, User, UserRole


class RegisterSerializer(serializers.Serializer):
    """
    Input serializer for POST /api/users/register/.

    Validates all fields required for a new user registration.
    Consent field enforces DPA 2021 acceptance gate.
    """

    phone_number = serializers.CharField(max_length=15)
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        validators=[validate_password],
    )
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    role = serializers.ChoiceField(
        choices=[UserRole.BUYER, UserRole.VENDOR],
        default=UserRole.BUYER,
    )
    email = serializers.EmailField(required=False, default="", allow_blank=True)
    consent_given = serializers.BooleanField()

    def validate_consent_given(self, value: bool) -> bool:
        """Reject registration if user has not explicitly accepted T&C / Privacy Policy."""
        if not value:
            raise serializers.ValidationError(
                "You must accept the Terms of Service and Privacy Policy to register "
                "(Zambia Data Protection Act 2021)."
            )
        return value

    def validate(self, data: dict) -> dict:
        """Cross-field: confirm passwords match."""
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return data


class KYCUploadSerializer(serializers.Serializer):
    """
    Input serializer for POST /api/users/me/kyc/.

    Accepts S3/R2 object keys returned from the presigned upload endpoint.
    The frontend uploads images directly to S3/R2 and passes the resulting
    object keys here — never streams binary through the Django API layer.

    BoZ requires: NRC front + back, selfie, physical address, province.
    """

    nrc_number = serializers.RegexField(
        regex=r"^\d{6}/\d{2}/[1-9]$",
        error_messages={
            "invalid": "NRC must be in format XXXXXX/YY/Z (e.g. 123456/78/1)."
        },
    )
    physical_address = serializers.CharField(max_length=500)
    province = serializers.ChoiceField(
        choices=[
            ("Copperbelt", "Copperbelt"),
            ("Lusaka", "Lusaka"),
            ("Central", "Central"),
            ("Eastern", "Eastern"),
            ("Luapula", "Luapula"),
            ("Muchinga", "Muchinga"),
            ("Northern", "Northern"),
            ("North-Western", "North-Western"),
            ("Southern", "Southern"),
            ("Western", "Western"),
        ]
    )
    nrc_front_key = serializers.CharField(max_length=512)
    nrc_back_key = serializers.CharField(max_length=512)
    selfie_key = serializers.CharField(max_length=512)


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Read serializer for GET /api/users/me/.

    Omits all sensitive fields (NRC number, S3 keys, password).
    Returns a safe public representation of the authenticated user.
    """

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "kyc_status",
            "is_frozen",
            "phone_verified",
            "email_verified",
            "date_joined",
            # Province shown — not the full address (DPA 2021 data minimisation)
            "province",
        ]
        read_only_fields = fields

    def get_full_name(self, obj: User) -> str:
        return obj.get_full_name()


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Write serializer for PATCH /api/users/me/.

    Only allows updating safe fields. Phone, NRC, KYC status, role, and
    freeze flags are immutable through this endpoint.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def validate_email(self, value: str) -> str:
        """If email is changing, reset email_verified flag."""
        if value and value != self.instance.email:
            self.instance.email_verified = False
        return value


class AdminUserDetailSerializer(serializers.ModelSerializer):
    """
    Admin-only read serializer. Exposes KYC metadata and review history.
    NEVER use on public endpoints.
    """

    kyc_reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "role",
            "nrc_number",
            "kyc_status",
            "kyc_submitted_at",
            "kyc_reviewed_at",
            "kyc_reviewed_by",
            "kyc_reviewed_by_name",
            "kyc_rejection_reason",
            "is_frozen",
            "frozen_at",
            "frozen_reason",
            "physical_address",
            "province",
            "date_joined",
            "consent_given_at",
            "data_deletion_requested_at",
        ]
        read_only_fields = fields

    def get_kyc_reviewed_by_name(self, obj: User) -> str | None:
        if obj.kyc_reviewed_by:
            return obj.kyc_reviewed_by.get_full_name()
        return None


class KYCReviewSerializer(serializers.Serializer):
    """
    Input serializer for admin KYC approve/reject actions.

    POST /api/admin/users/{id}/kyc/approve/
    POST /api/admin/users/{id}/kyc/reject/
    """

    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=1000,
    )

    def validate(self, data: dict) -> dict:
        """rejection_reason is mandatory when action=reject."""
        if data["action"] == "reject" and not data.get("rejection_reason", "").strip():
            raise serializers.ValidationError(
                {"rejection_reason": "A rejection reason is required when rejecting a KYC submission."}
            )
        return data


class LingiTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Customises the JWT access token payload with Lingi7-specific claims.

    Adds: role, kyc_status, is_frozen — so the React frontend and
    any microservice can make authorisation decisions without an
    additional /me round-trip on every request.
    """

    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        # Custom claims baked into the JWT
        token["role"] = user.role
        token["kyc_status"] = user.kyc_status
        token["is_frozen"] = user.is_frozen
        token["full_name"] = user.get_full_name()
        return token

    def validate(self, attrs: dict) -> dict:
        """Block login for frozen or inactive accounts at the token issuance layer."""
        data = super().validate(attrs)

        user: User = self.user  # type: ignore[attr-defined]

        if user.is_frozen:
            raise serializers.ValidationError(
                "Your account has been frozen. Please contact support."
            )

        # Augment the response body with user context
        data["user"] = {
            "id": str(user.id),
            "role": user.role,
            "kyc_status": user.kyc_status,
            "full_name": user.get_full_name(),
            "is_frozen": user.is_frozen,
        }
        return data
