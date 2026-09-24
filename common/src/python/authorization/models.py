"""Pydantic request and response models for the Authorization API."""

import json
import logging
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

log = logging.getLogger(__name__)


def _grant_request_payload(
    user_id: str,
    relation: str,
    resource: "ResourceObject",
) -> dict[str, Any]:
    """Build the JSON-serializable body of a single grant/revoke request.

    Emits ``userId``, ``relation``, and a structured ``resource`` via
    :meth:`ResourceObject.request_dump` (which uses API aliases, omits
    unset optionals, and excludes the server-owned ``flat_id``). No
    top-level ``type``/``resourceId`` is emitted. This is the single
    source of the single-operation request shape shared by
    :class:`GrantRequest`, :class:`RevokeRequest`, and
    :class:`PermissionCheckRequest`, and by each operation in a batch
    (see :meth:`BatchOperationModel.request_dump`), so the write paths
    cannot drift apart.
    """
    return {
        "userId": user_id,
        "relation": relation,
        "resource": resource.request_dump(),
    }


# Organization types carry no parent fields of their own. They are the
# structural containers in the Authorization API hierarchy (see the
# ``parent_type`` values used by the seed path in
# ``projects/hierarchy_seeder.py``: ``study``, ``research_center``,
# ``community``). ``ResourceObject`` uses this set to distinguish an
# organization type (which must carry none of ``study``/``center``/
# ``community``) from a resource type (which follows the per-type
# parent-field combination table). A type that is neither in this set nor
# in the per-type table is treated as a forward-compatible resource type
# and carries no parent-field combination constraint.
_ORGANIZATION_TYPES: frozenset[str] = frozenset(
    {"study", "research_center", "community"}
)

# --- Request Models ---


class GrantRequest(BaseModel):
    """Request model for granting a user a relation on a resource.

    Carries the resource identity as a structured
    :class:`ResourceObject` rather than a flat ``type``/``resourceId``
    pair. The request body is built by :meth:`request_body`, which emits
    ``{userId, relation, resource: resource.request_dump()}``.
    """

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    resource: "ResourceObject"

    def request_body(self) -> bytes:
        """Serialize this request to a JSON-encoded body.

        Emits ``userId``, ``relation``, and a structured ``resource`` (via
        :meth:`ResourceObject.request_dump`, which excludes ``flat_id``).
        No top-level ``type``/``resourceId`` is emitted.
        """
        payload = _grant_request_payload(self.user_id, self.relation, self.resource)
        return json.dumps(payload).encode()


class RevokeRequest(BaseModel):
    """Request model for revoking a user's relation on a resource.

    Mirrors :class:`GrantRequest`: identity is a structured
    :class:`ResourceObject`, and the request body is built by
    :meth:`request_body`.
    """

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    resource: "ResourceObject"

    def request_body(self) -> bytes:
        """Serialize this request to a JSON-encoded body.

        Emits ``userId``, ``relation``, and a structured ``resource`` (via
        :meth:`ResourceObject.request_dump`, which excludes ``flat_id``).
        No top-level ``type``/``resourceId`` is emitted.
        """
        payload = _grant_request_payload(self.user_id, self.relation, self.resource)
        return json.dumps(payload).encode()


class BatchOperationModel(BaseModel):
    """A single operation within a batch request payload.

    Carries the resource identity as a structured
    :class:`ResourceObject`; ``action``/``user_id``/``relation`` are
    unchanged.
    """

    model_config = ConfigDict(populate_by_name=True)

    action: Literal["grant", "revoke"]
    user_id: str = Field(alias="userId")
    relation: str
    resource: "ResourceObject"

    def request_dump(self) -> dict[str, Any]:
        """Serialize this operation for a batch request body.

        Emits ``action`` plus the same
        ``userId``/``relation``/structured ``resource`` shape as a
        single grant/revoke request (via the shared
        :func:`_grant_request_payload`), so a batched operation and a
        standalone operation serialize identically and cannot drift.
        """
        return {
            "action": self.action,
            **_grant_request_payload(self.user_id, self.relation, self.resource),
        }


