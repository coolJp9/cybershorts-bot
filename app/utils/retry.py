"""Generic retry helper for transient network and I/O operations."""

import logging
import time
from typing import Any, Callable, Optional

from app.config.settings import NETWORK_RETRIES

log = logging.getLogger("CyberBot.retry")


def retry_call(
    name: str,
    fn: Callable[[], Any],
    attempts: int = NETWORK_RETRIES,
    delay: float = 2.0,
) -> Any:
    """Call *fn* up to *attempts* times, backing off on each failure.

    Raises the last exception if every attempt fails.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                wait = delay * attempt
                log.warning("%s failed (attempt %d/%d): %s — retrying in %.1fs",
                            name, attempt, attempts, exc, wait)
                time.sleep(wait)
            else:
                log.warning("%s failed after %d attempts: %s", name, attempts, exc)
    if last_error:
        raise last_error
    return None
