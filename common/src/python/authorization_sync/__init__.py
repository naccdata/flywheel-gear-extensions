"""Authorization sync module for translating gear authorizations to API
grants."""

from authorization_sync.models import DesiredGrant
from authorization_sync.resource_ids import (
    build_label_for_resource_prefix,
    build_resource_id,
)
from authorization_sync.sync_service import (
    AuthorizationClientProtocol,
    AuthorizationSyncService,
)
from authorization_sync.translator import (
    ACTIVITY_RELATION_MAP,
    check_assignable,
    translate,
    validate_activity_relation_map,
)

__all__ = [
    "ACTIVITY_RELATION_MAP",
    "AuthorizationClientProtocol",
    "AuthorizationSyncService",
    "DesiredGrant",
    "build_label_for_resource_prefix",
    "build_resource_id",
    "check_assignable",
    "translate",
    "validate_activity_relation_map",
]