class BatchRequestModel(BaseModel):
    """Request model for a batch of grant/revoke operations."""

    model_config = ConfigDict(populate_by_name=True)

    operations: list[BatchOperationModel]

    def request_body(self) -> bytes:
        """Serialize the batch to a JSON-encoded body.

        Emits ``{"operations": [...]}`` where each operation is
        serialized via :meth:`BatchOperationModel.request_dump`, so
        every operation carries a structured ``resource`` (no
        ``flat_id``, no top-level ``type``/``resourceId``) identical to
        the single-request path.
        """
        payload = {
            "operations": [operation.request_dump() for operation in self.operations]
        }
        return json.dumps(payload).encode()


class ParentRelationshipModel(BaseModel):
    """A parent relationship within a set-parents request."""

    model_config = ConfigDict(populate_by_name=True)

    structural_relation: str = Field(alias="structuralRelation")
    parent_type: str = Field(alias="parentType")
    parent_id: str = Field(alias="parentId")


class SetParentsRequestModel(BaseModel):
    """Request model for setting resource parents."""

    model_config = ConfigDict(populate_by_name=True)

    parents: list[ParentRelationshipModel]


# --- Resource Object ---


class ResourceObject(BaseModel):
    """Structured resource identity with explicit parent fields.

    Replaces opaque flat resource IDs at the API boundary. A single
    model is used for both request serialization and response parsing.

    Identity is the structured tuple of ``type``, ``label``, and the
    applicable parent fields (``study``, ``center``, ``community``). The
    ``flat_id`` field is a server-owned, read-only handle: it is only
    populated when parsing a response and is never emitted on a request.

    ``extra="ignore"`` drops any legacy ``id`` field supplied on parsed
    input so it is never serialized back. Requests are serialized via
    :meth:`request_dump`, which excludes ``flat_id``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str
    label: str = Field(min_length=1)
    flat_id: str | None = Field(default=None, alias="flatId")
    name: str | None = None
    study: str | None = None
    center: str | None = None
    community: str | None = None

    @model_validator(mode="after")
    def check_parent_fields(self) -> "ResourceObject":
        """Validate the parent-field combination against the resource type.

        Which parent fields (``study``, ``center``, ``community``) a
        resource may carry depends on its ``type``:

        - organization type (``study``/``research_center``/``community``):
          none of the parent fields
        - ``data_pipeline``: (``study`` + ``center``) or (``study`` alone)
        - ``dashboard``: (``study`` + ``center``) or (``study`` alone) or
          (``community`` alone)
        - ``page``: (``study`` + ``center``) or (``study`` alone) or
          (``center`` alone) or (``community`` alone)

        A type that is neither an organization type nor one of the
        resource types above is left unconstrained beyond the general
        ``label`` rule, so unknown/forward-compatible types are not
        rejected solely for their parent fields.

        Raises:
            ValueError: If the present parent fields do not match a
                combination permitted for the resource type. The message
                names the offending type.
        """
        present = (
            self.study is not None,
            self.center is not None,
            self.community is not None,
        )

        if self.type in _ORGANIZATION_TYPES:
            if any(present):
                raise ValueError(
                    f"parent fields (study, center, community) are not "
                    f"permitted for the organization resource type "
                    f"{self.type!r}"
                )
            return self

        allowed_combinations = {
            # (study_present, center_present, community_present)
            "data_pipeline": {
                (True, True, False),  # study + center
                (True, False, False),  # study alone
            },
            "dashboard": {
                (True, True, False),  # study + center
                (True, False, False),  # study alone
                (False, False, True),  # community alone
            },
            "page": {
                (True, True, False),  # study + center
                (True, False, False),  # study alone
                (False, True, False),  # center alone
                (False, False, True),  # community alone
            },
        }

        combinations = allowed_combinations.get(self.type)
        if combinations is not None and present not in combinations:
            raise ValueError(
                f"invalid parent field combination for the {self.type!r} "
                f"resource type (study={self.study!r}, center="
                f"{self.center!r}, community={self.community!r})"
            )

        return self

    def request_dump(self) -> dict[str, Any]:
        """Serialize this resource for a request body.

        Uses API aliases, omits unset optional fields, and always
        excludes the server-owned ``flat_id`` handle so it never appears
        in a request payload.

        Note:
            ``exclude_none=True`` means a field set explicitly to ``None``
            and a field left unset serialize identically — both are
            omitted. For identity fields (``name`` and the parent fields
            ``study``/``center``/``community``) this is intended: absence
            and an explicit ``None`` carry the same "this parent does not
            apply" meaning, and the API treats a missing parent field the
            same as a null one. Do not rely on emitting an explicit
            ``null`` for any field through this method.
        """
        return self.model_dump(by_alias=True, exclude_none=True, exclude={"flat_id"})


# The write-request models above reference ``ResourceObject`` as a forward
# reference (it is defined here, after them). Resolve those references now
# that ``ResourceObject`` exists in the module namespace.
GrantRequest.model_rebuild()
RevokeRequest.model_rebuild()
BatchOperationModel.model_rebuild()


# --- Response Models ---


class GrantResult(BaseModel):
    """Response model for a successful grant operation.

    Identity is read solely from the structured ``resource`` field. The
    legacy top-level ``type``/``resourceId`` identity fields are
    removed; ``extra="ignore"`` silently drops them if present on an
    incoming response so parsing cannot fall back to them. A
    ``resource`` of ``None`` means no Structured Identity was returned
    (no partial reconstruction). The ``flat_id`` on ``resource`` is
    opaque and echoed byte-for-byte as a GET ``{resourceId}`` path
    segment.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    user_id: str = Field(alias="userId")
    relation: str
    resource: ResourceObject | None = None


