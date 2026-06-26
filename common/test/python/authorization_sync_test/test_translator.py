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
)

from .conftest import (
    dashboard_names_st,
    mapped_activities_st,
    page_names_st,
    registry_ids_st,
    valid_datatypes_st,
)


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

        # The resource_id is just the resource name (no center_group_id)
        resource_name = activity.resource.name

        expected_grants = {
            DesiredGrant(
                user_id=registry_id,
                resource_type=resource_type,
                resource_id=resource_name,
                relation=relation,
            )
            for resource_type, relation in expected_pairs
        }

        assert grants == expected_grants

    @given(
        datatype=valid_datatypes_st,
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_submit_audit_datatype_produces_submitter_and_viewer(
        self,
        datatype: str,
        registry_id: str,
    ) -> None:
        """submit-audit on DatatypeResource produces both submitter AND viewer.

        **Validates: Requirements 1.2, 10.1, 10.3**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = Authorizations()
        auth.add(resource=resource, action="submit-audit")

        grants = translate(registry_id=registry_id, authorizations=auth)

        resource_id = resource.name

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
    )
    @settings(max_examples=100, deadline=None)
    def test_view_datatype_produces_viewer(
        self,
        datatype: str,
        registry_id: str,
    ) -> None:
        """view on DatatypeResource produces viewer on data_pipeline.

        **Validates: Requirements 1.3**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = Authorizations()
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="data_pipeline",
                resource_id=resource.name,
                relation="viewer",
            )
        }

        assert grants == expected

    @given(
        name=dashboard_names_st,
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_view_dashboard_produces_viewer(
        self,
        name: str,
        registry_id: str,
    ) -> None:
        """view on DashboardResource produces viewer on dashboard.

        **Validates: Requirements 1.4**
        """
        resource = DashboardResource(dashboard=name)
        auth = Authorizations()
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="dashboard",
                resource_id=name,
                relation="viewer",
            )
        }

        assert grants == expected

    @given(
        name=page_names_st,
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_view_page_produces_viewer(
        self,
        name: str,
        registry_id: str,
    ) -> None:
        """view on PageResource produces viewer on page.

        **Validates: Requirements 1.5**
        """
        resource = PageResource(page=name)
        auth = Authorizations()
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="page",
                resource_id=name,
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
