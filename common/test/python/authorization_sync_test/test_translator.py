"""Property tests for the Activity-to-relation mapping correctness.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 10.1, 10.3**

Tests that the translate function correctly maps activities to relations
using the ACTIVITY_RELATION_MAP constant.
"""

from authorization_sync.models import DesiredGrant
from authorization_sync.translator import ACTIVITY_RELATION_MAP, translate
from hypothesis import given, settings
from hypothesis import strategies as st
from users.authorizations import (
    Activity,
    Authorizations,
    DashboardResource,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)

from .conftest import (
    center_group_ids_st,
    dashboard_names_st,
    mapped_activities_st,
    page_names_st,
    registry_ids_st,
    study_ids_st,
    valid_datatypes_st,
)


def _expected_resource_id(resource: "Activity.resource", study_id: str | None) -> str:
    """Build the expected resource_id for test assertions.

    Mirrors the _build_resource_id logic in the translator:
    - datatype → "ingest-{name}"
    - dashboard → "dashboard-{name}"
    - page → "page-{name}"
    Then appends "-{study_id}" if study_id is provided.
    """
    prefix = resource.prefix()
    name = resource.name
    if prefix == "datatype":
        label = f"ingest-{name}"
    elif prefix == "dashboard":
        label = f"dashboard-{name}"
    elif prefix == "page":
        label = f"page-{name}"
    else:
        label = name

    if study_id:
        label = f"{label}-{study_id}"
    return label


