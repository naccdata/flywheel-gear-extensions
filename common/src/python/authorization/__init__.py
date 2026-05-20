"""Authorization client library for the NACC Authorization API."""

from authorization.client import AuthorizationClient
from authorization.exceptions import (
    AuthorizationClientError,
    ConfigurationError,
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from authorization.factory import create_authorization_client
from authorization.models import (
    BatchError,
    BatchOperation,
    BatchOperationModel,
    BatchRequestModel,
    BatchResult,
    ErrorResponse,
    GrantRequest,
    GrantResult,
    HealthResult,
    InheritanceSource,
    ParentRelationship,
    ParentRelationshipModel,
    PermissionEntry,
    ResourceParents,
    RevokeRequest,
    RevokeResult,
    SetParentsRequestModel,
    UserPermissions,
)
from authorization.sigv4_transport import SigV4Transport
from authorization.transport import HttpResponse, HttpTransport

__all__ = [
    "AuthorizationClient",
    "AuthorizationClientError",
    "BatchError",
    "BatchOperation",
    "BatchOperationModel",
    "BatchRequestModel",
    "BatchResult",
    "ConfigurationError",
    "ErrorResponse",
    "GrantRequest",
    "GrantResult",
    "HealthResult",
    "HttpResponse",
    "HttpTransport",
    "InheritanceSource",
    "ParentRelationship",
    "ParentRelationshipModel",
    "ParseError",
    "PermissionEntry",
    "ResourceParents",
    "RevokeRequest",
    "RevokeResult",
    "ServiceUnavailableError",
    "SetParentsRequestModel",
    "SigV4Transport",
    "UnexpectedError",
    "UserPermissions",
    "ValidationError",
    "create_authorization_client",
]
