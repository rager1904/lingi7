"""
apps/users/admin.py
-------------------
Django admin configuration for the User model.

Design:
- NRC number is read-only in the admin — cannot be edited after submission
  to prevent identity fraud via admin backdoor.
- KYC status is read-only — transitions must use the API (UserService) to
  maintain audit log integrity.
- S3/R2 document keys are hidden from the list view — only visible in
  detail view to minimise accidental PII exposure.
- Custom actions for bulk freeze/unfreeze go through UserService.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import KYCStatus, User
from .services import UserService

_user_service = UserService()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin interface for the Lingi7 User model.

    Extends Django's BaseUserAdmin to preserve password change functionality
    while customising fieldsets for our model structure.
    """

    list_display = [
        "phone_number",
        "get_full_name",
        "role",
        "kyc_status_badge",
        "is_frozen",
        "is_active",
        "date_joined",
    ]
    list_filter = ["role", "kyc_status", "is_frozen", "is_active", "province"]
    search_fields = ["phone_number", "first_name", "last_name", "nrc_number", "email"]
    ordering = ["-date_joined"]
    readonly_fields = [
        "id",
        "date_joined",
        "nrc_number",          # Immutable after submission
        "kyc_status",          # Changed via API only
        "kyc_submitted_at",
        "kyc_reviewed_at",
        "kyc_reviewed_by",
        "kyc_rejection_reason",
        "nrc_front_key",
        "nrc_back_key",
        "selfie_key",
        "frozen_at",
        "consent_given_at",
        "data_deletion_requested_at",
    ]
    actions = ["action_freeze", "action_unfreeze"]

    # Custom fieldsets replacing BaseUserAdmin defaults
    fieldsets = (
        (
            _("Account"),
            {
                "fields": (
                    "id",
                    "phone_number",
                    "email",
                    "password",
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "date_joined",
                )
            },
        ),
        (
            _("Profile"),
            {"fields": ("first_name", "last_name", "physical_address", "province")},
        ),
        (
            _("KYC — BoZ Identity Verification"),
            {
                "fields": (
                    "nrc_number",
                    "kyc_status",
                    "kyc_submitted_at",
                    "kyc_reviewed_at",
                    "kyc_reviewed_by",
                    "kyc_rejection_reason",
                    "nrc_front_key",
                    "nrc_back_key",
                    "selfie_key",
                ),
                "description": (
                    "⚠️ KYC status and NRC fields are read-only. "
                    "Use the API (POST /api/admin/users/{id}/kyc/review/) to approve or reject."
                ),
            },
        ),
        (
            _("Fraud / Compliance"),
            {
                "fields": (
                    "is_frozen",
                    "frozen_at",
                    "frozen_reason",
                    "device_fingerprint",
                    "consent_given_at",
                    "data_deletion_requested_at",
                )
            },
        ),
        (
            _("Permissions"),
            {"fields": ("groups", "user_permissions"), "classes": ("collapse",)},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_number",
                    "first_name",
                    "last_name",
                    "role",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    # ---------------------------------------------------------------- #
    # Display helpers                                                   #
    # ---------------------------------------------------------------- #

    @admin.display(description=_("KYC Status"))
    def kyc_status_badge(self, obj: User) -> str:
        """Render KYC status as a coloured badge in the list view."""
        colours = {
            KYCStatus.UNVERIFIED: "#888",
            KYCStatus.PENDING: "#f0a500",
            KYCStatus.VERIFIED: "#28a745",
            KYCStatus.REJECTED: "#dc3545",
        }
        colour = colours.get(obj.kyc_status, "#888")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600;">{}</span>',
            colour,
            obj.get_kyc_status_display(),
        )

    # ---------------------------------------------------------------- #
    # Bulk actions                                                      #
    # ---------------------------------------------------------------- #

    @admin.action(description=_("Freeze selected accounts"))
    def action_freeze(self, request, queryset):
        """Bulk freeze via UserService to ensure audit logging."""
        count = 0
        for user in queryset.exclude(is_frozen=True):
            _user_service.freeze_account(
                user_id=str(user.id),
                reason="Bulk freeze via Django admin",
                frozen_by=request.user,
            )
            count += 1
        self.message_user(request, f"{count} account(s) frozen.")

    @admin.action(description=_("Unfreeze selected accounts"))
    def action_unfreeze(self, request, queryset):
        """Bulk unfreeze via UserService."""
        count = 0
        for user in queryset.filter(is_frozen=True):
            _user_service.unfreeze_account(
                user_id=str(user.id), unfrozen_by=request.user
            )
            count += 1
        self.message_user(request, f"{count} account(s) unfrozen.")