class TestActivityToRelationMappingCorrectness:
    """Property 1: Activity-to-relation mapping correctness.

    For any Activity consisting of an action and a Resource, the
    translator SHALL produce exactly the set of (resource_type,
    relation) pairs defined in the ACTIVITY_RELATION_MAP for that
    (action, resource_prefix) combination.
    """

    @given(
        activity=mapped_activities_st,
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_mapped_activity_produces_correct_grants(
        self,
        activity: Activity,
        registry_id: str,
    ) -> None:
        """Any mapped activity produces grants matching ACTIVITY_RELATION_MAP.

        **Validates: Requirements 1.1**
        """
        auth = Authorizations()
        auth.activities.add(resource=activity.resource, activity=activity)

        grants = translate(registry_id=registry_id, authorizations=auth)

        # Look up expected mapping
        mapping_key = (activity.action, activity.resource.prefix())
        expected_pairs = ACTIVITY_RELATION_MAP[mapping_key]

        # Resource ID uses the new format (no study_id when using bare Authorizations)
        resource_id = _expected_resource_id(activity.resource, study_id=None)

        expected_grants = {
            DesiredGrant(
                user_id=registry_id,
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
            )
            for resource_type, relation in expected_pairs
        }

        assert grants == expected_grants

    @given(
        datatype=valid_datatypes_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_submit_audit_datatype_produces_submitter_and_viewer(
        self,
        datatype: str,
        registry_id: str,
        study_id: str,
    ) -> None:
        """submit-audit on DatatypeResource produces both submitter AND viewer.

        **Validates: Requirements 1.2, 10.1, 10.3**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="submit-audit")

        grants = translate(registry_id=registry_id, authorizations=auth)

        resource_id = f"ingest-{datatype}-{study_id}"

        submitter_grant = DesiredGrant(
            user_id=registry_id,
            resource_type="data_pipeline",
            resource_id=resource_id,
            relation="submitter",
        )
        viewer_grant = DesiredGrant(
            user_id=registry_id,
            resource_type="data_pipeline",
            resource_id=resource_id,
            relation="viewer",
        )

        assert submitter_grant in grants
        assert viewer_grant in grants
        assert len(grants) == 2

    @given(
        datatype=valid_datatypes_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_view_datatype_produces_viewer(
        self,
        datatype: str,
        registry_id: str,
        study_id: str,
    ) -> None:
        """view on DatatypeResource produces viewer on data_pipeline.

        **Validates: Requirements 1.3**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="data_pipeline",
                resource_id=f"ingest-{datatype}-{study_id}",
                relation="viewer",
            )
        }

        assert grants == expected

    @given(
        name=dashboard_names_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_view_dashboard_produces_viewer(
        self,
        name: str,
        registry_id: str,
        study_id: str,
    ) -> None:
        """view on DashboardResource produces viewer on dashboard.

        **Validates: Requirements 1.4**
        """
        resource = DashboardResource(dashboard=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="dashboard",
                resource_id=f"dashboard-{name}-{study_id}",
                relation="viewer",
            )
        }

        assert grants == expected

    @given(
        name=page_names_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_view_page_produces_viewer(
        self,
        name: str,
        registry_id: str,
        study_id: str,
    ) -> None:
        """view on PageResource produces viewer on page.

        **Validates: Requirements 1.5**
        """
        resource = PageResource(page=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="page",
                resource_id=f"page-{name}-{study_id}",
                relation="viewer",
            )
        }

        assert grants == expected

    @given(
        activities=st.lists(mapped_activities_st, min_size=1, max_size=5),
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_all_view_activities_produce_viewer_grants(
        self,
        activities: list[Activity],
        registry_id: str,
    ) -> None:
        """view on any resource produces viewer grants.

        **Validates: Requirements 1.7**
        """
        # Filter to only view activities
        view_activities = [a for a in activities if a.action == "view"]
        if not view_activities:
            return

        auth = Authorizations()
        for activity in view_activities:
            auth.activities.add(resource=activity.resource, activity=activity)

        grants = translate(registry_id=registry_id, authorizations=auth)

        # Every grant from a view activity should have relation "viewer"
        for grant in grants:
            assert grant.relation == "viewer"


class TestCenterScopedResourceIds:
    """Tests for center-scoped resource ID format.

    Verifies that the translator produces resource IDs with the center
    prefix using underscore separator per ADR-016.
    """

    @given(
        datatype=valid_datatypes_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
        center_group_id=center_group_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_center_scoped_datatype_uses_underscore_separator(
        self,
        datatype: str,
        registry_id: str,
        study_id: str,
        center_group_id: str,
    ) -> None:
        """Center-scoped data_pipeline resource_id uses underscore separator.

        Format: {center}_{ingest}-{datatype}-{study_id}
        """
        resource = DatatypeResource(datatype=datatype)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="submit-audit")

        grants = translate(
            registry_id=registry_id,
            authorizations=auth,
            center_group_id=center_group_id,
        )

        expected_resource_id = f"{center_group_id}_ingest-{datatype}-{study_id}"
        for grant in grants:
            assert grant.resource_id == expected_resource_id

    @given(
        name=dashboard_names_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
        center_group_id=center_group_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_center_scoped_dashboard_uses_underscore_separator(
        self,
        name: str,
        registry_id: str,
        study_id: str,
        center_group_id: str,
    ) -> None:
        """Center-scoped dashboard resource_id uses underscore separator.

        Format: {center}_dashboard-{name}-{study_id}
        """
        resource = DashboardResource(dashboard=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(
            registry_id=registry_id,
            authorizations=auth,
            center_group_id=center_group_id,
        )

        expected_resource_id = f"{center_group_id}_dashboard-{name}-{study_id}"
        assert len(grants) == 1
        grant = next(iter(grants))
        assert grant.resource_id == expected_resource_id

    @given(
        name=page_names_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
        center_group_id=center_group_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_center_scoped_page_uses_underscore_separator(
        self,
        name: str,
        registry_id: str,
        study_id: str,
        center_group_id: str,
    ) -> None:
        """Center-scoped page resource_id uses underscore separator.

        Format: {center}_page-{name}-{study_id}
        """
        resource = PageResource(page=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(
            registry_id=registry_id,
            authorizations=auth,
            center_group_id=center_group_id,
        )

        expected_resource_id = f"{center_group_id}_page-{name}-{study_id}"
        assert len(grants) == 1
        grant = next(iter(grants))
        assert grant.resource_id == expected_resource_id
