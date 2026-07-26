"""
apps/payments/idempotency.py

Redis-backed idempotency layer for webhook and payment processing.

Prevents duplicate escrow state transitions when providers fire webhooks
multiple times for the same event (common in mobile money integrations).

Two-layer protection:
    1. Redis lock — fast in-memory check, prevents concurrent processing
    2. DB unique_together constraint — durable guarantee against race conditions

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from django.core.cache import cache

logger = logging.getLogger(__name__)

# TTL for idempotency keys in Redis (24 hours)
# Provider webhooks for a single payment shouldn't span more than 24 hours
_IDEMPOTENCY_TTL_SECONDS = 86_400

# Lock timeout — how long to hold the processing lock
# Should be longer than max webhook processing time
_LOCK_TTL_SECONDS = 30


class WebhookAlreadyProcessedError(Exception):
    """Raised when a webhook with this provider_reference was already processed."""

    def __init__(self, provider: str, provider_reference: str) -> None:
        self.provider = provider
        self.provider_reference = provider_reference
        super().__init__(
            f"Webhook already processed: {provider}:{provider_reference}"
        )


class WebhookConcurrentProcessingError(Exception):
    """Raised when another worker is currently processing the same webhook."""

    def __init__(self, provider: str, provider_reference: str) -> None:
        self.provider = provider
        self.provider_reference = provider_reference
        super().__init__(
            f"Concurrent processing detected: {provider}:{provider_reference}"
        )


def _idempotency_key(provider: str, provider_reference: str) -> str:
    """Build the Redis key for idempotency checking."""
    return f"payments:webhook:processed:{provider}:{provider_reference}"


def _lock_key(provider: str, provider_reference: str) -> str:
    """Build the Redis key for the processing lock."""
    return f"payments:webhook:lock:{provider}:{provider_reference}"


def is_already_processed(provider: str, provider_reference: str) -> bool:
    """
    Check if a webhook with this reference was already successfully processed.

    Args:
        provider: Provider identifier (e.g. "MTN_MOMO").
        provider_reference: Provider's unique reference for this event.

    Returns:
        True if already processed, False otherwise.
    """
    key = _idempotency_key(provider, provider_reference)
    return bool(cache.get(key))


def mark_as_processed(provider: str, provider_reference: str) -> None:
    """
    Mark a webhook reference as successfully processed in Redis.

    Args:
        provider: Provider identifier.
        provider_reference: Provider's unique reference.
    """
    key = _idempotency_key(provider, provider_reference)
    cache.set(key, "1", timeout=_IDEMPOTENCY_TTL_SECONDS)
    logger.debug("Marked webhook as processed: %s:%s", provider, provider_reference)


@contextmanager
def webhook_processing_lock(
    provider: str,
    provider_reference: str,
) -> Generator[None, None, None]:
    """
    Context manager that acquires a distributed lock for webhook processing.

    Prevents race conditions when a provider fires the same webhook multiple
    times in quick succession before the first processing completes.

    Raises:
        WebhookAlreadyProcessedError: If this reference was already processed.
        WebhookConcurrentProcessingError: If another worker holds the lock.

    Usage:
        try:
            with webhook_processing_lock("MTN_MOMO", "ref-123"):
                # process webhook
                pass
        except WebhookAlreadyProcessedError:
            return HttpResponse(status=200)  # Idempotent — acknowledge to provider
        except WebhookConcurrentProcessingError:
            return HttpResponse(status=202)  # Retry later
    """
    # Fast path: check Redis idempotency before acquiring lock
    if is_already_processed(provider, provider_reference):
        raise WebhookAlreadyProcessedError(provider, provider_reference)

    lock_key = _lock_key(provider, provider_reference)

    # Use Redis add (SET NX) as a distributed lock
    acquired = cache.add(lock_key, "1", timeout=_LOCK_TTL_SECONDS)
    if not acquired:
        logger.warning(
            "Concurrent processing attempt blocked: %s:%s",
            provider,
            provider_reference,
        )
        raise WebhookConcurrentProcessingError(provider, provider_reference)

    try:
        yield
    finally:
        # Always release the lock
        cache.delete(lock_key)
