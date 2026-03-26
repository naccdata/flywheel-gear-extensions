"""Property-based test for backward compatible project structure.

This module tests that studies using the old configuration format
(study-level mode field with datatypes as list of strings) produce the
same project structure as before the refactoring.
"""

from unittest.mock import Mock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from projects.study import StudyModel
from projects.study_mapping import StudyMappingVisitor

# Strategy for generating valid datatype names
datatype_names = st.text(
    min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))
)

# Strategy for generating valid modes
modes = st.sampled_from(["aggregation", "distribution"])

# Strategy for generating study types
study_types = st.sampled_from(["primary", "affiliated"])


# Feature: study-model-flexible-configuration
# Property 18: Backward Compatible Project Structure
@given(
    study_mode=modes,
    datatypes=st.lists(datatype_names, min_size=1, max_size=5, unique=True),
    legacy=st.booleans(),
)
@settings(max_examples=100)
def test_backward_compatible_project_structure(study_mode, datatypes, legacy):
    """For any study using the old configuration format (study-level mode), the
    Project_Management should produce the same project structure as it did
    before the refactoring.

    Property 18: Backward Compatible Project Structure
    Validates: Requirements 7.4

    This property verifies that:
    - Old format configurations are automatically migrated to new format
    - The resulting project structure is identical to pre-refactoring behavior
    - All project types are created correctly based on the study-level mode
    """
    # Determine study type based on mode (primary studies must be aggregation)
    study_type = "primary" if study_mode == "aggregation" else "affiliated"

    # Create study with old format (study-level mode, datatypes as list of
    # strings)
    study = StudyModel(
        name="Legacy Study",  # pyright: ignore[reportCallIssue]
        study_id="legacy-study",
        centers=[
            {
                "center-id": "center-01",
                "enrollment-pattern": "separate",
                "pipeline-adcid": 1,
            }
        ],
        datatypes=datatypes,  # Old format: list of strings
        mode=study_mode,  # Old format: study-level mode
        study_type=study_type,
        legacy=legacy,
    )

    # Create mock flywheel proxy
    mock_flywheel_proxy = Mock()

    # Create visitor
    visitor = StudyMappingVisitor(
        flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
    )

    # Create mock group adaptor
    mock_group = Mock()
    mock_group.id = "center-01"
    mock_group.label = "Center 01"
    mock_flywheel_proxy.find_group.return_value = mock_group

    # Create mock center
    mock_center = Mock()
    mock_center.id = "center-01"
    mock_center.adcid = 1
    mock_center.is_active.return_value = True
    mock_center.get_project_info.return_value = Mock()
    mock_center.get_project_info.return_value.get.return_value = None

    # Track created projects
    created_projects = []

    def track_project_creation(label):
        project = Mock()
        project.id = f"project-{label}"
        project.label = label
        created_projects.append(label)
        return project

    mock_center.add_project.side_effect = track_project_creation

    # Mock CenterGroup.create_from_group_adaptor and StudyGroup.create
    with (
        patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ),
        patch("projects.study_mapping.StudyGroup.create"),
    ):
        visitor.visit_study(study)

    # Determine project suffix based on study type
    # Primary studies have no suffix, affiliated studies have "-{study_id}"
    project_suffix = "" if study_type == "primary" else "-legacy-study"

    # Verify the project structure matches expected behavior based on mode
    if study_mode == "aggregation":
        # Aggregation mode should create:
        # 1. Accepted project (shared across all datatypes)
        # 2. Ingest project for each datatype
        # 3. Sandbox project for each datatype
        # 4. Retrospective project for each datatype (if legacy=True)

        # Verify accepted project exists
        assert f"accepted{project_suffix}" in created_projects, (
            "Aggregation mode study should have accepted project"
        )

        # Verify each datatype has ingest and sandbox projects
        for dt in datatypes:
            dt_lower = dt.lower()

            assert f"ingest-{dt_lower}{project_suffix}" in created_projects, (
                f"Aggregation datatype '{dt}' should have ingest project"
            )

            assert f"sandbox-{dt_lower}{project_suffix}" in created_projects, (
                f"Aggregation datatype '{dt}' should have sandbox project"
            )

            # Verify retrospective project if legacy=True
            if legacy:
                assert (
                    f"retrospective-{dt_lower}{project_suffix}" in created_projects
                ), (
                    f"Legacy aggregation datatype '{dt}' should have "
                    f"retrospective project"
                )

            # Verify NO distribution projects
            assert f"distribution-{dt_lower}{project_suffix}" not in created_projects, (
                f"Aggregation datatype '{dt}' should NOT have distribution project"
            )

    elif study_mode == "distribution":
        # Distribution mode should create:
        # 1. Distribution project for each datatype in center groups
        # 2. Ingest project for each datatype in study group (not tracked here)

        # Verify each datatype has distribution project
        for dt in datatypes:
            dt_lower = dt.lower()

            assert f"distribution-{dt_lower}{project_suffix}" in created_projects, (
                f"Distribution datatype '{dt}' should have distribution project"
            )

            # Verify NO aggregation projects
            assert f"ingest-{dt_lower}{project_suffix}" not in created_projects, (
                f"Distribution datatype '{dt}' should NOT have ingest project "
                f"in center group"
            )

            assert f"sandbox-{dt_lower}{project_suffix}" not in created_projects, (
                f"Distribution datatype '{dt}' should NOT have sandbox project"
            )

        # Verify NO accepted project
        assert f"accepted{project_suffix}" not in created_projects, (
            "Distribution mode study should NOT have accepted project"
        )

    # Verify that the study was migrated to new format internally
    # (all datatypes should have the study-level mode applied)
    datatype_configs = study.get_datatype_configs()
    assert len(datatype_configs) == len(datatypes), (
        f"Expected {len(datatypes)} datatype configs, got {len(datatype_configs)}"
    )

    for config in datatype_configs:
        assert config.mode == study_mode, (
            f"Expected all datatypes to have mode '{study_mode}', "
            f"but datatype '{config.name}' has mode '{config.mode}'"
        )
