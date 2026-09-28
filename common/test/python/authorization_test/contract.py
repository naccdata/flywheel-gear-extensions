"""Contract-enforcing test double for the Authorization API.

This module provides a transport-level mock that stands in for the real
Authorization API in tests, but — unlike a hand-written echo stub — derives
its behavior from the API's own published model metadata
(``contract_model.json``, a captured ``GET /model`` response). That makes it
an *independent* authority on the resource-identity contract rather than a
second copy of the client's assumptions:

- Requests the client serializes are validated against the model's
  ``validParentCombinations`` per type. A parent-field combination the API
  would reject (including a parentless resource type, or an organization type
  carrying parents) is rejected here with an HTTP 400 — without consulting the
  client's own ``ResourceObject.check_parent_fields``.
- Responses are generated *from the contract*: the structured ``resource`` is
  rebuilt from the request's structured identity and given a server-owned
  ``flat_id`` derived by the model's flat-form rule, never by echoing a handle
  the client supplied. If the client cannot parse a contract-shaped response,
  the parsing genuinely fails.

The premise (per the task) is "assume the API spec contract is met": the
fixture encodes the contract once, from the API's metadata, and the tests then
demonstrate the client only ever emits requests the contract accepts and
correctly consumes contract-shaped responses.

Provenance: ``contract_model.json`` is the ``GET /model`` response from the
Authorization API (version 1.0.0). If the API's model changes, re-capture that
file; the enforcement below reads it structurally and needs no code change.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from authorization.models import AuthorizationModelMetadata

# Maps a ResourceObject wire parent field to the structural-relation name the
# model's validParentCombinations are expressed in.
_FIELD_TO_STRUCTURAL_RELATION = {
    "study": "parent_study",
    "center": "parent_center",
    "community": "parent_community",
}


def load_contract_model() -> AuthorizationModelMetadata:
    """Load the captured authorization model metadata fixture.

    Returns:
        The parsed :class:`AuthorizationModelMetadata` from
        ``contract_model.json`` (a captured ``GET /model`` response).
    """
    path = Path(__file__).parent / "contract_model.json"
    return AuthorizationModelMetadata.model_validate_json(path.read_text())


def permitted_parent_field_sets(
    model: AuthorizationModelMetadata,
    resource_type: str,
) -> list[frozenset[str]]:
    """Return the permitted parent-field combinations for a type.

    Reads the type's ``validParentCombinations`` from the model and maps
    each combination's structural-relation names
    (``parent_study``/``parent_center``/``parent_community``) back to the
    ``ResourceObject`` wire field names (``study``/``center``/``community``).

    Args:
        model: The authorization model metadata.
        resource_type: The resource type to look up.

    Returns:
        A list of permitted parent-field-name sets. For an organization
        type (or any type with no ``validParentCombinations``) this is
        ``[frozenset()]`` — the only permitted combination is "no parents".
        For an unknown type, an empty list (nothing permitted).
    """
    relation_to_field = {v: k for k, v in _FIELD_TO_STRUCTURAL_RELATION.items()}
    type_meta = model.types.get(resource_type)
    if type_meta is None:
        return []
    if not type_meta.valid_parent_combinations:
        # Organization types and resource types without structural parents
        # accept exactly one combination: no parent fields.
        return [frozenset()]
    return [
        frozenset(relation_to_field[p] for p in combo.parents)
        for combo in type_meta.valid_parent_combinations
    ]


class ContractViolation(Exception):
    """Raised internally when a request violates the model contract."""


@dataclass
class _MockResponse:
    """Minimal HTTP response (status_code + body) for the client."""

    status_code: int
    body: bytes


@dataclass
class ContractEnforcingTransport:
    """Transport double that enforces the API's identity contract.

    Sits behind the real :class:`~authorization.client.AuthorizationClient`.
    Validates every grant/revoke/batch resource against the model's
    ``validParentCombinations`` and returns contract-shaped responses with
    an independently-derived ``flat_id``. Records the structured grants it
    holds so a sync round-trip can be exercised end-to-end.

    Any request carrying a parent-field combination the model does not
    permit yields an HTTP 400 (as the real API would), so a client that
    emitted such a request is caught here rather than by the client's own
    validator.
    """

    model: AuthorizationModelMetadata
    # Stored grants keyed by structured identity, as the API would persist
    # them: (user_id, type, label, relation, study, center, community).
    grants: set[tuple[str, str, str, str, str | None, str | None, str | None]] = field(
        default_factory=set
    )
    # Every resource payload the client sent, for assertions.
    seen_resources: list[dict[str, Any]] = field(default_factory=list)
    # Requests that violated the contract (should stay empty for a correct
    # client): list of (path, resource_payload, reason).
    violations: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)

    # --- contract enforcement -------------------------------------------------

    def _validate_resource(self, resource: dict[str, Any]) -> None:
        """Validate a resource payload against the model contract.

        Raises:
            ContractViolation: If the payload carries a flat identity, is
                missing an identity core, or its parent-field combination is
                not permitted for its type by the model.
        """
        self.seen_resources.append(resource)

        # The client must never emit a flat identity on a request.
        if "flatId" in resource or "flat_id" in resource:
            raise ContractViolation("request resource carries a flat id")

        resource_type = resource.get("type")
        label = resource.get("label")
        if not resource_type or not label:
            raise ContractViolation("resource missing type or label")

        present_fields = frozenset(
            fieldname
            for fieldname in _FIELD_TO_STRUCTURAL_RELATION
            if resource.get(fieldname) is not None
        )
        permitted = permitted_parent_field_sets(self.model, resource_type)
        if resource_type not in self.model.types:
            raise ContractViolation(f"unknown resource type {resource_type!r}")
        if present_fields not in permitted:
            raise ContractViolation(
                f"parent combination {sorted(present_fields)} not permitted for "
                f"type {resource_type!r}; permitted: "
                f"{[sorted(p) for p in permitted]}"
            )

    def _flat_id(self, resource: dict[str, Any]) -> str:
        """Derive a server-owned flat id per the model's flat form (ADR-016).

        Format: ``{center}_{label}-{study}`` with the scoping parts optional
        and a community prefix when community-scoped. Built here so the
        response carries a handle the client never produced itself.
        """
        label = resource["label"]
        study = resource.get("study")
        center = resource.get("center")
        community = resource.get("community")
        core = f"{label}-{study}" if study else label
        if center is not None:
            core = f"{center}_{core}"
        if community is not None:
            core = f"{community}_{core}"
        # A namespace marker so the id is visibly server-assigned and could
        # never be reproduced by the client from its structured identity.
        return f"srv::{core}"

    def _resource_response(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Build a contract-shaped response resource with a server flat id.

        Rebuilds the structured resource from the request's identity
        fields (not by copying the request object) and attaches an
        independently derived ``flatId``.
        """
        out: dict[str, Any] = {
            "type": resource["type"],
            "label": resource["label"],
            "flatId": self._flat_id(resource),
        }
        for fieldname in _FIELD_TO_STRUCTURAL_RELATION:
            if resource.get(fieldname) is not None:
                out[fieldname] = resource[fieldname]
        return out

    # --- transport interface --------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> _MockResponse:
        """Route a request, enforcing the contract on writes."""
        if path == "/grants" and method in ("POST", "DELETE"):
            return self._handle_single(method, body)
        if path == "/grants/batch" and method == "POST":
            return self._handle_batch(body)
        if path.endswith("/permissions") and method == "GET":
            return self._handle_permissions(path, query_params)
        return _MockResponse(status_code=404, body=b"{}")

    def _key(
        self, user_id: str, relation: str, resource: dict[str, Any]
    ) -> tuple[str, str, str, str, str | None, str | None, str | None]:
        return (
            user_id,
            resource["type"],
            resource["label"],
            relation,
            resource.get("study"),
            resource.get("center"),
            resource.get("community"),
        )

    def _handle_single(self, method: str, body: bytes | None) -> _MockResponse:
        assert body is not None
        payload = json.loads(body)
        resource = payload["resource"]
        user_id = payload["userId"]
        relation = payload["relation"]
        try:
            self._validate_resource(resource)
        except ContractViolation as exc:
            self.violations.append(("/grants", resource, str(exc)))
            return _MockResponse(
                status_code=400,
                body=json.dumps(
                    {"error": "validation_error", "message": str(exc)}
                ).encode(),
            )

        key = self._key(user_id, relation, resource)
        if method == "POST":
            self.grants.add(key)
        else:
            self.grants.discard(key)

        return _MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "userId": user_id,
                    "relation": relation,
                    "resource": self._resource_response(resource),
                }
            ).encode(),
        )

    def _handle_batch(self, body: bytes | None) -> _MockResponse:
        assert body is not None
        payload = json.loads(body)
        operations = payload["operations"]
        errors: list[dict[str, Any]] = []
        succeeded = 0
        for index, operation in enumerate(operations):
            resource = operation["resource"]
            try:
                self._validate_resource(resource)
            except ContractViolation as exc:
                self.violations.append(("/grants/batch", resource, str(exc)))
                errors.append(
                    {"index": index, "error": "validation_error", "message": str(exc)}
                )
                continue
            key = self._key(operation["userId"], operation["relation"], resource)
            if operation["action"] == "grant":
                self.grants.add(key)
            else:
                self.grants.discard(key)
            succeeded += 1
        return _MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "total": len(operations),
                    "succeeded": succeeded,
                    "failed": len(errors),
                    "errors": errors,
                }
            ).encode(),
        )

    def _handle_permissions(
        self, path: str, query_params: dict[str, str] | None
    ) -> _MockResponse:
        # ADR-015: the type query parameter is required.
        if not query_params or "type" not in query_params:
            return _MockResponse(
                status_code=400,
                body=json.dumps(
                    {"error": "validation_error", "message": "type is required"}
                ).encode(),
            )
        type_filter = query_params["type"]
        # user id is the path segment before /permissions
        user_id = path.split("/")[-2]

        entries = []
        for key in self.grants:
            (uid, rtype, label, relation, study, center, community) = key
            if uid != user_id or rtype != type_filter:
                continue
            resource: dict[str, Any] = {
                "type": rtype,
                "label": label,
                "flatId": self._flat_id(
                    {
                        "label": label,
                        "study": study,
                        "center": center,
                        "community": community,
                    }
                ),
            }
            if study is not None:
                resource["study"] = study
            if center is not None:
                resource["center"] = center
            if community is not None:
                resource["community"] = community
            entries.append({"relation": relation, "resource": resource})

        permissions = {type_filter: entries} if entries else {}
        return _MockResponse(
            status_code=200,
            body=json.dumps({"userId": user_id, "permissions": permissions}).encode(),
        )
