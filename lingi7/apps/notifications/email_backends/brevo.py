"""
Brevo Transactional Email Backend — apps/notifications/email_backends/brevo.py

Sends email through the Brevo Transactional Email API v3 instead of SMTP.

Brevo's SMTP relay requires authorizing the sending IP in your account, which
is unusable on dynamic/CGNAT connections (e.g. Zambian residential ISPs).
The Email API authenticates with an API key only and works from any IP.

Credential (settings):
    BREVO_API_KEY: Brevo API key (starts with "xkeysib-")

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_API_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
DEFAULT_SENDER_NAME = "Lingi7"

# Matches "Name <email@example.com>" and plain "email@example.com"
_EMAIL_RE = re.compile(r"^(.*?)\s*<([^>]+)>$")


def _parse_identity(raw: str) -> tuple[str, str]:
    """Split an RFC 5322 identity into (name, email)."""
    if not raw:
        return "", settings.DEFAULT_FROM_EMAIL
    match = _EMAIL_RE.match(raw.strip())
    if match:
        name, email = match.group(1).strip().strip('"'), match.group(2).strip()
        return name, email
    return "", raw.strip()


class BrevoEmailBackend(BaseEmailBackend):
    """
    Django email backend that POSTs messages to the Brevo v3 API.

    Works with django.core.mail.send_mail and EmailMultiAlternatives
    (plain-text body + text/html alternative). Supports cc, bcc,
    reply-to and file attachments.
    """

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, "BREVO_API_KEY", "")
        if not api_key:
            self._log_or_raise("BREVO_API_KEY is not configured")
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send_one(message, api_key)
                sent += 1
            except Exception as exc:
                self._log_or_raise(
                    "Brevo send failed for %s: %s", message.to, exc
                )
                if not self.fail_silently:
                    raise
        return sent

    # -- internal helpers ----------------------------------------------------

    def _send_one(self, message, api_key: str) -> None:
        from_email = message.from_email or settings.DEFAULT_FROM_EMAIL
        sender_name, sender_email = _parse_identity(from_email)
        if not sender_name:
            sender_name = DEFAULT_SENDER_NAME

        recipients = [{"email": e} for e in message.to]
        payload: dict = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": recipients,
            "subject": message.subject,
        }

        if message.cc:
            payload["cc"] = [{"email": e} for e in message.cc]
        if message.bcc:
            payload["bcc"] = [{"email": e} for e in message.bcc]
        if message.reply_to:
            _, reply_email = _parse_identity(message.reply_to[0])
            payload["replyTo"] = {"email": reply_email}

        text_value = message.body
        html_value = ""
        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                html_value = content

        if html_value:
            payload["htmlContent"] = html_value
        if text_value or not html_value:
            payload["textContent"] = text_value

        attachments = self._collect_attachments(message.attachments)
        if attachments:
            payload["attachments"] = attachments

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            BREVO_API_ENDPOINT,
            data=body,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()
                logger.info(
                    "Brevo accepted email to %s [%s]", message.to, response.status
                )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.error("Brevo API error %s: %s", exc.code, detail)
            raise RuntimeError(f"Brevo API returned {exc.code}: {detail}") from exc

    @staticmethod
    def _collect_attachments(attachments):
        """Convert Django attachments into Brevo's base64 payload format."""
        collected = []
        for item in attachments or []:
            if len(item) != 3:
                continue  # MIMEImage / other encoded objects — skip
            filename, content, _mimetype = item
            if isinstance(content, str):
                content = content.encode("utf-8")
            collected.append(
                {
                    "name": filename,
                    "content": base64.b64encode(content).decode("ascii"),
                }
            )
        return collected

    def _log_or_raise(self, fmt: str, *args) -> None:
        if self.fail_silently:
            logger.error(fmt, *args)
        else:
            raise RuntimeError(fmt % args if args else fmt)