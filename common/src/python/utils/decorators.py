"""Utility decorators."""

import logging
import time
from typing import Callable, Type, TypeVar, Union

from flywheel.rest import ApiException

log = logging.getLogger(__name__)

T = TypeVar("T")


def api_retry(func, max_retries: int = 3):
    """Decorator to handle Flywheel API retries."""

    def wrapper(*args, **kwargs):
        retries = 0
        while retries <= max_retries:
            try:
                return func(*args, **kwargs)
            except ApiException as e:
                retries += 1
                if retries <= max_retries:
                    log.warning(
                        f"Encountered API error, retrying {retries}/{max_retries}"
                    )
                else:
                    raise e

    return wrapper


def retry_with_backoff(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    exceptions: Union[Type[Exception], tuple[Type[Exception], ...]] = Exception,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to retry a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Multiplier for exponential backoff (default: 2.0)
        exceptions: Exception type(s) to catch and retry (default: Exception)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(max_retries=3, backoff_factor=2.0)
        def my_function():
            # function that might fail transiently
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            retries = 0
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as error:
                    retries += 1
                    if retries > max_retries:
                        log.error(
                            (
                                f"{func.__name__} failed after "
                                f"{max_retries} retries: {error}"
                            )
                        )
                        raise

                    # Calculate exponential backoff delay
                    delay = backoff_factor**retries
                    log.warning(
                        f"{func.__name__} failed (attempt {retries}/{max_retries}), "
                        f"retrying in {delay:.1f}s: {error}"
                    )
                    time.sleep(delay)

            # This should never be reached, but satisfies type checker
            raise RuntimeError(f"{func.__name__} exhausted retries")

        return wrapper

    return decorator
