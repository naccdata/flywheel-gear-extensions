"""Pydantic request and response models for the Authorization API."""

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

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


# --- Response Models ---


class GrantResult(BaseModel):
    """Response model for a successful grant operation."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")


class RevokeResult(BaseModel):
    """Response model for a successful revoke operation."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    relation: str
    type: str
    resource_id: str = Field(alias="resourceId")


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
    """A single permission entry for a user on a resource."""

    model_config = ConfigDict(populate_by_name=True)

    resource_id: str = Field(alias="resourceId")
    relation: str
    access: Literal["direct", "inherited", "both"]
    inherited_from: InheritanceSource | None = Field(
        default=None, alias="inheritedFrom"
    )


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
