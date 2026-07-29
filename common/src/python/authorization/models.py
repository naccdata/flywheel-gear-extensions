"""Pydantic request and response models for the Authorization API."""

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Request Models ---


class GrantRequest(BaseModel):
    """Request model for granting a user a relation on a resource."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")


class RevokeRequest(BaseModel):
    """Request model for revoking a user's relation on a resource."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")


class BatchOperationModel(BaseModel):
    """A single operation within a batch request payload."""

    model_config = ConfigDict(populate_by_name=True)

    action: Literal["grant", "revoke"]
    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")


class BatchRequestModel(BaseModel):
    """Request model for a batch of grant/revoke operations."""

    model_config = ConfigDict(populate_by_name=True)

    operations: list[BatchOperationModel]


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

    Replaces opaque flat resource IDs at the API boundary. Parent fields
    vary by resource type based on the authorization model's
    validParentCombinations.

    During the transition period, this appears alongside legacy type and
    resourceId fields. When both are present in a request, the resource
    field takes precedence.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str
    id: str
    flat_id: str | None = Field(default=None, alias="flat_id")
    name: str | None = None
    study: str | None = None
    center: str | None = None
    community: str | None = None


# --- Response Models ---


class GrantResult(BaseModel):
    """Response model for a successful grant operation."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")
    resource: ResourceObject | None = None


class RevokeResult(BaseModel):
    """Response model for a successful revoke operation."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")
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
    """

    model_config = ConfigDict(populate_by_name=True)

    resource_id: str = Field(alias="resourceId")
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

    def to_grants(self, factory: "Callable[[str, str, str, str], Any]") -> set:
        """Convert permissions to a set of grant objects via a factory.

        Iterates over all permission entries and calls the factory for
        each, passing (user_id, resource_type, resource_id, relation).

        Args:
            factory: Callable that creates a hashable grant object from
                the four identifying fields.

        Returns:
            Set of grant objects produced by the factory.
        """
        grants: set = set()
        for resource_type, entries in self.permissions.items():
            for entry in entries:
                grants.add(
                    factory(
                        self.user_id,
                        resource_type,
                        entry.resource_id,
                        entry.relation,
                    )
                )
        return grants


class ParentRelationship(BaseModel):
    """A parent relationship in a resource parents response."""

    model_config = ConfigDict(populate_by_name=True)

    structural_relation: str = Field(alias="structuralRelation")
    parent_type: str = Field(alias="parentType")
    parent_id: str = Field(alias="parentId")


class ResourceParents(BaseModel):
    """Response model for a resource's parent relationships."""

    model_config = ConfigDict(populate_by_name=True)

    type: str
    resource_id: str = Field(alias="resourceId")
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
    resource_id: str
    relation: str


# --- Resource Listing Models ---


class ResourceListItem(BaseModel):
    """A single resource in a list resources response."""

    model_config = ConfigDict(populate_by_name=True)

    resource_id: str = Field(alias="resourceId")
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
    """Request model for checking a specific permission."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")


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
