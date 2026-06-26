"""Authorization sync module for translating gear authorizations to API
grants."""

from authorization_sync.models import DesiredGrant
from authorization_sync.sync_service import (
    AuthorizationClientProtocol,
    AuthorizationSyncService,
)
from authorization_sync.translator import ACTIVITY_RELATION_MAP, translate

__all__ = [
    "ACTIVITY_RELATION_MAP",
    "AuthorizationClientProtocol",
    "AuthorizationSyncService",
    "DesiredGrant",
    "translate",
]
