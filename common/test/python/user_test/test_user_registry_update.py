"""Unit tests for UserRegistry.suspend and re_enable methods.

Tests cover:
- suspend with valid registry ID calls GET then PUT with status "S"
- re_enable with valid registry ID calls GET then PUT with status "A"
- suspend with no registry ID raises RegistryError
- suspend when GET returns no record raises RegistryError
- suspend when PUT fails raises RegistryError with API error details
- re_enable when GET fails raises RegistryError
- dry-run mode logs but does not call PUT
"""

import logging
from unittest.mock import MagicMock

import pytest
from coreapi_client.api.default_api import DefaultApi
from coreapi_client.exceptions import ApiException
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name
from users.user_registry import RegistryError, UserRegistry


def _build_person_message(
    status: str = "A",
    registry_id: str = "NACC-001",
) -> CoPersonMessage:
    """Build a CoPersonMessage with related models for testing."""
    return CoPersonMessage(
        CoPerson=CoPerson(co_id=1, status=status, meta=None),
        EmailAddress=[
            EmailAddress(mail="test@example.com", type="official", verified=True)
        ],
        Name=[Name(given="John", family="Doe", type="official", primary_name=True)],
        Identifier=[Identifier(identifier=registry_id, type="naccid", status="A")],
        CoPersonRole=[CoPersonRole(cou_id=None, affiliation="member", status="A")],
    )


def _build_get_response(person_message: CoPersonMessage) -> MagicMock:
    """Build a mock GetCoPerson200Response."""
    response = MagicMock()
    response.var_0 = person_message
    response.additional_properties = None
    return response


def _build_empty_response() -> MagicMock:
    """Build a mock GetCoPerson200Response with no record."""
    response = MagicMock()
    response.var_0 = None
    response.additional_properties = None
    return response


def _build_registry(
    mock_api: MagicMock,
    dry_run: bool = False,
) -> UserRegistry:
    """Build a UserRegistry with a mock API."""
    return UserRegistry(
        api_instance=mock_api,
        coid=1,
        name_normalizer=lambda s: " ".join(s.lower().split()),
        dry_run=dry_run,
    )


