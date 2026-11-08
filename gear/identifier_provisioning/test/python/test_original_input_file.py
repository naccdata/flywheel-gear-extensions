"""Tests for locating the original CSV behind a provisioning file."""

from identifier_provisioning_app.run import get_original_input_file
from test_mocks.mock_flywheel import MockFile, MockProjectAdaptor


class TestGetOriginalInputFile:
    """Tests for get_original_input_file."""

    def test_finds_original_for_provisioning_file(self):
        """The provisioning suffix is stripped to find the original CSV."""
        original = MockFile(name="form-enrl.csv")
        project = MockProjectAdaptor(label="ingest", files=[original])

        found = get_original_input_file(
            filename="form-enrl_provisioning.csv", project=project
        )

        assert found is original

    def test_returns_none_when_original_missing(self):
        """Returns None if the original CSV is no longer in the project."""
        project = MockProjectAdaptor(label="ingest")

        assert (
            get_original_input_file(
                filename="form-enrl_provisioning.csv", project=project
            )
            is None
        )

    def test_filename_without_suffix_is_unchanged(self):
        """A name without the suffix is looked up as-is."""
        input_file = MockFile(name="form-enrl.csv")
        project = MockProjectAdaptor(label="ingest", files=[input_file])

        found = get_original_input_file(filename="form-enrl.csv", project=project)

        assert found is input_file

    def test_suffix_only_stripped_from_the_end(self):
        """An embedded occurrence of the suffix is not removed."""
        input_file = MockFile(name="provisioning-form-enrl.csv")
        project = MockProjectAdaptor(label="ingest", files=[input_file])

        found = get_original_input_file(
            filename="provisioning-form-enrl.csv", project=project
        )

        assert found is input_file
