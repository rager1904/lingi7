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
from django import forms
from django.template.response import TemplateResponse
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
import logging

from .managers import UserManager
from .models import KYCStatus, User
from .services import UserService

_user_service = UserService()
logger = logging.getLogger(__name__)


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

    # Add KYC review actions to admin list view
    actions += ["action_approve_kyc", "action_reject_kyc"]

    change_form_template = "admin/users/change_form_with_kyc.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("kyc/reject/", self.admin_site.admin_view(self.kyc_reject_view), name="users_user_kyc_reject"),
            path("<path:object_id>/kyc/reject/", self.admin_site.admin_view(self.kyc_reject_view), name="users_user_kyc_reject_single"),
            path("<path:object_id>/kyc/approve/", self.admin_site.admin_view(self.kyc_approve_view), name="users_user_kyc_approve_single"),
        ]
        return custom_urls + urls

    class KYCRejectForm(forms.Form):
        _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
        rejection_reason = forms.CharField(widget=forms.Textarea, required=True, max_length=1000)

    def action_reject_kyc_with_reason(self, request, queryset):
        """Redirect selected users to the KYC reject form."""
        selected = queryset.values_list("id", flat=True)
        return redirect(f"../kyc/reject/?ids={','.join(str(x) for x in selected)}")

    action_reject_kyc_with_reason.short_description = "Reject selected KYC submissions (provide reason)"

    def kyc_reject_view(self, request, object_id=None):
        """Handle KYC reject form for selected users or single user."""
        ids = request.GET.get("ids", "")
        if object_id and not ids:
            ids = object_id
        id_list = [s for s in ids.split(",") if s]

        if request.method == "POST":
            form = self.KYCRejectForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data["rejection_reason"]
                count = 0
                for uid in id_list:
                    try:
                        _user_service.kyc_reject(user_id=str(uid), reviewed_by=request.user, rejection_reason=reason)
                        count += 1
                    except Exception as exc:
                        self.message_user(request, f"User {uid}: {exc}", level=messages.ERROR)
                self.message_user(request, f"{count} user(s) rejected.")
                return redirect("../")
        else:
            form = self.KYCRejectForm(initial={"_selected_action": id_list})

        context = dict(
            self.admin_site.each_context(request),
            form=form,
            ids=ids,
            title="Reject KYC submissions",
        )
        return TemplateResponse(request, "admin/users/kyc_reject.html", context)

    def kyc_approve_view(self, request, object_id):
        try:
            _user_service.kyc_approve(user_id=str(object_id), reviewed_by=request.user)
            self.message_user(request, "KYC approved.")
        except Exception as exc:
            self.message_user(request, f"Error approving KYC: {exc}", level=messages.ERROR)
        return redirect("../../")

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

    def save_model(self, request, obj, form, change):
        """Normalise phone to E.164 — admin bypasses UserManager.create_user."""
        obj.phone_number = UserManager._normalise_phone(obj.phone_number)
        super().save_model(request, obj, form, change)

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

    @admin.action(description=_("Approve selected KYC submissions"))
    def action_approve_kyc(self, request, queryset):
        """Approve KYC for selected users via UserService (only PENDING allowed)."""
        count = 0
        skipped = 0
        for user in queryset:
            if user.kyc_status != KYCStatus.PENDING:
                skipped += 1
                continue
            try:
                _user_service.kyc_approve(user_id=str(user.id), reviewed_by=request.user)
                count += 1
            except Exception:
                # Log and continue with next user
                logger.exception("admin.kyc.approve_failed", extra={"user_id": str(user.id)})
        msg = f"{count} KYC submission(s) approved."
        if skipped:
            msg += f" {skipped} user(s) skipped (not in PENDING state)."
        self.message_user(request, msg)

    @admin.action(description=_("Reject selected KYC submissions (uses generic reason)"))
    def action_reject_kyc(self, request, queryset):
        """Reject KYC for selected users via UserService with a generic reason."""
        count = 0
        skipped = 0
        for user in queryset:
            if user.kyc_status != KYCStatus.PENDING:
                skipped += 1
                continue
            try:
                _user_service.kyc_reject(
                    user_id=str(user.id),
                    reviewed_by=request.user,
                    rejection_reason="Rejected via admin panel",
                )
                count += 1
            except Exception:
                logger.exception("admin.kyc.reject_failed", extra={"user_id": str(user.id)})
        msg = f"{count} KYC submission(s) rejected."
        if skipped:
            msg += f" {skipped} user(s) skipped (not in PENDING state)."
        self.message_user(request, msg)
