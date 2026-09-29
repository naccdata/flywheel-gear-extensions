"""Tests for the flat-handle revoke form of the write-request models.

A revoke may address a resource either by a structured
``ScopedResourceObject`` (``resource``) or by the opaque flat handle
(``type`` + ``resourceId``) the API returned. The flat form exists so a
grant whose structured scope did not resolve (a catalog-gap fallback)
can still be revoked without rebuilding a structured identity. Grants
must always be structured.
"""

import json

import pytest
from authorization.models import (
    BatchOperationModel,
    RevokeRequest,
    ScopedResourceObject,
)
from pydantic import ValidationError as PydanticValidationError


class TestRevokeRequestFlatForm:
    """RevokeRequest supports the flat ``type`` + ``resourceId`` form."""

    def test_flat_handle_serializes_type_and_resource_id(self) -> None:
        """A flat revoke emits type + resourceId and no structured resource."""
        request = RevokeRequest(
            user_id="user@example.com",
            relation="viewer",
            resource_type="page",
            resource_id="ohsu_page-enrollment-clariti",
        )
        payload = json.loads(request.request_body())

        assert payload == {
            "userId": "user@example.com",
            "relation": "viewer",
            "type": "page",
            "resourceId": "ohsu_page-enrollment-clariti",
        }
        assert "resource" not in payload

    def test_structured_form_still_emits_resource(self) -> None:
        """The structured form is unchanged: emits a resource, no flat pair."""
        request = RevokeRequest(
            user_id="user@example.com",
            relation="viewer",
            resource=ScopedResourceObject(
                type="dashboard", label="dashboard-enrollment", community="nacc"
            ),
        )
        payload = json.loads(request.request_body())

        assert payload["resource"]["type"] == "dashboard"
        assert payload["resource"]["label"] == "dashboard-enrollment"
        assert "type" not in payload
        assert "resourceId" not in payload

    def test_both_forms_is_rejected(self) -> None:
        """Supplying both a structured resource and a flat handle is
        invalid."""
        with pytest.raises(PydanticValidationError):
            RevokeRequest(
                user_id="user@example.com",
                relation="viewer",
                resource=ScopedResourceObject(
                    type="page", label="page-x", community="nacc"
                ),
                resource_type="page",
                resource_id="page-x",
            )

    def test_neither_form_is_rejected(self) -> None:
        """Supplying no identity at all is invalid."""
        with pytest.raises(PydanticValidationError):
            RevokeRequest(user_id="user@example.com", relation="viewer")

    def test_partial_flat_handle_is_rejected(self) -> None:
        """A flat handle needs both type and resourceId."""
        with pytest.raises(PydanticValidationError):
            RevokeRequest(
                user_id="user@example.com",
                relation="viewer",
                resource_id="ohsu_page-enrollment-clariti",
            )


class TestBatchOperationFlatForm:
    """BatchOperationModel supports the flat form for revokes only."""

    def test_flat_revoke_serializes_type_and_resource_id(self) -> None:
        """A flat revoke op emits action + type + resourceId, no resource."""
        operation = BatchOperationModel(
            action="revoke",
            user_id="user@example.com",
            relation="viewer",
            resource_type="dashboard",
            resource_id="ohsu_dashboard-enrollment-clariti",
        )
        dumped = operation.request_dump()

        assert dumped == {
            "action": "revoke",
            "userId": "user@example.com",
            "relation": "viewer",
            "type": "dashboard",
            "resourceId": "ohsu_dashboard-enrollment-clariti",
        }
        assert "resource" not in dumped

    def test_structured_revoke_serializes_resource(self) -> None:
        """A structured revoke op still emits a resource."""
        operation = BatchOperationModel(
            action="revoke",
            user_id="user@example.com",
            relation="viewer",
            resource=ScopedResourceObject(
                type="dashboard", label="dashboard-enrollment", community="nacc"
            ),
        )
        dumped = operation.request_dump()

        assert dumped["action"] == "revoke"
        assert dumped["resource"]["label"] == "dashboard-enrollment"
        assert "resourceId" not in dumped

    def test_flat_grant_is_rejected(self) -> None:
        """A grant may not use the flat form — grants must be structured."""
        with pytest.raises(PydanticValidationError):
            BatchOperationModel(
                action="grant",
                user_id="user@example.com",
                relation="viewer",
                resource_type="page",
                resource_id="page-x",
            )

    def test_both_forms_is_rejected(self) -> None:
        """Supplying both forms on a batch op is invalid."""
        with pytest.raises(PydanticValidationError):
            BatchOperationModel(
                action="revoke",
                user_id="user@example.com",
                relation="viewer",
                resource=ScopedResourceObject(
                    type="page", label="page-x", community="nacc"
                ),
                resource_type="page",
                resource_id="page-x",
            )
