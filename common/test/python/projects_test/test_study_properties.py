"""Property-based tests for StudyModel using Hypothesis.

These tests validate universal properties that should hold across all
valid inputs.
"""

from unittest.mock import Mock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from projects.study import DatatypeConfig, StudyModel
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
# Property 1: Datatype Mode Storage and Retrieval
@given(
    datatypes=st.lists(
        st.tuples(datatype_names, modes),
        min_size=1,
        max_size=5,
        unique_by=lambda x: x[0],  # Unique datatype names
    )
)
@settings(max_examples=100)
def test_datatype_mode_storage_and_retrieval(datatypes):
    """For any StudyModel with datatype configs, retrieving mode should return
    configured mode.

    Property 1: Datatype Mode Storage and Retrieval
    Validates: Requirements 1.1, 1.5
    """
    # Create study with datatype configurations
    study_dict = {
        "study": "Test Study",
        "study-id": "test",
        "centers": ["ac"],
        "datatypes": [{"name": name, "mode": mode} for name, mode in datatypes],
        "study-type": "affiliated",  # Use affiliated to allow any mode
    }

    study = StudyModel.create(study_dict)

    # Verify each datatype's mode can be retrieved correctly
    for name, expected_mode in datatypes:
        actual_mode = study.get_datatype_mode(name)
        assert actual_mode == expected_mode, (
            f"Expected mode '{expected_mode}' for datatype '{name}', "
            f"but got '{actual_mode}'"
        )


# Feature: study-model-flexible-configuration
# Property 3: Backward Compatible Mode Field
@given(
    study_mode=modes,
    datatypes=st.lists(datatype_names, min_size=1, max_size=5, unique=True),
)
@settings(max_examples=100)
def test_backward_compatible_mode_field(study_mode, datatypes):
    """For any StudyModel with study-level mode, all datatypes should have that
    mode.

    Property 3: Backward Compatible Mode Field
    Validates: Requirements 1.3, 7.1
    """
    # Create study with old format (study-level mode)
    study_dict = {
        "study": "Legacy Study",
        "study-id": "legacy",
        "centers": ["ac"],
        "mode": study_mode,
        "datatypes": datatypes,
        "study-type": "affiliated" if study_mode == "distribution" else "primary",
    }

    study = StudyModel.create(study_dict)

    # Verify all datatypes have the study-level mode applied
    datatype_configs = study.get_datatype_configs()
    assert len(datatype_configs) == len(datatypes), (
        f"Expected {len(datatypes)} datatype configs, got {len(datatype_configs)}"
    )

    for config in datatype_configs:
        assert config.mode == study_mode, (
            f"Expected all datatypes to have mode '{study_mode}', "
            f"but datatype '{config.name}' has mode '{config.mode}'"
        )

    # Verify get_datatype_mode returns correct mode for each datatype
    for datatype_name in datatypes:
        actual_mode = study.get_datatype_mode(datatype_name)
        assert actual_mode == study_mode, (
            f"Expected mode '{study_mode}' for datatype '{datatype_name}', "
            f"but got '{actual_mode}'"
        )


# Additional property test: get_datatypes_by_mode consistency
@given(
    datatypes=st.lists(
        st.tuples(datatype_names, modes),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x[0],
    )
)
@settings(max_examples=100)
def test_get_datatypes_by_mode_consistency(datatypes):
    """Verify get_datatypes_by_mode returns correct subsets.

    This property ensures that:
    1. All datatypes are accounted for when querying by mode
    2. No datatype appears in both aggregation and distribution lists
    3. The union of both mode lists equals all datatypes
    """
    study_dict = {
        "study": "Test Study",
        "study-id": "test",
        "centers": ["ac"],
        "datatypes": [{"name": name, "mode": mode} for name, mode in datatypes],
        "study-type": "affiliated",
    }

    study = StudyModel.create(study_dict)

    # Get datatypes by mode
    agg_datatypes = study.get_datatypes_by_mode("aggregation")
    dist_datatypes = study.get_datatypes_by_mode("distribution")

    # Verify no overlap
    assert set(agg_datatypes).isdisjoint(set(dist_datatypes)), (
        "Datatypes should not appear in both aggregation and distribution lists"
    )

    # Verify union equals all datatypes
    all_datatype_names = {name for name, _ in datatypes}
    retrieved_names = set(agg_datatypes) | set(dist_datatypes)
    assert all_datatype_names == retrieved_names, (
        f"Union of mode-filtered datatypes should equal all datatypes. "
        f"Expected: {all_datatype_names}, Got: {retrieved_names}"
    )

    # Verify each list contains only datatypes with the correct mode
    for name in agg_datatypes:
        mode = study.get_datatype_mode(name)
        assert mode == "aggregation", (
            f"Datatype '{name}' in aggregation list has mode '{mode}'"
        )

    for name in dist_datatypes:
        mode = study.get_datatype_mode(name)
        assert mode == "distribution", (
            f"Datatype '{name}' in distribution list has mode '{mode}'"
        )


