"""Tests for the translator's structured DesiredGrant production.

**Validates: Requirements 3.2, 3.3, 3.4, 3.6, 3.7**

Tests that the translate function maps activities to relations using the
ACTIVITY_RELATION_MAP constant and produces DesiredGrant objects carrying
the Structured Identity (resource type, resource label, and parent fields)
rather than a flat resource id. Also tests the prefix->kind mapping table
and unknown-prefix rejection in build_label_for_resource_prefix.
"""

import pytest
from authorization_sync.models import DesiredGrant
from authorization_sync.resource_ids import build_label_for_resource_prefix
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

# Maps a resource prefix to the label kind produced for it (Req 3.6).
PREFIX_TO_KIND = {
    "datatype": "ingest",
    "dashboard": "dashboard",
    "page": "page",
}


def _expected_label(prefix: str, name: str) -> str:
    """Build the expected structured resource label for assertions.

    Uses the prefix->kind mapping (Req 3.6). Unlike the removed flat-id
    helper, this produces only the structured label: no study suffix and
    no center prefix. Parents are carried as separate DesiredGrant
    fields.
    """
    return f"{PREFIX_TO_KIND[prefix]}-{name}"


class TestActivityToRelationMappingCorrectness:
    """The translator produces DesiredGrants with structured identity.

    For any Activity consisting of an action and a Resource, the
    translator SHALL produce exactly the set of (resource_type,
    relation) pairs defined in the ACTIVITY_RELATION_MAP for that
    (action, resource_prefix) combination, each carrying the structured
    resource label and applicable parent fields.
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

        With a bare Authorizations (no study, no center) the parent the API
        requires must come from the general scope. A community-scoped
        resource type (``page``) carries ``community="nacc"``; any other
        mapped type has no parent the general path can supply and is
        skipped rather than emitted parentless (and rejected by the API).

        **Validates: Requirements 3.3, 3.4**
        """
        auth = Authorizations()
        auth.activities.add(resource=activity.resource, activity=activity)

        grants = translate(registry_id=registry_id, authorizations=auth)

        mapping_key = (activity.action, activity.resource.prefix())
        expected_pairs = ACTIVITY_RELATION_MAP[mapping_key]

        label = _expected_label(activity.resource.prefix(), activity.resource.name)

        expected_grants = {
            DesiredGrant(
                user_id=registry_id,
                resource_type=resource_type,
                relation=relation,
                resource_label=label,
                center=None,
                study=None,
                community="nacc",
            )
            for resource_type, relation in expected_pairs
            if resource_type == "page"
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

        Both grants carry the same structured label and the study parent
        from the StudyAuthorizations.

        **Validates: Requirements 3.3, 3.4**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="submit-audit")

        grants = translate(registry_id=registry_id, authorizations=auth)

        label = f"ingest-{datatype}"

        submitter_grant = DesiredGrant(
            user_id=registry_id,
            resource_type="data_pipeline",
            relation="submitter",
            resource_label=label,
            center=None,
            study=study_id,
            community=None,
        )
        viewer_grant = DesiredGrant(
            user_id=registry_id,
            resource_type="data_pipeline",
            relation="viewer",
            resource_label=label,
            center=None,
            study=study_id,
            community=None,
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

        **Validates: Requirements 3.3, 3.4**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="data_pipeline",
                relation="viewer",
                resource_label=f"ingest-{datatype}",
                center=None,
                study=study_id,
                community=None,
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

        **Validates: Requirements 3.3, 3.4**
        """
        resource = DashboardResource(dashboard=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="dashboard",
                relation="viewer",
                resource_label=f"dashboard-{name}",
                center=None,
                study=study_id,
                community=None,
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

        **Validates: Requirements 3.3, 3.4**
        """
        resource = PageResource(page=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(registry_id=registry_id, authorizations=auth)

        expected = {
            DesiredGrant(
                user_id=registry_id,
                resource_type="page",
                relation="viewer",
                resource_label=f"page-{name}",
                center=None,
                study=study_id,
                community=None,
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

        **Validates: Requirements 3.3**
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


class TestStructuredParentFields:
    """The translator carries parent fields as separate structured fields.

    Instead of composing a flat resource id with a center prefix and
    study suffix, each DesiredGrant carries center/study/community as
    distinct fields. Inapplicable parents are left None (Req 3.4).
    """

    @given(
        datatype=valid_datatypes_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
        center_group_id=center_group_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_center_scoped_datatype_sets_center_and_study_parents(
        self,
        datatype: str,
        registry_id: str,
        study_id: str,
        center_group_id: str,
    ) -> None:
        """Center-scoped data_pipeline grant carries center + study parents.

        The label has no study suffix and no center prefix; those are
        carried as structured fields instead.

        **Validates: Requirements 3.3, 3.4**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="submit-audit")

        grants = translate(
            registry_id=registry_id,
            authorizations=auth,
            center_group_id=center_group_id,
        )

        assert grants
        for grant in grants:
            assert grant.resource_type == "data_pipeline"
            assert grant.resource_label == f"ingest-{datatype}"
            assert grant.center == center_group_id
            assert grant.study == study_id
            assert grant.community is None

    @given(
        name=dashboard_names_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
        center_group_id=center_group_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_center_scoped_dashboard_sets_center_and_study_parents(
        self,
        name: str,
        registry_id: str,
        study_id: str,
        center_group_id: str,
    ) -> None:
        """Center-scoped dashboard grant carries center + study parents.

        **Validates: Requirements 3.3, 3.4**
        """
        resource = DashboardResource(dashboard=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(
            registry_id=registry_id,
            authorizations=auth,
            center_group_id=center_group_id,
        )

        assert len(grants) == 1
        grant = next(iter(grants))
        assert grant.resource_type == "dashboard"
        assert grant.resource_label == f"dashboard-{name}"
        assert grant.center == center_group_id
        assert grant.study == study_id
        assert grant.community is None

    @given(
        name=page_names_st,
        registry_id=registry_ids_st,
        study_id=study_ids_st,
        center_group_id=center_group_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_center_scoped_page_sets_center_and_study_parents(
        self,
        name: str,
        registry_id: str,
        study_id: str,
        center_group_id: str,
    ) -> None:
        """Center-scoped page grant carries center + study parents.

        **Validates: Requirements 3.3, 3.4**
        """
        resource = PageResource(page=name)
        auth = StudyAuthorizations(study_id=study_id)
        auth.add(resource=resource, action="view")

        grants = translate(
            registry_id=registry_id,
            authorizations=auth,
            center_group_id=center_group_id,
        )

        assert len(grants) == 1
        grant = next(iter(grants))
        assert grant.resource_type == "page"
        assert grant.resource_label == f"page-{name}"
        assert grant.center == center_group_id
        assert grant.study == study_id
        assert grant.community is None

    @given(
        page=page_names_st,
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_general_page_grant_is_community_scoped(
        self,
        page: str,
        registry_id: str,
    ) -> None:
        """General-scope page grants are scoped to the NACC community.

        A bare Authorizations has no study, and no center is passed. The
        Authorization API requires a parent for a ``page`` resource, so a
        general page grant carries ``community="nacc"`` (center and study
        stay unset) rather than being emitted parentless and rejected.

        **Validates: Requirements 3.4**
        """
        resource = PageResource(page=page)
        auth = Authorizations()
        auth.activities.add(
            resource=resource,
            activity=Activity(resource=resource, action="view"),
        )

        grants = translate(registry_id=registry_id, authorizations=auth)

        assert grants
        for grant in grants:
            assert grant.resource_type == "page"
            assert grant.center is None
            assert grant.study is None
            assert grant.community == "nacc"

    @given(
        datatype=valid_datatypes_st,
        registry_id=registry_ids_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_general_scope_skips_parentless_non_community_type(
        self,
        datatype: str,
        registry_id: str,
    ) -> None:
        """General-scope grants with no supplyable parent are skipped.

        A ``view`` on a datatype maps to a ``data_pipeline`` grant, which
        the Authorization API requires a parent for. With no center and no
        study (a bare Authorizations), the general path has no parent to
        supply and ``data_pipeline`` is not community-scoped, so the grant
        is skipped rather than emitted and rejected by the API.

        **Validates: Requirements 3.4**
        """
        resource = DatatypeResource(datatype=datatype)
        auth = Authorizations()
        auth.activities.add(
            resource=resource,
            activity=Activity(resource=resource, action="view"),
        )

        grants = translate(registry_id=registry_id, authorizations=auth)

        assert grants == set()


class TestResourcePrefixLabelMapping:
    """build_label_for_resource_prefix maps prefixes to label kinds.

    Covers the prefix->kind mapping table (Req 3.6) and rejection of
    unsupported prefixes (Req 3.7).
    """

    @pytest.mark.parametrize(
        ("prefix", "kind"),
        [
            ("datatype", "ingest"),
            ("dashboard", "dashboard"),
            ("page", "page"),
        ],
    )
    def test_prefix_maps_to_expected_kind(self, prefix: str, kind: str) -> None:
        """Each supported prefix produces a "{kind}-{name}" label.

        **Validates: Requirements 3.6**
        """
        assert build_label_for_resource_prefix(prefix, "example") == f"{kind}-example"

    @given(name=st.text(min_size=1, max_size=30))
    @settings(max_examples=50, deadline=None)
    def test_name_with_hyphens_is_preserved(self, name: str) -> None:
        """The name portion is appended verbatim after the kind.

        **Validates: Requirements 3.6**
        """
        assert build_label_for_resource_prefix("datatype", name) == f"ingest-{name}"

    @pytest.mark.parametrize(
        "unsupported_prefix",
        ["", "unknown", "organization", "study", "center", "ingest", "form"],
    )
    def test_unknown_prefix_is_rejected(self, unsupported_prefix: str) -> None:
        """An unsupported prefix raises ValueError without emitting a label.

        **Validates: Requirements 3.7**
        """
        with pytest.raises(ValueError):
            build_label_for_resource_prefix(unsupported_prefix, "example")


class TestDesiredGrantConstructionRejection:
    """DesiredGrant rejects construction missing structured identity.

    A DesiredGrant requires both a resource type and a resource label; a
    missing (empty) value for either is rejected rather than producing a
    partial grant (Req 3.2).
    """

    @given(
        registry_id=registry_ids_st,
        relation=st.sampled_from(["viewer", "submitter"]),
    )
    @settings(max_examples=25, deadline=None)
    def test_missing_resource_label_is_rejected(
        self,
        registry_id: str,
        relation: str,
    ) -> None:
        """Constructing a grant without a resource label raises ValueError.

        **Validates: Requirements 3.2**
        """
        with pytest.raises(ValueError):
            DesiredGrant(
                user_id=registry_id,
                resource_type="data_pipeline",
                relation=relation,
                resource_label="",
            )

    @given(
        registry_id=registry_ids_st,
        relation=st.sampled_from(["viewer", "submitter"]),
    )
    @settings(max_examples=25, deadline=None)
    def test_missing_resource_type_is_rejected(
        self,
        registry_id: str,
        relation: str,
    ) -> None:
        """Constructing a grant without a resource type raises ValueError.

        **Validates: Requirements 3.2**
        """
        with pytest.raises(ValueError):
            DesiredGrant(
                user_id=registry_id,
                resource_type="",
                relation=relation,
                resource_label="ingest-form",
            )