class TestSuspend:
    """Tests for UserRegistry.suspend method."""

    def test_suspend_calls_get_then_put_with_status_s(self):
        """Suspend retrieves the full record and PUTs it back with status S."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="A")
        mock_api.get_co_person.return_value = _build_get_response(person_message)

        registry = _build_registry(mock_api)
        registry.suspend("NACC-001")

        mock_api.get_co_person.assert_called_once_with(coid=1, identifier="NACC-001")
        mock_api.update_co_person.assert_called_once_with(
            coid=1,
            identifier="NACC-001",
            co_person_message=person_message,
        )
        assert person_message.co_person is not None
        assert person_message.co_person.status == "S"

    def test_suspend_with_none_registry_id_raises_error(self):
        """Suspend with None registry ID raises RegistryError."""
        mock_api = MagicMock(spec=DefaultApi)
        registry = _build_registry(mock_api)

        with pytest.raises(RegistryError, match="Cannot update person: no registry ID"):
            registry.suspend(None)  # type: ignore[arg-type]

    def test_suspend_with_empty_registry_id_raises_error(self):
        """Suspend with empty string registry ID raises RegistryError."""
        mock_api = MagicMock(spec=DefaultApi)
        registry = _build_registry(mock_api)

        with pytest.raises(RegistryError, match="Cannot update person: no registry ID"):
            registry.suspend("")

    def test_suspend_when_get_returns_no_record_raises_error(self):
        """Suspend raises RegistryError when GET returns no matching record."""
        mock_api = MagicMock(spec=DefaultApi)
        mock_api.get_co_person.return_value = _build_empty_response()

        registry = _build_registry(mock_api)

        with pytest.raises(
            RegistryError,
            match="No COmanage record found for registry ID NACC-001",
        ):
            registry.suspend("NACC-001")

    def test_suspend_when_get_fails_raises_error(self):
        """Suspend raises RegistryError when GET API call fails."""
        mock_api = MagicMock(spec=DefaultApi)
        mock_api.get_co_person.side_effect = ApiException(
            status=500, reason="Server Error"
        )

        registry = _build_registry(mock_api)

        with pytest.raises(RegistryError, match="API get_co_person call failed"):
            registry.suspend("NACC-001")

    def test_suspend_when_put_fails_raises_error(self):
        """Suspend raises RegistryError with API error details when PUT
        fails."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="A")
        mock_api.get_co_person.return_value = _build_get_response(person_message)
        mock_api.update_co_person.side_effect = ApiException(
            status=400, reason="Bad Request"
        )

        registry = _build_registry(mock_api)

        with pytest.raises(RegistryError, match="API update_co_person call failed"):
            registry.suspend("NACC-001")

    def test_suspend_preserves_related_models(self):
        """Suspend preserves all related models in the PUT request."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="A")
        mock_api.get_co_person.return_value = _build_get_response(person_message)

        registry = _build_registry(mock_api)
        registry.suspend("NACC-001")

        put_message = mock_api.update_co_person.call_args.kwargs["co_person_message"]
        assert put_message.email_address is not None
        assert len(put_message.email_address) == 1
        assert put_message.name is not None
        assert len(put_message.name) == 1
        assert put_message.identifier is not None
        assert put_message.co_person_role is not None


class TestReEnable:
    """Tests for UserRegistry.re_enable method."""

    def test_re_enable_calls_get_then_put_with_status_a(self):
        """Re-enable retrieves the full record and PUTs it back with status
        A."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="S")
        mock_api.get_co_person.return_value = _build_get_response(person_message)

        registry = _build_registry(mock_api)
        registry.re_enable("NACC-001")

        mock_api.get_co_person.assert_called_once_with(coid=1, identifier="NACC-001")
        mock_api.update_co_person.assert_called_once_with(
            coid=1,
            identifier="NACC-001",
            co_person_message=person_message,
        )
        assert person_message.co_person is not None
        assert person_message.co_person.status == "A"

    def test_re_enable_with_no_registry_id_raises_error(self):
        """Re-enable with None registry ID raises RegistryError."""
        mock_api = MagicMock(spec=DefaultApi)
        registry = _build_registry(mock_api)

        with pytest.raises(RegistryError, match="Cannot update person: no registry ID"):
            registry.re_enable(None)  # type: ignore[arg-type]

    def test_re_enable_when_get_fails_raises_error(self):
        """Re-enable raises RegistryError when GET API call fails."""
        mock_api = MagicMock(spec=DefaultApi)
        mock_api.get_co_person.side_effect = ApiException(
            status=500, reason="Server Error"
        )

        registry = _build_registry(mock_api)

        with pytest.raises(RegistryError, match="API get_co_person call failed"):
            registry.re_enable("NACC-001")


class TestDryRunMode:
    """Tests for dry-run mode behavior in status update methods."""

    def test_suspend_dry_run_logs_but_does_not_put(self, caplog):
        """In dry-run mode, suspend logs the intended action without calling
        PUT."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="A")
        mock_api.get_co_person.return_value = _build_get_response(person_message)

        registry = _build_registry(mock_api, dry_run=True)

        with caplog.at_level(logging.INFO):
            registry.suspend("NACC-001")

        mock_api.get_co_person.assert_called_once()
        mock_api.update_co_person.assert_not_called()
        assert "DRY RUN" in caplog.text
        assert "NACC-001" in caplog.text
        assert "S" in caplog.text

    def test_re_enable_dry_run_logs_but_does_not_put(self, caplog):
        """In dry-run mode, re_enable logs the intended action without calling
        PUT."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="S")
        mock_api.get_co_person.return_value = _build_get_response(person_message)

        registry = _build_registry(mock_api, dry_run=True)

        with caplog.at_level(logging.INFO):
            registry.re_enable("NACC-001")

        mock_api.get_co_person.assert_called_once()
        mock_api.update_co_person.assert_not_called()
        assert "DRY RUN" in caplog.text
        assert "NACC-001" in caplog.text
        assert "A" in caplog.text

    def test_dry_run_still_performs_get(self):
        """In dry-run mode, GET is still called to validate the record
        exists."""
        mock_api = MagicMock(spec=DefaultApi)
        person_message = _build_person_message(status="A")
        mock_api.get_co_person.return_value = _build_get_response(person_message)

        registry = _build_registry(mock_api, dry_run=True)
        registry.suspend("NACC-001")

        mock_api.get_co_person.assert_called_once_with(coid=1, identifier="NACC-001")

    def test_dry_run_property(self):
        """The dry_run property reflects the constructor parameter."""
        mock_api = MagicMock(spec=DefaultApi)

        registry_normal = _build_registry(mock_api, dry_run=False)
        assert registry_normal.dry_run is False

        registry_dry = _build_registry(mock_api, dry_run=True)
        assert registry_dry.dry_run is True
