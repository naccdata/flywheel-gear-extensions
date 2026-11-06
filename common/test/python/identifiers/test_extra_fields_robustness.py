"""Tests that identifier response parsing tolerates extra fields.

The identifier lambdas are being changed to stop serializing ``naccadc``
in their responses. This repo no longer models ``naccadc``. These tests
pin the reverse-compatibility guarantee: if a lambda response still
carries ``naccadc`` (or any other unmodeled field), the repository
parses it successfully and simply drops the extra field, rather than
raising.
"""

import json
from typing import Any, Dict, List
from unittest.mock import Mock

from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository
from identifiers.model import IdentifierObject
from lambdas.lambda_function import LambdaClient


def _identifier_payload(**overrides: Any) -> Dict[str, Any]:
    """Builds an identifier response dict including the extra ``naccadc`` field
    that the model no longer declares."""
    payload = {
        "adcid": 1,
        "naccadc": 7,  # extra field no longer modeled by IdentifierObject
        "ptid": "one",
        "naccid": "NACC000000",
        "active": True,
    }
    payload.update(overrides)
    return payload


def _mock_client_returning(body: str) -> LambdaClient:
    """Returns a LambdaClient whose single invocation yields the given body."""
    response = Mock()
    response.statusCode = 200
    response.body = body

    client = Mock(spec=LambdaClient)
    client.invoke.return_value = response
    return client


def _envelope(data: List[Dict[str, Any]]) -> str:
    return json.dumps({"offset": 0, "limit": 100, "data": data})


class TestExtraFieldRobustness:
    """The repository tolerates an extra ``naccadc`` field in responses."""

    def test_model_ignores_extra_field(self):
        """IdentifierObject drops an unmodeled field instead of raising."""
        identifier = IdentifierObject.model_validate(_identifier_payload())

        assert identifier.adcid == 1
        assert identifier.ptid == "one"
        assert identifier.naccid == "NACC000000"
        assert not hasattr(identifier, "naccadc")

    def test_get_by_naccid_tolerates_extra_field(self):
        """A single-object response path ignores the extra field."""
        client = _mock_client_returning(json.dumps(_identifier_payload()))
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        identifier = repo.get(naccid="NACC000000")

        assert identifier is not None
        assert identifier.naccid == "NACC000000"
        assert not hasattr(identifier, "naccadc")

    def test_create_tolerates_extra_field(self):
        """The create response path ignores the extra field."""
        client = _mock_client_returning(json.dumps(_identifier_payload()))
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        identifier = repo.create(adcid=1, ptid="one", guid=None)

        assert identifier.naccid == "NACC000000"
        assert not hasattr(identifier, "naccadc")

    def test_list_for_naccid_tolerates_extra_field(self):
        """The paged list-envelope path ignores the extra field."""
        # A short page (len < limit) terminates the paging loop.
        client = _mock_client_returning(_envelope([_identifier_payload()]))
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        identifiers = repo.list(naccid="NACC000000")

        assert len(identifiers) == 1
        assert identifiers[0].naccid == "NACC000000"
        assert not hasattr(identifiers[0], "naccadc")

    def test_search_naccids_tolerates_extra_field(self):
        """The search_naccids envelope path ignores the extra field."""
        client = _mock_client_returning(
            _envelope(
                [
                    _identifier_payload(),
                    _identifier_payload(ptid="two", naccid="NACC000001"),
                ]
            )
        )
        repo = IdentifiersLambdaRepository(client=client, mode="prod")

        identifiers = repo.search_naccids(naccids=["NACC000000", "NACC000001"])

        assert len(identifiers) == 2
        assert {identifier.naccid for identifier in identifiers} == {
            "NACC000000",
            "NACC000001",
        }
        assert all(not hasattr(identifier, "naccadc") for identifier in identifiers)
