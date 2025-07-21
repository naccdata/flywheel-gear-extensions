"""Tests the redcap project input object for updating center info."""

from centers.center_group import REDCapFormProjectMetadata, REDCapProjectInput
from pydantic import ValidationError


# pylint: disable=too-few-public-methods
class TestREDCapProjectInput:
    """Test REDCap Project Input."""

    # pylint: disable=no-self-use
    def test_redcap_project_input(self):
        """Test REDCap Project Input."""
        project_model = REDCapProjectInput(
            center_id="test",
            study_id="test",
            project_label="test",
            projects=[
                REDCapFormProjectMetadata(redcap_pid=12345, label="test", report_id=22)
            ],
        )
        project_dump = project_model.model_dump(by_alias=True, exclude_none=True)
        assert "center-id" in project_dump
        assert "study-id" in project_dump
        assert "project-label" in project_dump
        assert project_dump["projects"][0]["redcap-pid"] == 12345

        try:
            model_object = REDCapProjectInput.model_validate(project_dump)
            assert model_object == project_model
        except ValidationError as error:
            assert False, error  # noqa: B011
