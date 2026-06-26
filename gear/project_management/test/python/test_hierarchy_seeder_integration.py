"""Integration tests for ResourceHierarchySeeder with StudyMappingVisitor.

Tests the full gear run with a representative StudyModel containing
center-scoped pipelines, center-scoped dashboards, study-scoped dashboards,
study-scoped pages, and community-scoped pages. Verifies the complete set
of set_resource_parents calls matches expected (resource_type, resource_id,
parents) tuples.

Validates: Requirements 9.1, 6.1, 6.3
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from authorization.client import AuthorizationClient
from authorization.models import ParentRelationshipModel, ResourceParents
from projects.hierarchy_seeder import ResourceHierarchySeeder
from projects.study import DashboardConfig, DatatypeConfig, PageConfig, StudyModel
from projects.study_mapping import StudyMappingVisitor


def _parent(
    structural_relation: str, parent_type: str, parent_id: str
) -> ParentRelationshipModel:
    """Helper to create a ParentRelationshipModel."""
    return ParentRelationshipModel(
        structural_relation=structural_relation,
        parent_type=parent_type,
        parent_id=parent_id,
    )


def _center_parents(study_id: str, center_id: str) -> list[ParentRelationshipModel]:
    """Build expected center-scoped parents."""
    return [
        _parent("parent_study", "study", study_id),
        _parent("parent_center", "research_center", center_id),
    ]


def _study_parents(study_id: str) -> list[ParentRelationshipModel]:
    """Build expected study-scoped parents."""
    return [
        _parent("parent_study", "study", study_id),
    ]


def _community_parents() -> list[ParentRelationshipModel]:
    """Build expected community-scoped parents."""
    return [
        _parent("parent_community", "community", "nacc"),
    ]


@pytest.fixture
def mock_authorization_client() -> MagicMock:
    """Create a mock AuthorizationClient that records set_resource_parents
    calls."""
    client = MagicMock(spec=AuthorizationClient)
    client.set_resource_parents.return_value = ResourceParents(
        type="mock", resource_id="mock", parents=[]
    )
    return client


@pytest.fixture
def mock_flywheel_proxy() -> MagicMock:
    """Create a mock FlywheelProxy."""
    return MagicMock()


def _create_mock_center(center_id: str, is_active: bool = True) -> Mock:
    """Create a mock CenterGroup for testing.

    Args:
        center_id: The center identifier.
        is_active: Whether the center is active.

    Returns:
        A Mock configured as a CenterGroup.
    """
    center = Mock()
    center.id = center_id
    center.adcid = 1
    center.is_active.return_value = is_active

    def create_mock_project(label):
        project = Mock()
        project.id = f"project-{label}"
        project.label = label
        return project

    center.add_project.side_effect = create_mock_project

    portal_info = Mock()
    portal_info.get.return_value = None
    center.get_project_info.return_value = portal_info

    return center


class TestHierarchySeederIntegration:
    """Integration tests for full gear run with hierarchy seeding.

    Validates: Requirements 9.1, 6.1, 6.3
    """

    def test_full_run_seeds_all_resource_types(
        self,
        mock_authorization_client: MagicMock,
        mock_flywheel_proxy: MagicMock,
    ) -> None:
        """Test full gear run with representative StudyModel seeds all
        resources.

        Creates a study with:
        - 1 center (center-01)
        - aggregation datatypes: form, dicom
        - center-scoped dashboards: adrc-reports
        - study-scoped dashboards: study-overview
        - center-scoped pages: enrollment
        - study-scoped pages: study-summary
        - community-scoped pages: community-resources

        Verifies the complete set of set_resource_parents calls.
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
                DatatypeConfig(name="dicom", mode="aggregation"),
            ],
            dashboards=[
                DashboardConfig(name="adrc-reports", level="center"),
                DashboardConfig(name="study-overview", level="study"),
            ],
            pages=[
                PageConfig(name="enrollment", level="center"),
                PageConfig(name="study-summary", level="study"),
                PageConfig(name="community-resources", level="community"),
            ],
            study_type="primary",
            legacy=True,
        )

        seeder = ResourceHierarchySeeder(client=mock_authorization_client)
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy,
            admin_permissions=[],
            hierarchy_seeder=seeder,
        )

        mock_center = _create_mock_center("center-01")

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            mock_group = Mock()
            mock_group.id = "center-01"
            mock_group.label = "Center 01"
            mock_flywheel_proxy.find_group.return_value = mock_group

            visitor.visit_study(study)

        # Collect all set_resource_parents calls
        calls = mock_authorization_client.set_resource_parents.call_args_list

        # Build expected calls as (resource_type, resource_id, parents) tuples
        expected_calls = set()

        # Center-scoped data pipelines (primary study, no suffix)
        # accepted, ingest-form, sandbox-form, ingest-dicom, sandbox-dicom
        # retrospective-form, retrospective-dicom (legacy=True)
        center_pipeline_labels = [
            "accepted",
            "ingest-form",
            "sandbox-form",
            "ingest-dicom",
            "sandbox-dicom",
            "retrospective-form",
            "retrospective-dicom",
        ]
        for label in center_pipeline_labels:
            expected_calls.add(("data_pipeline", label, "test-study", "center-01"))

        # Center-scoped dashboard: adrc-reports
        expected_calls.add(
            ("dashboard", "dashboard-adrc-reports", "test-study", "center-01")
        )

        # Center-scoped page: enrollment
        expected_calls.add(("page", "page-enrollment", "test-study", "center-01"))

        # Study-scoped dashboard: study-overview
        # Study-scoped page: study-summary
        # Community-scoped page: community-resources
        # These are checked separately below

        # Verify center-scoped calls
        actual_center_calls = set()
        actual_study_calls = set()
        actual_community_calls = set()

        for c in calls:
            resource_type = c.kwargs["resource_type"]
            resource_id = c.kwargs["resource_id"]
            parents = c.kwargs["parents"]

            if len(parents) == 2:
                # Center-scoped: parent_study + parent_center
                study_parent = next(
                    p for p in parents if p.structural_relation == "parent_study"
                )
                center_parent = next(
                    p for p in parents if p.structural_relation == "parent_center"
                )
                actual_center_calls.add(
                    (
                        resource_type,
                        resource_id,
                        study_parent.parent_id,
                        center_parent.parent_id,
                    )
                )
            elif len(parents) == 1:
                parent = parents[0]
                if parent.structural_relation == "parent_study":
                    actual_study_calls.add(
                        (resource_type, resource_id, parent.parent_id)
                    )
                elif parent.structural_relation == "parent_community":
                    actual_community_calls.add(
                        (resource_type, resource_id, parent.parent_id)
                    )

        # Assert center-scoped resources
        assert expected_calls == actual_center_calls

        # Assert study-scoped resources
        expected_study_calls = {
            ("dashboard", "dashboard-study-overview", "test-study"),
            ("page", "page-study-summary", "test-study"),
        }
        assert expected_study_calls == actual_study_calls

        # Assert community-scoped resources
        expected_community_calls = {
            ("page", "page-community-resources", "nacc"),
        }
        assert expected_community_calls == actual_community_calls

    def test_seeding_happens_within_same_execution(
        self,
        mock_authorization_client: MagicMock,
        mock_flywheel_proxy: MagicMock,
    ) -> None:
        """Verify seeding happens within the same gear execution as project
        creation.

        The seeder calls should happen during visit_study, not requiring a
        separate invocation.

        Validates: Requirement 9.1
        """
        study = StudyModel(
            name="Simple Study",  # pyright: ignore[reportCallIssue]
            study_id="simple",
            centers=["center-01"],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
            ],
            dashboards=[
                DashboardConfig(name="reports", level="center"),
            ],
            pages=[
                PageConfig(name="status", level="center"),
            ],
            study_type="primary",
            legacy=False,
        )

        seeder = ResourceHierarchySeeder(client=mock_authorization_client)
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy,
            admin_permissions=[],
            hierarchy_seeder=seeder,
        )

        mock_center = _create_mock_center("center-01")

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            mock_group = Mock()
            mock_group.id = "center-01"
            mock_group.label = "Center 01"
            mock_flywheel_proxy.find_group.return_value = mock_group

            # Before visit_study, no calls should have been made
            assert mock_authorization_client.set_resource_parents.call_count == 0

            visitor.visit_study(study)

            # After visit_study, calls should have been made
            assert mock_authorization_client.set_resource_parents.call_count > 0

    def test_idempotent_execution_produces_identical_calls(
        self,
        mock_authorization_client: MagicMock,
        mock_flywheel_proxy: MagicMock,
    ) -> None:
        """Running the visitor twice produces identical set_resource_parents
        calls.

        Validates: Requirements 6.1, 6.3
        """
        study = StudyModel(
            name="Idempotent Study",  # pyright: ignore[reportCallIssue]
            study_id="idem-study",
            centers=["center-01"],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
            ],
            dashboards=[
                DashboardConfig(name="reports", level="center"),
                DashboardConfig(name="overview", level="study"),
            ],
            pages=[
                PageConfig(name="enrollment", level="center"),
                PageConfig(name="summary", level="study"),
                PageConfig(name="community-info", level="community"),
            ],
            study_type="primary",
            legacy=True,
        )

        mock_center = _create_mock_center("center-01")

        def run_once() -> list:
            """Run the visitor once and return the call args list."""
            client = MagicMock(spec=AuthorizationClient)
            client.set_resource_parents.return_value = ResourceParents(
                type="mock", resource_id="mock", parents=[]
            )

            seeder = ResourceHierarchySeeder(client=client)
            visitor = StudyMappingVisitor(
                flywheel_proxy=mock_flywheel_proxy,
                admin_permissions=[],
                hierarchy_seeder=seeder,
            )

            with patch(
                "projects.study_mapping.CenterGroup.create_from_group_adaptor",
                return_value=mock_center,
            ):
                mock_group = Mock()
                mock_group.id = "center-01"
                mock_group.label = "Center 01"
                mock_flywheel_proxy.find_group.return_value = mock_group

                visitor.visit_study(study)

            return client.set_resource_parents.call_args_list

        first_run_calls = run_once()
        second_run_calls = run_once()

        # Both runs should produce the same number of calls
        assert len(first_run_calls) == len(second_run_calls)

        # Both runs should produce identical call arguments
        for first_call, second_call in zip(
            first_run_calls, second_run_calls, strict=False
        ):
            assert first_call == second_call

    def test_affiliated_study_with_suffix(
        self,
        mock_authorization_client: MagicMock,
        mock_flywheel_proxy: MagicMock,
    ) -> None:
        """Test affiliated study appends study_id suffix to resource IDs.

        Validates: Requirements 1.2, 2.2, 3.2, 4.2, 5.2
        """
        study = StudyModel(
            name="NACC FTLD",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[
                {
                    "center-id": "center-01",
                    "enrollment-pattern": "separate",
                    "pipeline-adcid": 1,
                }
            ],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
            ],
            dashboards=[
                DashboardConfig(name="reports", level="center"),
                DashboardConfig(name="overview", level="study"),
            ],
            pages=[
                PageConfig(name="enrollment", level="center"),
                PageConfig(name="summary", level="study"),
                PageConfig(name="community-info", level="community"),
            ],
            study_type="affiliated",
            legacy=True,
        )

        seeder = ResourceHierarchySeeder(client=mock_authorization_client)
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy,
            admin_permissions=[],
            hierarchy_seeder=seeder,
        )

        mock_center = _create_mock_center("center-01")

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            mock_group = Mock()
            mock_group.id = "center-01"
            mock_group.label = "Center 01"
            mock_flywheel_proxy.find_group.return_value = mock_group

            visitor.visit_study(study)

        calls = mock_authorization_client.set_resource_parents.call_args_list

        # Extract all resource_ids
        resource_ids = [c.kwargs["resource_id"] for c in calls]

        # All resource IDs for affiliated study should have -nacc-ftld suffix
        for resource_id in resource_ids:
            assert resource_id.endswith("-nacc-ftld"), (
                f"Expected suffix '-nacc-ftld' on resource_id '{resource_id}'"
            )

    def test_multiple_centers(
        self,
        mock_authorization_client: MagicMock,
        mock_flywheel_proxy: MagicMock,
    ) -> None:
        """Test study with multiple centers seeds hierarchy for each center.

        Validates: Requirements 9.1, 1.1, 2.1
        """
        study = StudyModel(
            name="Multi Center Study",  # pyright: ignore[reportCallIssue]
            study_id="multi",
            centers=["center-01", "center-02"],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
            ],
            dashboards=[
                DashboardConfig(name="reports", level="center"),
            ],
            pages=[
                PageConfig(name="enrollment", level="center"),
            ],
            study_type="primary",
            legacy=False,
        )

        seeder = ResourceHierarchySeeder(client=mock_authorization_client)
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy,
            admin_permissions=[],
            hierarchy_seeder=seeder,
        )

        mock_center_01 = _create_mock_center("center-01")
        mock_center_02 = _create_mock_center("center-02")

        center_map = {
            "center-01": mock_center_01,
            "center-02": mock_center_02,
        }

        def find_group(center_id):
            mock_group = Mock()
            mock_group.id = center_id
            mock_group.label = f"Center {center_id}"
            return mock_group

        mock_flywheel_proxy.find_group.side_effect = find_group

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            side_effect=lambda adaptor: center_map[adaptor.id],
        ):
            visitor.visit_study(study)

        calls = mock_authorization_client.set_resource_parents.call_args_list

        # Collect center-scoped calls by center_id
        center_01_calls = []
        center_02_calls = []

        for c in calls:
            parents = c.kwargs["parents"]
            if len(parents) == 2:
                center_parent = next(
                    (p for p in parents if p.structural_relation == "parent_center"),
                    None,
                )
                if center_parent:
                    if center_parent.parent_id == "center-01":
                        center_01_calls.append(c)
                    elif center_parent.parent_id == "center-02":
                        center_02_calls.append(c)

        # Both centers should have pipeline + dashboard + page seeded
        # For each center: accepted, ingest-form, sandbox-form,
        #   dashboard-reports, page-enrollment
        assert len(center_01_calls) == 5
        assert len(center_02_calls) == 5

    def test_inactive_center_skips_dashboards_and_pages(
        self,
        mock_authorization_client: MagicMock,
        mock_flywheel_proxy: MagicMock,
    ) -> None:
        """Test that inactive centers skip dashboard and page seeding.

        Validates: Requirement 2.3
        """
        study = StudyModel(
            name="Inactive Center Study",  # pyright: ignore[reportCallIssue]
            study_id="inactive-test",
            centers=["center-01"],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
            ],
            dashboards=[
                DashboardConfig(name="reports", level="center"),
            ],
            pages=[
                PageConfig(name="enrollment", level="center"),
            ],
            study_type="primary",
            legacy=False,
        )

        seeder = ResourceHierarchySeeder(client=mock_authorization_client)
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy,
            admin_permissions=[],
            hierarchy_seeder=seeder,
        )

        mock_center = _create_mock_center("center-01", is_active=False)

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            mock_group = Mock()
            mock_group.id = "center-01"
            mock_group.label = "Center 01"
            mock_flywheel_proxy.find_group.return_value = mock_group

            visitor.visit_study(study)

        calls = mock_authorization_client.set_resource_parents.call_args_list

        # Inactive center should still get pipeline seeding (accepted is
        # always created) but NOT dashboard or page seeding
        resource_types_and_ids = [
            (c.kwargs["resource_type"], c.kwargs["resource_id"]) for c in calls
        ]

        # Should NOT have center-scoped dashboards or pages
        assert ("dashboard", "dashboard-reports") not in resource_types_and_ids
        assert ("page", "page-enrollment") not in resource_types_and_ids
