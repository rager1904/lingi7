"""Live USD-to-ZMW exchange rate helper.

Keeps the shopping assistant's Kwacha conversions current without hardcoding
a rate. The rate is fetched from a free FX endpoint, cached for a short TTL,
and falls back to the ``USD_TO_ZMW_RATE`` setting when the network is
unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_KEY = "usd_to_zmw_rate"


def get_usd_to_zmw_rate() -> float:
    """Return the current USD -> ZMW rate (units of Kwacha per 1 USD)."""
    cached = cache.get(_CACHE_KEY)
    if cached:
        return float(cached)

    rate = _fetch_live_rate()
    if rate is None:
        rate = float(getattr(settings, "USD_TO_ZMW_RATE", 27.0))
        logger.info("Using configured USD->ZMW fallback rate %.4f", rate)

    ttl = int(getattr(settings, "USD_TO_ZMW_RATE_TTL_SECONDS", 12 * 3600))
    if ttl > 0:
        try:
            cache.set(_CACHE_KEY, rate, timeout=ttl)
        except Exception as exc:  # cache backend hiccup should never block the assistant
            logger.warning("Failed to cache USD->ZMW rate: %s", exc)
    return rate


def _fetch_live_rate() -> float | None:
    urls = (
        getattr(
            settings,
            "USD_TO_ZMW_RATE_API",
            "https://open.er-api.com/v6/latest/USD",
        ),
        "https://api.frankfurter.app/latest?from=USD&to=ZMW",
    )
    for url in urls:
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            rate = _extract_rate(response.json())
            if rate is not None and rate > 0:
                logger.info("Fetched live USD->ZMW rate %.4f from %s", rate, url)
                return rate
        except Exception as exc:
            logger.warning("USD->ZMW rate fetch failed (%s): %s", url, exc)
    return None


def _extract_rate(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    rates = data.get("rates")
    if not isinstance(rates, dict):
        return None
    zmw = rates.get("ZMW")
    if zmw is None:
        return None
    try:
        zmw_number = float(zmw)
    except (TypeError, ValueError):
        return None

    base = str(data.get("base") or data.get("base_code") or "").upper()
    usd = rates.get("USD")
    if base == "EUR" and usd is not None:
        try:
            usd_number = float(usd)
        except (TypeError, ValueError):
            return None
        if usd_number > 0:
            return zmw_number / usd_number
    return zmw_number