# Property test: Primary study validation
@given(
    datatypes=st.lists(
        st.tuples(datatype_names, modes),
        min_size=1,
        max_size=5,
        unique_by=lambda x: x[0],
    )
)
@settings(max_examples=100)
def test_primary_study_validation_property(datatypes):
    """Primary studies should only accept all-aggregation datatypes.

    This property verifies that:
    - If all datatypes are aggregation, primary study is valid
    - If any datatype is distribution, primary study is invalid
    """
    from projects.study import StudyError

    study_dict = {
        "study": "Primary Study",
        "study-id": "primary",
        "centers": ["ac"],
        "datatypes": [{"name": name, "mode": mode} for name, mode in datatypes],
        "study-type": "primary",
    }

    # Check if all datatypes are aggregation
    all_aggregation = all(mode == "aggregation" for _, mode in datatypes)

    if all_aggregation:
        # Should succeed
        study = StudyModel.create(study_dict)
        assert study.study_type == "primary"
    else:
        # Should fail
        try:
            StudyModel.create(study_dict)
            raise AssertionError(
                "Expected StudyError for primary study with distribution datatypes"
            )
        except StudyError as e:
            # Verify error message mentions the issue
            assert "Primary study cannot have datatype" in str(
                e
            ) or "mode of a primary study must be aggregation" in str(e)


# Feature: study-model-flexible-configuration
# Property 16: Mixed Mode Independence
@given(
    agg_datatypes=st.lists(
        datatype_names,
        min_size=1,
        max_size=3,
        unique=True,
    ),
    dist_datatypes=st.lists(
        datatype_names,
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_mixed_mode_independence(agg_datatypes, dist_datatypes):
    """For any study with both aggregation and distribution mode datatypes, the
    Project_Management should create the correct project types for each
    datatype based on its individual mode.

    Property 16: Mixed Mode Independence
    Validates: Requirements 5.3

    This property verifies that:
    - Aggregation datatypes get ingest, sandbox, and accepted projects in
      center groups
    - Distribution datatypes get distribution projects in center groups and
      ingest projects in study group
    - Both types coexist independently in the same study
    """
    # Ensure no overlap between aggregation and distribution datatypes
    if set(agg_datatypes) & set(dist_datatypes):
        return  # Skip if there's overlap

    # Create study with mixed modes
    study = StudyModel(
        name="Mixed Mode Study",  # pyright: ignore[reportCallIssue]
        study_id="mixed-study",
        centers=[
            {
                "center-id": "center-01",
                "enrollment-pattern": "separate",
                "pipeline-adcid": 1,
            }
        ],
        datatypes=[
            *[DatatypeConfig(name=dt, mode="aggregation") for dt in agg_datatypes],
            *[DatatypeConfig(name=dt, mode="distribution") for dt in dist_datatypes],
        ],
        study_type="affiliated",  # Must be affiliated to allow mixed modes
        legacy=True,
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

    # Verify aggregation datatype projects
    for dt in agg_datatypes:
        # Project labels use lowercase datatype names
        dt_lower = dt.lower()

        # Should have ingest project
        assert f"ingest-{dt_lower}-mixed-study" in created_projects, (
            f"Aggregation datatype '{dt}' should have ingest project"
        )

        # Should have sandbox project
        assert f"sandbox-{dt_lower}-mixed-study" in created_projects, (
            f"Aggregation datatype '{dt}' should have sandbox project"
        )

        # Should NOT have distribution project
        assert f"distribution-{dt_lower}-mixed-study" not in created_projects, (
            f"Aggregation datatype '{dt}' should NOT have distribution project"
        )

    # Verify distribution datatype projects
    for dt in dist_datatypes:
        # Project labels use lowercase datatype names
        dt_lower = dt.lower()

        # Should have distribution project
        assert f"distribution-{dt_lower}-mixed-study" in created_projects, (
            f"Distribution datatype '{dt}' should have distribution project"
        )

        # Should NOT have ingest project (in center group)
        assert f"ingest-{dt_lower}-mixed-study" not in created_projects, (
            f"Distribution datatype '{dt}' should NOT have ingest project "
            f"in center group"
        )

        # Should NOT have sandbox project
        assert f"sandbox-{dt_lower}-mixed-study" not in created_projects, (
            f"Distribution datatype '{dt}' should NOT have sandbox project"
        )

    # Verify accepted project exists (shared across all aggregation datatypes)
    if agg_datatypes:
        assert "accepted-mixed-study" in created_projects, (
            "Study with aggregation datatypes should have accepted project"
        )
