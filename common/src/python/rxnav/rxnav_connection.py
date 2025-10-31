"""Module for connecting to the RxNav APIs.

https://lhncbc.nlm.nih.gov/RxNav/APIs
"""

import json
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel

import requests
from ratelimit import limits, sleep_and_retry
from requests import Response

log = logging.getLogger(__name__)


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


class RxcuiData(BaseModel):
    name: str
    tty: str


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
    def handle_response(cls, path: str, message: str) -> Dict[str, Any]:
        """Handle the response."""
        response = RxNavConnection.get_request(path)

        if not response.ok:
            raise RxNavConnectionError(
                message=error_message(message=message, response=response)
            )

        try:
            return json.loads(response.text)
        except (JSONDecodeError, ValueError) as error:
            message = f"Error decoding RxNav API response to JSON: {error}"
            raise RxNavConnectionError(message=message) from error

    @classmethod
    def get_rxcui_status(cls, rxcui: int) -> str:
        """Get the RxCUI status - uses the getRxcuiHistoryStatus endpoint:

        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getRxcuiHistoryStatus.html

        Args:
            rxcui: int, the RXCUI

        Returns:
            RxcuiStatus: The RxcuiStatus
        """
        record = cls.handle_response(
            message=f"Getting the RXCUI history status for {rxcui}",
            path=f"REST/rxcui/{rxcui}/historystatus.json",
        )

        return record["rxcuiStatusHistory"]["metaData"]["status"]

    @classmethod
    def get_rxclass_members(
        cls, rxclass: str, rela_source: str = "ATCPROD"
    ) -> Dict[str, RxcuiData]:
        """Get mapping of of RxClass members as RxCUI codes to its data.

        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxClass.getClassMembers.html

        Args:
            rxclass: str, the RxClass (e.g. C02L)
            rela_source: str, the class to drug member relation (e.g. ATC or ATCPROD)

        Returns:
            Mapping of RxCUIs to their data associated with the RxClass
        """
        record = cls.handle_response(
            message=f"Getting members for RxClass {rxclass}",
            path=f"REST/rxclass/classMembers.json?classId={rxclass}&relaSource={rela_source}",
        )
        results = {}

        # some may not have members depending on the class/relation source
        if record:
            for member in record["drugMemberGroup"]["drugMember"]:
                minconcept = member["minConcept"]
                rxcui = minconcept["rxcui"].strip()
                if rxcui in results:
                    continue

                results[rxcui] = RxcuiData(
                    name=minconcept["name"].strip(), tty=minconcept["tty"].strip()
                )

        return results

    @classmethod
    def get_related_rxcuis(cls, rxcui: str) -> Dict[str, RxcuiData]:
        """Get all related concepts as a mapping from RxCUI to data.

        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getAllRelatedInfo.html

        Args:
            rxcui: The RxCUI to get related info for
        Returns:
            Mapping of related RxCUIs to their data
        """
        record = cls.handle_response(
            message=f"Getting related concepts for RxCUI {rxcui}",
            path=f"REST/rxcui/{rxcui}/allrelated.json",
        )
        results = {}

        if record:
            for group in record["allRelatedGroup"]["conceptGroup"]:
                # filter/ignore out these ttys
                if group.get("tty") in ["IN", "DN", "DFG", None]:
                    continue

                for concept in group.get("conceptProperties", {}):
                    rxcui = concept["rxcui"].strip()
                    if rxcui in results:
                        continue

                    results[rxcui] = RxcuiData(
                        name=concept["name"].strip(), tty=concept["tty"].strip()
                    )

        return results

    @classmethod
    def get_all_rxclass_members(
        cls, rxclasses: List[str], rela_source: str = "ATCPROD"
    ) -> Dict[str, Dict[str, RxcuiData]]:
        """Get all related members for the specified RxClasses. Assumes all
        have the same relation source.

        Has two steps:
            1. Query the immediate members (getClassMembers endpoint)
                - ATCPROD notably returns products, not ingredients, which is why
                  we need step 2
            2. For each RxCUI returned, query the related concepts and keep track
               of all unique RxCUIs overall (getAllRelatedInfo endpoint)
                - This will include the ingredients
                - Filter out DF and DFG

        Args:
            rxclasses: List of the RxClasses to query and aggregate for
            rela_source: str, the class to drug member relation (e.g. ATC or ATCPROD)

        Returns:
            Mapping of RxClass to the RxCUI members and their data
        """
        results: Dict[str, Dict[str, RxcuiData]] = {}
        for rxclass in rxclasses:
            log.debug(f"Querying concepts for {rxclass}...")
            results[rxclass] = {}
            members = cls.get_rxclass_members(rxclass, rela_source=rela_source)

            for rxcui, data in members.items():
                if rxcui in results[rxclass]:
                    continue

                results[rxclass][rxcui] = data
                results[rxclass].update(cls.get_related_rxcuis(rxcui))

        return results


def load_rxclass_concepts_from_file(stream) -> Dict[str, Dict[str, RxcuiData]]:
    """Loads RxClass concepts from file, to avoid querying.

    Args:
        stream: input IO stream
    Returns:
        Mapping of RxClass to the RxCUI members and their data
    """
    results: Dict[str, Dict[str, RxcuiData]] = {}
    raw_concepts = json.load(stream)

    for rxclass, members in raw_concepts.items():
        for rxcui, data in members.items():
            results[rxclass][rxcui] = RxcuiData(**data)

    return results
