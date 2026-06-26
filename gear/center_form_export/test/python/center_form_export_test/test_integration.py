"""Integration tests for the Center Form Export gear.

Tests CenterFormExportVisitor.run with mocked Flywheel SDK components
(group resolution, project resolution, subject iteration).

Validates: Requirements 8.1, 8.3
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from center_form_export_app.run import CenterFormExportVisitor
from gear_execution.gear_execution import GearExecutionError


def create_visitor(
    mock_client: MagicMock,
    group_id: str = "test-group",
    project_name: str = "test-project",
    modules: set[str] | None = None,
    info_paths: list[str] | None = None,
    study_id: str = "adrc",
    formver_split: bool = False,
) -> CenterFormExportVisitor:
    """Factory to create a CenterFormExportVisitor with test defaults."""
    if modules is None:
        modules = {"UDS"}
    if info_paths is None:
        info_paths = ["forms.json"]

    return CenterFormExportVisitor(
        client=mock_client,
        group_id=group_id,
        project_name=project_name,
        info_paths=info_paths,
        modules=modules,
        study_id=study_id,
        formver_split=formver_split,
    )


def create_mock_subject(label: str, subject_id: str) -> MagicMock:
    """Factory to create a mock Flywheel subject."""
    subject = MagicMock()
    subject.label = label
    subject.id = subject_id
    return subject


class TestErrorHandling:
    """Tests for graceful handling of missing groups, projects, and subjects.

    Validates: Requirements 3.4, 3.5, 3.6
    """

    def test_group_not_found(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """When proxy.find_group returns None, raise GearExecutionError."""
        mock_proxy.find_group.return_value = None

        visitor = create_visitor(mock_client, group_id="nonexistent-group")

        with pytest.raises(
            GearExecutionError, match="Group not found: nonexistent-group"
        ):
            visitor.run(mock_context)

        mock_context.open_output.assert_not_called()

    def test_project_not_found(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """When group is found but project is not, raise GearExecutionError."""
        mock_group = MagicMock()
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = None

        visitor = create_visitor(
            mock_client,
            group_id="test-group",
            project_name="nonexistent-project",
        )

        with pytest.raises(
            GearExecutionError, match="Project not found: nonexistent-project"
        ):
            visitor.run(mock_context)

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


class TestOutput:
    """Tests for CSV output file production.

    Validates: Requirements 5.1, 5.2, 5.3
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

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.content = "header1,header2\nval1,val2\n"
            mock_gatherer.split_by_formver = False
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

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "FTLD"
            mock_gatherer.content = "col1\ndata1\n"
            mock_gatherer.split_by_formver = False
            mock_gatherer_cls.return_value = mock_gatherer

            with patch("center_form_export_app.run.date") as mock_date:
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
        mock_uds_gatherer.split_by_formver = False

        mock_ftld_gatherer = MagicMock()
        mock_ftld_gatherer.module_name = "FTLD"
        mock_ftld_gatherer.content = ""  # Empty - no data
        mock_ftld_gatherer.split_by_formver = False

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:

            def create_gatherer(proxy, module_name, info_paths, **kwargs):
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


class TestFormverSplit:
    """Tests for formver_split=True output behavior.

    When formver_split is enabled, the gear produces one CSV per
    (module, formver) pair instead of one CSV per module.
    """

    def _build_visitor(self, mock_client: MagicMock):
        return CenterFormExportVisitor(
            client=mock_client,
            group_id="test-group",
            project_name="test-project",
            info_paths=["forms.json"],
            modules={"UDS"},
            study_id="adrc",
            formver_split=True,
        )

    def test_produces_one_file_per_formver_bucket(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """A gatherer with two formver buckets produces two output files."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_project.label = "test-project"
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = self._build_visitor(mock_client)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.split_by_formver = True
            mock_gatherer.content_by_formver = {
                "v3": "naccid\nNACC000001\n",
                "v4": "naccid,extra\nNACC000002,x\n",
            }
            mock_gatherer_cls.return_value = mock_gatherer

            with patch("center_form_export_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2024-01-15"
                visitor.run(mock_context)

        assert mock_context.open_output.call_count == 2
        filenames = sorted(mock_context.output_files.keys())
        assert filenames == [
            "adrc-UDS-v3-2024-01-15.csv",
            "adrc-UDS-v4-2024-01-15.csv",
        ]
        # Each output file contains its bucket's content
        assert mock_context.output_files["adrc-UDS-v3-2024-01-15.csv"] == (
            "naccid\nNACC000001\n"
        )
        assert mock_context.output_files["adrc-UDS-v4-2024-01-15.csv"] == (
            "naccid,extra\nNACC000002,x\n"
        )

    def test_empty_buckets_are_skipped(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """Buckets with empty content do not produce files."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_project.label = "test-project"
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = self._build_visitor(mock_client)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.split_by_formver = True
            mock_gatherer.content_by_formver = {
                "v3": "naccid\nNACC000001\n",
                "v4": "",  # empty
            }
            mock_gatherer_cls.return_value = mock_gatherer

            visitor.run(mock_context)

        assert mock_context.open_output.call_count == 1
        filename = next(iter(mock_context.output_files.keys()))
        assert "v3" in filename and "v4" not in filename

    def test_gatherer_with_no_buckets_logs_warning(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """A gatherer that gathered no rows produces no files and logs."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_project.label = "test-project"
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = self._build_visitor(mock_client)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.split_by_formver = True
            mock_gatherer.content_by_formver = {}
            mock_gatherer_cls.return_value = mock_gatherer

            with caplog.at_level(logging.WARNING):
                visitor.run(mock_context)

        mock_context.open_output.assert_not_called()
        assert "skipping output for module UDS" in caplog.text
