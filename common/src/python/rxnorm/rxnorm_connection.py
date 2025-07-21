"""Module for connecting to the RxNorm API.

https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html
"""

import json
from dataclasses import dataclass
from json import JSONDecodeError

import requests
from ratelimit import limits, sleep_and_retry
from requests import Response


def error_message(message: str, response: Response) -> str:
    """Build an error message from the given message and HTTP response.

    Returns:
      The error string
    """
    return (
        f"Error: {message}\nHTTP Error:{response.status_code} "
        f"{response.reason}: {response.text}"
    )


@dataclass
class RxcuiStatus:
    """Enumeration for keeping track of valid Rxcui statuses returned by the
    API."""

    ACTIVE = "Active"
    OBSOLETE = "Obsolete"
    REMAPPED = "Remapped"
    QUANTIFIED = "Quantified"
    NOT_CURRENT = "NotCurrent"
    UNKNOWN = "UNKNOWN"


class RxNormConnectionError(Exception):
    """Exception for errors that occur when connecting to the RxNorm API."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def __str__(self) -> str:
        return self.message

    @property
    def message(self):
        """The error message."""
        return self._message


class RxNormConnection:
    """Manages a connection to the RxNorm API."""

    @classmethod
    def url(cls, path: str) -> str:
        """Builds a URL for accessing a RxNorm endpoint.

        Returns:
          URL constructed by extending the RxNorm API path with the given string.
        """
        return f"https://rxnav.nlm.nih.gov/{path}"

    @classmethod
    @sleep_and_retry
    @limits(calls=20, period=1)
    def get_request(cls, path: str) -> Response:
        """Posts a request to the RxNorm API.

        NLM requires users send no more than 20 requests per second per IP address:
        https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html

        Returns:
          The response from posting the request.

        Raises:
          RxNormConnectionError if there is an error connecting to the API.
        """
        target_url = cls.url(path)
        try:
            response = requests.get(target_url)
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
        ) as error:
            raise RxNormConnectionError(
                message=f"Error connecting to {target_url} - {error}"
            ) from error

        return response

    @classmethod
    def get_rxcui_status(cls, rxcui: int) -> str:
        """Get the RxCUI status - uses the getRxcuiHistoryStatus endpoint:

        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getRxcuiHistoryStatus.html

        Args:
            rxcui: int, the RXCUI

        Returns:
            RxcuiStatus: The RxcuiStatus
        """
        message = "Getting the RXCUI history status"
        response = RxNormConnection.get_request(
            f"REST/rxcui/{rxcui}/historystatus.json"
        )

        if not response.ok:
            raise RxNormConnectionError(
                message=error_message(message=message, response=response)
            )

        try:
            history_record = json.loads(response.text)
        except (JSONDecodeError, ValueError) as error:
            message = f"Error decoding RXCUI history status response to JSON: {error}"
            raise RxNormConnectionError(message=message) from error

        return history_record["rxcuiStatusHistory"]["metaData"]["status"]
