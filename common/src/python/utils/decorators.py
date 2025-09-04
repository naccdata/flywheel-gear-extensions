"""Utility decorators."""

import logging
import time

import pymysql  # type: ignore
from flywheel.rest import ApiException

log = logging.getLogger(__name__)


def api_retry(func, max_retries: int = 3):
    """Decorator to handle Flywheel API retries."""

    def wrapper(*args, **kwargs):
        retries = 0
        while retries <= max_retries:
            try:
                return func(*args, **kwargs)
                break
            except ApiException as e:
                retries += 1
                if retries <= max_retries:
                    log.warning(
                        f"Encountered API error, retrying {retries}/{max_retries}"
                    )
                else:
                    raise e

    return wrapper
