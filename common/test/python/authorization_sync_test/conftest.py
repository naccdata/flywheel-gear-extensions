"""Shared fixtures and Hypothesis strategies for authorization_sync tests."""

from dataclasses import dataclass, field
from typing import get_args
from unittest.mock import MagicMock

import pytest
from authorization.exceptions import (
    AuthorizationClientError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import (
    BatchOperation,
    BatchResult,
    PermissionEntry,
    UserPermissions,
    UserProfile,
    UserProfileRequest,
)
from authorization_sync.models import DesiredGrant
from hypothesis import strategies as st
from keys.types import DatatypeNameType
from users.authorizations import (
    ActionType,
    Activity,
    Authorizations,
    DashboardResource,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)

# --- Primitive Strategies ---

# Valid actions from the gear's ActionType literal
VALID_ACTIONS: list[str] = list(get_args(ActionType))
valid_actions_st = st.sampled_from(VALID_ACTIONS)

# Valid datatype names from DatatypeNameType literal
VALID_DATATYPES: list[str] = list(get_args(DatatypeNameType))
valid_datatypes_st = st.sampled_from(VALID_DATATYPES)

# Center group IDs: non-empty alphanumeric strings with hyphens
center_group_ids_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: not s.startswith("-") and not s.endswith("-"))

# Project labels: non-empty strings matching Flywheel naming patterns
project_labels_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=40,
).filter(lambda s: not s.startswith("-") and not s.endswith("-"))

# Registry IDs (ePPN format): non-empty strings
registry_ids_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-_@.",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

# Study IDs: non-empty alphanumeric strings
study_ids_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: not s.startswith("-") and not s.endswith("-"))

# Dashboard names
dashboard_names_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: not s.startswith("-") and not s.endswith("-"))

# Page names
page_names_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Nd"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: not s.startswith("-") and not s.endswith("-"))

# --- Resource Strategies ---

datatype_resources_st = valid_datatypes_st.map(lambda dt: DatatypeResource(datatype=dt))

dashboard_resources_st = dashboard_names_st.map(
    lambda name: DashboardResource(dashboard=name)
)

page_resources_st = page_names_st.map(lambda name: PageResource(page=name))

# Any valid Resource instance
resources_st = st.one_of(
    datatype_resources_st,
    dashboard_resources_st,
    page_resources_st,
)

# --- Activity Strategies ---

# Activities with valid mapped combinations
mapped_activities_st = st.one_of(
    # submit-audit + DatatypeResource
    valid_datatypes_st.map(
        lambda dt: Activity(
            resource=DatatypeResource(datatype=dt), action="submit-audit"
        )
    ),
    # view + DatatypeResource
    valid_datatypes_st.map(
        lambda dt: Activity(resource=DatatypeResource(datatype=dt), action="view")
    ),
    # view + DashboardResource
    dashboard_names_st.map(
        lambda name: Activity(resource=DashboardResource(dashboard=name), action="view")
    ),
    # view + PageResource
    page_names_st.map(
        lambda name: Activity(resource=PageResource(page=name), action="view")
    ),
)

# Activities with unmapped combinations (submit-audit + non-datatype)
unmapped_activities_st = st.one_of(
    # submit-audit + DashboardResource (unmapped)
    dashboard_names_st.map(
        lambda name: Activity(
            resource=DashboardResource(dashboard=name), action="submit-audit"
        )
    ),
    # submit-audit + PageResource (unmapped)
    page_names_st.map(
        lambda name: Activity(resource=PageResource(page=name), action="submit-audit")
    ),
)

# Any valid activity (mapped or unmapped)
any_activity_st = st.one_of(mapped_activities_st, unmapped_activities_st)


# --- DesiredGrant Strategies ---

# Resource types used in the Authorization API
API_RESOURCE_TYPES = ["data_pipeline", "dashboard", "page"]
api_resource_types_st = st.sampled_from(API_RESOURCE_TYPES)

# Relations used in the Authorization API
API_RELATIONS = ["submitter", "viewer", "editor"]
api_relations_st = st.sampled_from(API_RELATIONS)

# Resource IDs (can be center-scoped or general)
resource_ids_st = st.one_of(
    # Center-scoped: {center_group_id}/{project_label}
    st.tuples(center_group_ids_st, project_labels_st).map(lambda t: f"{t[0]}/{t[1]}"),
    # General: just project_label
    project_labels_st,
)

# DesiredGrant instances
desired_grants_st = st.builds(
    DesiredGrant,
    user_id=registry_ids_st,
    resource_type=api_resource_types_st,
    resource_id=resource_ids_st,
    relation=api_relations_st,
)

# Sets of DesiredGrant instances (for diff testing)
desired_grant_sets_st = st.frozensets(desired_grants_st, min_size=0, max_size=20)


# --- UserPermissions Response Strategies ---


