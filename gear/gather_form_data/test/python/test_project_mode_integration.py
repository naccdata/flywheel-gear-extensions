"""Integration tests for project mode end-to-end.

Tests the ProjectModeVisitor.run method with mocked Flywheel SDK
components (group resolution, project resolution, subject iteration).

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 7.1
"""

import logging
from contextlib import contextmanager
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from gather_form_data_app.run import ProjectModeVisitor
from gear_execution.gear_execution import ClientWrapper


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock ClientWrapper."""
    return MagicMock(spec=ClientWrapper)


@pytest.fixture
def mock_proxy(mock_client: MagicMock) -> MagicMock:
    """Create a mock FlywheelProxy returned by the client."""
    proxy = MagicMock()
    mock_client.get_proxy.return_value = proxy
    return proxy


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock GearContext with open_output support."""
    context = MagicMock()

    @contextmanager
    def fake_open_output(filename, mode="w", encoding="utf-8"):
        buf = StringIO()
        yield buf
        context.output_files[filename] = buf.getvalue()

    context.output_files = {}
    context.open_output.side_effect = fake_open_output
    return context


def create_visitor(
    mock_client: MagicMock,
    group_id: str = "test-group",
    project_name: str = "test-project",
    modules: set[str] | None = None,
    info_paths: list[str] | None = None,
    study_id: str = "adrc",
) -> ProjectModeVisitor:
    """Factory to create a ProjectModeVisitor with test defaults."""
    if modules is None:
        modules = {"UDS"}
    if info_paths is None:
        info_paths = ["forms.json"]

    return ProjectModeVisitor(
        client=mock_client,
        group_id=group_id,
        project_name=project_name,
        info_paths=info_paths,
        modules=modules,
        study_id=study_id,
    )


def create_mock_subject(label: str, subject_id: str) -> MagicMock:
    """Factory to create a mock Flywheel subject."""
    subject = MagicMock()
    subject.label = label
    subject.id = subject_id
    return subject


class TestProjectModeErrorHandling:
    """Tests for graceful handling of missing groups, projects, and subjects.

    Validates: Requirements 4.3, 4.4, 4.5
    """

    def test_group_not_found(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """When proxy.find_group returns None, log error and return."""
        mock_proxy.find_group.return_value = None

        visitor = create_visitor(mock_client, group_id="nonexistent-group")

        with caplog.at_level(logging.ERROR):
            visitor.run(mock_context)

        assert "Group not found: nonexistent-group" in caplog.text
        mock_context.open_output.assert_not_called()

    def test_project_not_found(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """When group is found but project is not, log error and return."""
        mock_group = MagicMock()
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = None

        visitor = create_visitor(
            mock_client,
            group_id="test-group",
            project_name="nonexistent-project",
        )

        with caplog.at_level(logging.ERROR):
            visitor.run(mock_context)

        assert "Project not found: nonexistent-project" in caplog.text
        mock_context.open_output.assert_not_called()

    def test_empty_project(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """When project has no subjects, log warning and return."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.project.subjects.iter.return_value = iter([])
        mock_project.label = "test-project"

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client)

        with caplog.at_level(logging.WARNING):
            visitor.run(mock_context)

        assert "No subjects found" in caplog.text
        mock_context.open_output.assert_not_called()


class TestProjectModeOutput:
    """Tests for CSV output file production.

    Validates: Requirements 4.1, 4.2, 7.1, 7.2
    """

    def test_produces_output(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """When subjects have data, output files are written."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        subjects = [
            create_mock_subject("NACC000001", "sub-001"),
            create_mock_subject("NACC000002", "sub-002"),
        ]
        mock_project.project.subjects.iter.return_value = iter(subjects)
        mock_project.label = "test-project"

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client, modules={"UDS"}, study_id="adrc")

        with patch("gather_form_data_app.run.ModuleDataGatherer") as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.content = "header1,header2\nval1,val2\n"
            mock_gatherer_cls.return_value = mock_gatherer

            visitor.run(mock_context)

        mock_context.open_output.assert_called_once()
        call_args = mock_context.open_output.call_args
        filename = call_args[0][0]
        assert filename.startswith("adrc-UDS-")
        assert filename.endswith(".csv")

    def test_output_filename_format(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """Output filename follows {study_id}-{module}-{date}.csv pattern."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        subjects = [create_mock_subject("NACC000001", "sub-001")]
        mock_project.project.subjects.iter.return_value = iter(subjects)
        mock_project.label = "test-project"

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client, modules={"FTLD"}, study_id="mystudy")

        with patch("gather_form_data_app.run.ModuleDataGatherer") as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "FTLD"
            mock_gatherer.content = "col1\ndata1\n"
            mock_gatherer_cls.return_value = mock_gatherer

            with patch("gather_form_data_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2024-01-15"
                visitor.run(mock_context)

        call_args = mock_context.open_output.call_args
        filename = call_args[0][0]
        assert filename == "mystudy-FTLD-2024-01-15.csv"

    def test_skips_empty_modules(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Only modules with content produce output; empty ones are skipped."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        subjects = [create_mock_subject("NACC000001", "sub-001")]
        mock_project.project.subjects.iter.return_value = iter(subjects)
        mock_project.label = "test-project"

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client, modules={"UDS", "FTLD"}, study_id="adrc")

        mock_uds_gatherer = MagicMock()
        mock_uds_gatherer.module_name = "UDS"
        mock_uds_gatherer.content = "header\ndata\n"

        mock_ftld_gatherer = MagicMock()
        mock_ftld_gatherer.module_name = "FTLD"
        mock_ftld_gatherer.content = ""  # Empty - no data

        with patch("gather_form_data_app.run.ModuleDataGatherer") as mock_gatherer_cls:

            def create_gatherer(proxy, module_name, info_paths):
                if module_name == "UDS":
                    return mock_uds_gatherer
                return mock_ftld_gatherer

            mock_gatherer_cls.side_effect = create_gatherer

            with caplog.at_level(logging.WARNING):
                visitor.run(mock_context)

        # Only UDS should produce output (FTLD has no content)
        assert mock_context.open_output.call_count == 1
        call_args = mock_context.open_output.call_args
        filename = call_args[0][0]
        assert "UDS" in filename

        # Warning should be logged for the empty module
        assert "skipping output for module FTLD" in caplog.text