class RevokeResult(BaseModel):
    """Response model for a successful revoke operation.

    Identity is read solely from the structured ``resource`` field. The
    legacy top-level ``type``/``resourceId`` identity fields are
    removed; ``extra="ignore"`` silently drops them if present on an
    incoming response so parsing cannot fall back to them. A
    ``resource`` of ``None`` means no Structured Identity was returned
    (no partial reconstruction). The ``flat_id`` on ``resource`` is
    opaque and echoed byte-for-byte as a GET ``{resourceId}`` path
    segment.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    user_id: str = Field(alias="userId")
    relation: str
    resource: ResourceObject | None = None


class BatchError(BaseModel):
    """Details of a single failed operation within a batch response."""

    model_config = ConfigDict(populate_by_name=True)

    index: int
    error: str
    message: str


class BatchResult(BaseModel):
    """Aggregate result of a batch operation across all chunks."""

    model_config = ConfigDict(populate_by_name=True)

    total: int
    succeeded: int
    failed: int
    errors: list[BatchError] = []

    @field_validator("errors", mode="before")
    @classmethod
    def coerce_null_errors(cls, v: Any) -> Any:
        """Coerce a null or missing ``errors`` field to an empty list.

        The API omits ``errors`` on a clean batch, but some responses
        send ``"errors": null`` explicitly. A null value would otherwise
        fail list validation and make the whole response unparseable,
        masking the real batch outcome. Treat null as "no errors".
        """
        if v is None:
            return []
        return v


class InheritanceSource(BaseModel):
    """Source of an inherited permission."""

    model_config = ConfigDict(populate_by_name=True)

    parent_type: str = Field(alias="parentType")
    parent_id: str = Field(alias="parentId")
    parent_role: str = Field(alias="parentRole")


class PermissionEntry(BaseModel):
    """A single permission entry for a user on a resource.

    Note: The access and inherited_from fields are no longer returned by
    the bulk permissions endpoint (ADR-015). Use the effective-permissions
    endpoint for per-entry classification when needed.

    Identity is read solely from the structured ``resource`` field. The
    legacy top-level ``resourceId`` identity field is removed;
    ``extra="ignore"`` silently drops it if present on an incoming
    response so parsing cannot fall back to it. A ``resource`` of ``None``
    means no Structured Identity was returned (catalog gap): the entry has
    no identity and is not reconstructed from a flat id.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    relation: str
    access: Literal["direct", "inherited", "both"] | None = None
    inherited_from: InheritanceSource | None = Field(
        default=None, alias="inheritedFrom"
    )
    resource: ResourceObject | None = None


