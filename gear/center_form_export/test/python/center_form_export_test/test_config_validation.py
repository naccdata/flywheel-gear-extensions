"""Property test for blank config field rejection.

Feature: center-form-export, Property 1: Blank config fields are rejected
Validates: Requirements 2.9
"""

import pytest
from center_form_export_app.main import ProjectModeConfig
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

# Strategy for whitespace-only strings
whitespace_strategy = st.from_regex(r"^[\s]*$", fullmatch=True).filter(
    lambda s: not s.strip()
)


class TestBlankConfigRejection:
    """Property tests for ProjectModeConfig blank field rejection."""

    @given(blank_value=whitespace_strategy)
    @settings(max_examples=100)
    def test_blank_group_id_rejected(self, blank_value: str):
        """Blank group_id raises ValidationError.

        **Validates: Requirements 2.9**
        """
        with pytest.raises(ValidationError):
            ProjectModeConfig(
                group_id=blank_value,
                project_name="valid-project",
                modules={"UDS"},
                info_paths=["forms.json"],
                study_id="adrc",
            )

    @given(blank_value=whitespace_strategy)
    @settings(max_examples=100)
    def test_blank_project_name_rejected(self, blank_value: str):
        """Blank project_name raises ValidationError.

        **Validates: Requirements 2.9**
        """
        with pytest.raises(ValidationError):
            ProjectModeConfig(
                group_id="valid-group",
                project_name=blank_value,
                modules={"UDS"},
                info_paths=["forms.json"],
                study_id="adrc",
            )
