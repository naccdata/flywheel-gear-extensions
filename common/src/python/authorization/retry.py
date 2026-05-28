"""Retry logic with exponential backoff for the Authorization Client."""

import logging
import time
from collections.abc import Callable

from authorization.exceptions import ServiceUnavailableError
from authorization.transport import HttpResponse

log = logging.getLogger(__name__)


def retry_on_503(
    operation: Callable[[], HttpResponse],
    *,
    max_retries: int = 3,
    base_backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> HttpResponse:
    """Execute an operation with retry on HTTP 503 responses.

    Retries the given callable up to `max_retries` times when it returns
    an HTTP 503 status code. Uses exponential backoff between attempts
    with the formula: base_backoff * 2^(attempt-1).

    Args:
        operation: A callable that returns an HttpResponse.
        max_retries: Maximum number of retry attempts before raising.
        base_backoff: Base delay in seconds for exponential backoff.
        sleep: Callable used to pause between retries. Defaults to
            ``time.sleep``; inject a no-op for fast unit tests.

    Returns:
        The HttpResponse from a successful (non-503) call.

    Raises:
        ServiceUnavailableError: When all retry attempts are exhausted
            and the service continues to return 503.
    """
    response = operation()
    if response.status_code != 503:
        return response

    for attempt in range(1, max_retries + 1):
        delay = base_backoff * (2 ** (attempt - 1))
        log.warning(
            "Received 503, retrying (attempt %d/%d) after %.2fs",
            attempt,
            max_retries,
            delay,
        )
        sleep(delay)
        response = operation()
        if response.status_code != 503:
            return response

    raise ServiceUnavailableError(f"Service unavailable after {max_retries} retries")
