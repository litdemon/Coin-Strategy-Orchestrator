import time
import logging
import functools

logger = logging.getLogger(__name__)


def with_retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 16.0):
    """Decorator: retry with exponential backoff on any exception.

    Usage:
        @with_retry(max_attempts=3)
        def call_external_api():
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts:
                        logger.error(f"{fn.__name__} failed after {max_attempts} attempts: {exc}")
                        raise
                    logger.warning(
                        f"{fn.__name__} attempt {attempt}/{max_attempts} failed: {exc}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
        return wrapper
    return decorator