@st.composite
def permission_entries_st(draw: st.DrawFn) -> PermissionEntry:
    """Generate a valid PermissionEntry."""
    resource_id = draw(resource_ids_st)
    relation = draw(api_relations_st)
    access = draw(st.sampled_from(["direct", "inherited", "both"]))
    return PermissionEntry(
        resource_id=resource_id,
        relation=relation,
        access=access,
        inherited_from=None,
    )


@st.composite
def user_permissions_st(draw: st.DrawFn) -> UserPermissions:
    """Generate a valid UserPermissions response."""
    user_id = draw(registry_ids_st)
    # Generate permissions grouped by resource type
    permissions: dict[str, list[PermissionEntry]] = {}
    resource_types = draw(
        st.lists(api_resource_types_st, min_size=0, max_size=3, unique=True)
    )
    for resource_type in resource_types:
        entries = draw(st.lists(permission_entries_st(), min_size=1, max_size=5))
        permissions[resource_type] = entries
    return UserPermissions(user_id=user_id, permissions=permissions)


# --- Authorizations Strategies ---


@st.composite
def authorizations_st(draw: st.DrawFn) -> Authorizations:
    """Generate a valid Authorizations object with random activities."""
    activities_list = draw(st.lists(mapped_activities_st, min_size=0, max_size=5))
    auth = Authorizations()
    for activity in activities_list:
        auth.activities.add(resource=activity.resource, activity=activity)
    return auth


@st.composite
def study_authorizations_st(draw: st.DrawFn) -> StudyAuthorizations:
    """Generate a valid StudyAuthorizations object."""
    study_id = draw(study_ids_st)
    activities_list = draw(st.lists(mapped_activities_st, min_size=0, max_size=5))
    auth = StudyAuthorizations(study_id=study_id)
    for activity in activities_list:
        auth.activities.add(resource=activity.resource, activity=activity)
    return auth


# --- AuthorizationClientError Strategies ---

authorization_client_errors_st = st.one_of(
    st.builds(
        ServiceUnavailableError,
        st.just("Service unavailable after retries"),
    ),
    st.builds(
        UnexpectedError,
        status_code=st.sampled_from([500, 502, 504]),
        message=st.text(min_size=1, max_size=50),
    ),
    st.builds(
        ValidationError,
        message=st.text(min_size=1, max_size=50),
        details=st.none(),
    ),
)


# --- Mock AuthorizationClient ---


@dataclass
class MockAuthorizationClient:
    """Mock AuthorizationClient for property tests.

    Configurable to return specific responses or raise exceptions.
    Captures all method calls for verification.
    """

    # Configurable responses
    permissions_response: UserPermissions | None = None
    batch_response: BatchResult = field(
        default_factory=lambda: BatchResult(total=0, succeeded=0, failed=0, errors=[])
    )
    error_to_raise: AuthorizationClientError | None = None

    # Call tracking
    get_user_permissions_calls: list[dict] = field(default_factory=list)
    batch_calls: list[list[BatchOperation]] = field(default_factory=list)
    put_user_profile_calls: list[dict] = field(default_factory=list)

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str | None = None,
        relation_filter: str | None = None,
    ) -> UserPermissions:
        """Mock get_user_permissions that returns configured response."""
        self.get_user_permissions_calls.append(
            {
                "user_id": user_id,
                "type_filter": type_filter,
                "relation_filter": relation_filter,
            }
        )
        if self.error_to_raise is not None:
            raise self.error_to_raise
        if self.permissions_response is not None:
            return self.permissions_response
        return UserPermissions(user_id=user_id, permissions={})

    def batch(self, operations: list[BatchOperation]) -> BatchResult:
        """Mock batch that returns configured response."""
        self.batch_calls.append(operations)
        if self.error_to_raise is not None:
            raise self.error_to_raise
        return BatchResult(
            total=len(operations),
            succeeded=len(operations),
            failed=0,
            errors=[],
        )

    def put_user_profile(
        self,
        profile_user_id: str,
        request: UserProfileRequest,
    ) -> UserProfile:
        """Mock put_user_profile that returns a default profile."""
        self.put_user_profile_calls.append(
            {"profile_user_id": profile_user_id, "request": request}
        )
        if self.error_to_raise is not None:
            raise self.error_to_raise
        return UserProfile(
            user_id=profile_user_id,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            auth_email=request.auth_email,
            active=request.active if request.active is not None else True,
        )


@pytest.fixture
def mock_authorization_client() -> MockAuthorizationClient:
    """Provide a mock AuthorizationClient for tests."""
    return MockAuthorizationClient()


@pytest.fixture
def mock_event_collector() -> MagicMock:
    """Provide a mock UserEventCollector for tests.

    Uses MagicMock so tests can verify collect() calls with
    assert_called_with patterns.
    """
    from users.event_models import UserEventCollector

    collector = MagicMock(spec=UserEventCollector)
    collector.get_events.return_value = []
    collector.get_errors.return_value = []
    return collector
