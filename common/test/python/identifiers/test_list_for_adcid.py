"""Tests listing identifiers by ADCID through the lambda repository."""

import json
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository
from identifiers.identifiers_repository import IdentifierRepositoryError
from lambdas.lambda_function import LambdaClient


def _response(status: int, body: Dict[str, Any]) -> Mock:
    response = Mock()
    response.statusCode = status
    response.body = json.dumps(body)
    return response


def _client_returning(*responses: Mock) -> LambdaClient:
    client = Mock(spec=LambdaClient)
    client.invoke.side_effect = list(responses)
    return client


def _identifiers(count: int) -> List[Dict[str, Any]]:
    return [
        {
            "adcid": 1,
            "ptid": f"ptid{i}",
            "naccid": f"NACC{i:06d}",
            "active": True,
        }
        for i in range(count)
    ]


class TestListForADCID:
    """Listing identifiers for a center."""

    def test_no_identifiers_returns_empty_list(self):
        """A 404 on the first page means the center has no identifiers."""
        client = _client_returning(
            _response(404, {"message": "No identifiers found for ADCID 1"})
        )
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        assert repo.list(adcid=1) == []

    @pytest.mark.parametrize("status", [400, 500])
    def test_error_status_raises(self, status: int):
        """Statuses other than success or not-found are repository errors."""
        client = _client_returning(_response(status, {"message": "failure"}))
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        with pytest.raises(IdentifierRepositoryError):
            repo.list(adcid=1)

    def test_not_found_on_later_page_raises(self):
        """A 404 after the first page is unexpected and is not treated as the
        end of the list."""
        client = _client_returning(
            _response(200, {"offset": 0, "limit": 100, "data": _identifiers(100)}),
            _response(404, {"message": "not found"}),
        )
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        with pytest.raises(IdentifierRepositoryError):
            repo.list(adcid=1)

    def test_pages_are_combined(self):
        """Identifiers from all pages are returned."""
        client = _client_returning(
            _response(200, {"offset": 0, "limit": 100, "data": _identifiers(100)}),
            _response(200, {"offset": 100, "limit": 100, "data": []}),
        )
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        assert len(repo.list(adcid=1)) == 100