class UserPermissions(BaseModel):
    """Response model for a user's permissions grouped by resource type."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    permissions: dict[str, list[PermissionEntry]]

    def to_grants(self, factory: 'Callable[[str, "ResourceObject", str], Any]') -> set:
        """Convert permissions to a set of grant objects via a factory.

        Iterates over all permission entries and calls the factory for
        each, passing (user_id, resource, relation) where ``resource`` is
        the entry's structured :class:`ResourceObject`.

        Entries whose ``resource`` is ``None`` have no structured identity
        (a catalog gap): they are skipped with a warning and contribute no
        grant, so the conversion still completes successfully.

        Args:
            factory: Callable that creates a hashable grant object from
                the user id, the structured resource, and the relation.

        Returns:
            Set of grant objects produced by the factory.
        """
        grants: set = set()
        for resource_type, entries in self.permissions.items():
            for entry in entries:
                if entry.resource is None:
                    log.warning(
                        "Permissions entry for type %s has no resource; "
                        "skipping (catalog gap)",
                        resource_type,
                    )
                    continue
                grants.add(factory(self.user_id, entry.resource, entry.relation))
        return grants


class ParentRelationship(BaseModel):
    """A parent relationship in a resource parents response."""

    model_config = ConfigDict(populate_by_name=True)

    structural_relation: str = Field(alias="structuralRelation")
    parent_type: str = Field(alias="parentType")
    parent_id: str = Field(alias="parentId")


class ResourceParents(BaseModel):
    """Response model for a resource's parent relationships.

    Identity is read solely from the structured ``resource`` field. The
    legacy top-level ``type``/``resourceId`` identity fields are
    removed; ``extra="ignore"`` silently drops them if present on an
    incoming response so parsing cannot fall back to them. A
    ``resource`` of ``None`` means no Structured Identity was returned
    (no partial reconstruction). The ``parents`` relationship data is
    retained.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    parents: list[ParentRelationship]
    resource: ResourceObject | None = None


class HealthResult(BaseModel):
    """Response model for the health check endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["healthy", "degraded", "unhealthy"]
    authorization_engine: Literal["connected", "unreachable"] | None = Field(
        default=None, alias="authorizationEngine"
    )


class ErrorResponse(BaseModel):
    """Response model for API error responses."""

    model_config = ConfigDict(populate_by_name=True)

    error: str
    message: str
    details: dict | None = None


# --- User Profile Models ---


class UserProfileRequest(BaseModel):
    """Request model for creating or updating a user profile."""

    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(alias="firstName", min_length=1, max_length=256)
    last_name: str = Field(alias="lastName", min_length=1, max_length=256)
    email: str | None = Field(default=None, alias="email")
    auth_email: str = Field(alias="authEmail", min_length=1, max_length=256)
    active: bool | None = Field(default=None, alias="active")

    @field_validator("first_name", "last_name")
    @classmethod
    def must_contain_non_whitespace(cls, v: str) -> str:
        """Validate that name fields contain at least one non-whitespace
        character."""
        if not v.strip():
            raise ValueError("must contain at least one non-whitespace character")
        return v


class UserProfile(BaseModel):
    """Response model for a user profile."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    email: str | None = Field(default=None)
    auth_email: str = Field(alias="authEmail")
    active: bool


class UserProfileList(BaseModel):
    """Response model for batch user profile retrieval."""

    model_config = ConfigDict(populate_by_name=True)

    users: list[UserProfile]


class UserProfileSearchResponse(BaseModel):
    """Response model for user profile search with pagination."""

    model_config = ConfigDict(populate_by_name=True)

    users: list[UserProfile]
    next_token: str | None = Field(default=None, alias="nextToken")
    total: int
    limit: int


# --- Domain Types ---


