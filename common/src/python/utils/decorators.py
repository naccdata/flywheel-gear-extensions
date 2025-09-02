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


def sql_connection_retry(func, max_retries: int = 3, wait_time: int = 10):
    """Decorator to handle 1040, 'Too many connections' error."""

    def wrapper(*args, **kwargs):
        retries = 0
        while retries <= max_retries:
            try:
                return func(*args, **kwargs)
                break
            except pymysql.err.OperationalError as e:
                # only retry on 1040
                if e.args[0] == 1040:
                    retries += 1
                    if retries <= max_retries:
                        log.warning(
                            "Too many SQL connections, retrying "
                            f"{retries}/{max_retries} in {wait_time} seconds"
                        )
                        time.sleep(wait_time)
                        continue

                raise e

    return wrapper
