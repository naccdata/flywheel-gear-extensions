"""Module for connecting to the RxNav APIs.

https://lhncbc.nlm.nih.gov/RxNav/APIs
"""

import json
from dataclasses import dataclass
from json import JSONDecodeError

import requests
from ratelimit import limits, sleep_and_retry
from requests import Response

from .rxclass import ALL_RXCLASSES


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


class RxNavConnectionError(Exception):
    """Exception for errors that occur when connecting to the RxNav API."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def __str__(self) -> str:
        return self.message

    @property
    def message(self):
        """The error message."""
        return self._message


class RxNavConnection:
    """Manages a connection to the RxNav API."""

    @classmethod
    def url(cls, path: str) -> str:
        """Builds a URL for accessing a RxNav endpoint.

        Returns:
          URL constructed by extending the RxNav API path with the given string.
        """
        return f"https://rxnav.nlm.nih.gov/{path}"

    @classmethod
    @sleep_and_retry
    @limits(calls=20, period=1)
    def get_request(cls, path: str) -> Response:
        """Posts a request to the RxNav API.

        NLM requires users send no more than 20 requests per second per IP address:
        https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html

        Returns:
          The response from posting the request.

        Raises:
          RxNavConnectionError if there is an error connecting to the API.
        """
        target_url = cls.url(path)
        try:
            response = requests.get(target_url)
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
        ) as error:
            raise RxNavConnectionError(
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
        response = RxNavConnection.get_request(
            f"REST/rxcui/{rxcui}/historystatus.json"
        )

        if not response.ok:
            raise RxNavConnectionError(
                message=error_message(message=message, response=response)
            )

        try:
            history_record = json.loads(response.text)
        except (JSONDecodeError, ValueError) as error:
            message = f"Error decoding RXCUI history status response to JSON: {error}"
            raise RxNavConnectionError(message=message) from error

        return history_record["rxcuiStatusHistory"]["metaData"]["status"]

    @classmethod
    def get_rxclass_members(cls, rxclass: str, rela_source: str = 'ATCPROD') -> Optional[List[str]]:
        """Get list of RxClass members as RxCUI codes.

        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxClass.getClassMembers.html

        Args:
            rxclass: str, the RxClass (e.g. C02L)
            rela_source: str, the class to drug member relation (e.g. ATC or ATCPROD)

        Returns:
            List of RxCUIs associated with the RxClass
        """
        message = f"Getting RxClass members for {rxclass}"
        response = RxConnection.get_request(
            f"REST/rxclass/classMembers.json?classid={rxclass}&relaSource={rela_source}"
        )

        if not response.ok:
            raise RxConnectionError(
                message=error_message(message=message, response=response)
            )

        try:
            record = json.loads(response.text)
        except (JSONDecodeError, ValueError) as error:
            message = f"Error decoding RxClass response to JSON: {error}"
            raise RxConnectionError(message=message) from error

        # some may not have members depending on the class/relation source
        if not record:
            return None

        rxcuis = []
        for member in record["drugMemberGroup"]["drugMember"]:
            rxcuis.append(member['minConcept']['rxcui'].strip())

        return rxcuis

    @classmethod
    def get_all_rxclass_members(cls,
                                rxclasses: List[str],
                                rela_source: str = 'ATCPROD') -> Optional[Dict[str, List[str]]]:
        """Get members for all specified RxClasses. Assumes all have the same
        relation source.

        Returns mapping in the format:
        {
            "C02L": [
                    197959,
                    237192,
                    ...
                ],
                ...
            }
        }
        """
        results = {}
        for rxclass in rxclasses:
            results[rxclass] = cls.get_rxclass_members(rxclass, rela_source=rela_source)

        return results