class BatchOperation(BaseModel):
    """A single grant or revoke operation for batch submission.

    This is the caller-facing type used to construct batch requests.
    Field names use Python conventions (snake_case) rather than API
    aliases.
    """

    action: Literal["grant", "revoke"]
    user_id: str
    resource_type: str
    resource_label: str
    relation: str
    center: str | None = None
    study: str | None = None
    community: str | None = None


# --- Resource Listing Models ---


class ResourceListItem(BaseModel):
    """A single resource in a list resources response.

    Identity is read solely from the structured ``resource`` field. The
    legacy top-level ``resourceId`` identity field is removed;
    ``extra="ignore"`` silently drops it if present on an incoming
    response so parsing cannot fall back to it. A ``resource`` of
    ``None`` means no Structured Identity was returned (no partial
    reconstruction). The ``structural_relation``/``display_name`` list-
    display fields are retained.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    structural_relation: str | None = Field(default=None, alias="structuralRelation")
    display_name: str | None = Field(default=None, alias="displayName")
    resource: ResourceObject | None = None


class ResourceListResponse(BaseModel):
    """Response model for listing resources by type."""

    model_config = ConfigDict(populate_by_name=True)

    resources: list[ResourceListItem]
    next_token: str | None = Field(default=None, alias="nextToken")
    limit: int
    total: int | None = None


# --- Resource Update Models ---


class UpdateResourceRequest(BaseModel):
    """Request model for updating a resource's display name."""

    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName", max_length=256)


class UpdateResourceResponse(BaseModel):
    """Response model for a resource update operation."""

    model_config = ConfigDict(populate_by_name=True)

    resource_type: str = Field(alias="resourceType")
    resource_id: str = Field(alias="resourceId")
    display_name: str | None = Field(default=None, alias="displayName")


# --- Permission Check Models ---


class PermissionCheckRequest(BaseModel):
    """Request model for checking a specific permission.

    Mirrors :class:`GrantRequest`: identity is a structured
    :class:`ResourceObject`, and the request body is built by
    :meth:`request_body`.
    """

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    resource: "ResourceObject"

    def request_body(self) -> bytes:
        """Serialize this request to a JSON-encoded body.

        Emits ``userId``, ``relation``, and a structured ``resource`` (via
        :meth:`ResourceObject.request_dump`, which excludes ``flat_id``).
        No top-level ``type``/``resourceId`` is emitted.
        """
        payload = _grant_request_payload(self.user_id, self.relation, self.resource)
        return json.dumps(payload).encode()


class PermissionCheckResponse(BaseModel):
    """Response model for a permission check."""

    model_config = ConfigDict(populate_by_name=True)

    allowed: bool


# --- Authorization Model Metadata ---


class RelationMetadata(BaseModel):
    """Metadata for a relation within a type."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    assignable: bool


class StructuralRelationMetadata(BaseModel):
    """Metadata for a structural relation linking a resource to a parent."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    parent_type: str = Field(alias="parentType")
    description: str | None = None


class ComputedRelationMetadata(BaseModel):
    """Metadata for a computed relation derived from the hierarchy."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    source_relation: str = Field(alias="sourceRelation")
    parent_relation: str = Field(alias="parentRelation")
    grants_relation: str = Field(alias="grantsRelation")


class ParentCombination(BaseModel):
    """A valid combination of parent relationships for a resource type."""

    model_config = ConfigDict(populate_by_name=True)

    parents: list[str]
    description: str | None = None
    condition: str | None = None


class TypeMetadata(BaseModel):
    """Metadata for an organization or resource type."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    category: Literal["organization", "resource"]
    catalogable: bool = False
    description: str | None = None
    relations: dict[str, RelationMetadata]
    structural_relations: dict[str, StructuralRelationMetadata] | None = Field(
        default=None, alias="structuralRelations"
    )
    computed_relations: dict[str, ComputedRelationMetadata] | None = Field(
        default=None, alias="computedRelations"
    )
    valid_parent_combinations: list[ParentCombination] | None = Field(
        default=None, alias="validParentCombinations"
    )


class AuthorizationModelMetadata(BaseModel):
    """Response model for the authorization model metadata endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    version: str
    types: dict[str, TypeMetadata]
