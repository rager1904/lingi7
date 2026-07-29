import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def sync_cart_add(user_id: int, item: str, amount: int = 1, price: float | None = None) -> dict:
    """Forward a cart-add request to the memory_retriever service."""
    import httpx

    url = f"{settings.MEMORY_RETRIEVER_URL}/user/{user_id}/cart/add"
    payload = {"item": item, "amount": amount}
    if price is not None:
        payload["price"] = price

    try:
        with httpx.Client(timeout=5) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        logger.warning("memory_retriever returned %s: %s", e.response.status_code, e.response.text)
        return {"error": f"memory_retriever error: {e.response.status_code}", "detail": e.response.text}
    except httpx.RequestError as e:
        logger.warning("memory_retriever unreachable: %s", e)
        return {"error": f"memory_retriever unreachable: {e}"}



def sync_cart_remove(user_id: int, item: str, amount: int = 1) -> dict:
    import httpx

    url = f"{settings.MEMORY_RETRIEVER_URL}/user/{user_id}/cart/remove"
    payload = {"item": item, "amount": amount}

    try:
        with httpx.Client(timeout=5) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        logger.warning("memory_retriever returned %s: %s", e.response.status_code, e.response.text)
        return {"error": f"memory_retriever error: {e.response.status_code}", "detail": e.response.text}
    except httpx.RequestError as e:
        logger.warning("memory_retriever unreachable: %s", e)
        return {"error": f"memory_retriever unreachable: {e}"}


def sync_cart_update(user_id: int, item: str, amount: int = 1, price: float | None = None) -> dict:
    """Update quantity by computing the delta via add/remove."""
    import httpx

    url = f"{settings.MEMORY_RETRIEVER_URL}/user/{user_id}/cart/add"
    payload = {"item": item, "amount": amount}
    if price is not None:
        payload["price"] = price

    try:
        with httpx.Client(timeout=5) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        logger.warning("memory_retriever returned %s: %s", e.response.status_code, e.response.text)
        return {"error": f"memory_retriever error: {e.response.status_code}", "detail": e.response.text}
    except httpx.RequestError as e:
        logger.warning("memory_retriever unreachable: %s", e)
        return {"error": f"memory_retriever unreachable: {e}"}
