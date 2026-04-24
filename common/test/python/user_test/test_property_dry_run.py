"""Property test for dry-run mode behavior.

**Feature: disable-inactive-comanage-users, Property 4: Dry-run mode skips
writes but performs reads**
**Validates: Requirements 5.1, 5.2, 5.3**
"""

from unittest.mock import MagicMock

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from hypothesis import given, settings
from hypothesis import strategies as st
from users.user_registry import UserRegistry


def _registry_id_strategy():
    """Generate random non-empty registry ID strings."""
    return st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    ).filter(lambda s: len(s.strip()) > 0)


def _target_status_strategy():
    """Generate target status values: 'S' (suspend) or 'A' (re-enable)."""
    return st.sampled_from(["S", "A"])


@given(
    registry_id=_registry_id_strategy(),
    target_status=_target_status_strategy(),
)
@settings(max_examples=100)
def test_dry_run_skips_writes_but_performs_reads(
    registry_id: str,
    target_status: str,
):
    """Property test: Dry-run mode calls GET but never calls PUT.

    **Feature: disable-inactive-comanage-users, Property 4: Dry-run mode skips
    writes but performs reads**
    **Validates: Requirements 5.1, 5.2, 5.3**

    For any valid registry ID and any target status ('S' or 'A'), when dry-run
    mode is enabled, the UserRegistry SHALL call the GET endpoint to retrieve
    the record but SHALL NOT call the PUT endpoint.
    """
    # Arrange: build a mock API and a dry-run registry
    mock_api = MagicMock(spec=DefaultApi)

    # Mock GET to return a valid CoPersonMessage
    person_message = CoPersonMessage(
        CoPerson=CoPerson(co_id=1, status="A", meta=None),
    )
    get_response = MagicMock()
    get_response.var_0 = person_message
    mock_api.get_co_person.return_value = get_response

    registry = UserRegistry(
        api_instance=mock_api,
        coid=1,
        name_normalizer=lambda s: " ".join(s.lower().split()),
        dry_run=True,
    )

    # Act: call suspend or re_enable based on target_status
    if target_status == "S":
        registry.suspend(registry_id)
    else:
        registry.re_enable(registry_id)

    # Assert: GET was called (read performed)
    mock_api.get_co_person.assert_called_once_with(coid=1, identifier=registry_id)

    # Assert: PUT was NOT called (write skipped)
    mock_api.update_co_person.assert_not_called()
