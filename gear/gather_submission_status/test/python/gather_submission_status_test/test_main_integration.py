"""Integration tests for end-to-end main.run() flow.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 4.1 /
Property 3: Reload Failure Isolation
"""

import io
from csv import DictWriter
from typing import Any
from unittest.mock import Mock, patch

from gather_submission_status_app.main import run


def _create_mock_file_entry(
    name: str,
    info: dict[str, Any] | None = None,
    reload_side_effect: Exception | None = None,
) -> Mock:
    """Create a mock FileEntry with .name, .info, and .reload() method."""
    file_entry = Mock()
    file_entry.name = name
    file_entry.info = info

    if reload_side_effect:
        file_entry.reload.side_effect = reload_side_effect
    else:
        # reload returns itself by default (already populated)
        file_entry.reload.return_value = file_entry

    return file_entry


def _create_mock_clustering_visitor(
    pipeline_map: dict[int, list[Any]],
    request_map: dict[int, list[Any]],
) -> Mock:
    """Create a mock StatusRequestClusteringVisitor with pipeline_map and
    request_map."""
    visitor = Mock()
    visitor.pipeline_map = pipeline_map
    visitor.request_map = request_map
    return visitor


def _create_mock_project(label: str, files: list[Mock]) -> Mock:
    """Create a mock ProjectAdaptor with .label and .project.files."""
    project_adaptor = Mock()
    project_adaptor.label = label
    project_adaptor.project = Mock()
    project_adaptor.project.files = files
    return project_adaptor


def _create_mock_request(adcid: int, ptid: str) -> Mock:
    """Create a mock StatusRequest with .adcid and .ptid."""
    request = Mock()
    request.adcid = adcid
    request.ptid = ptid
    return request


def _create_file_visitor_builder() -> Mock:
    """Create a mock file_visitor_builder that returns a visitor with table
    rows."""
    mock_report_row = Mock()
    mock_report_row.model_dump.return_value = {
        "adcid": 1,
        "ptid": "PT001",
        "module": "UDS",
        "visitdate": "2024-01-15",
        "stage": "form-qc-checker",
        "status": "PASS",
    }

    mock_file_visitor = Mock()
    mock_file_visitor.visit_details = Mock()  # non-None
    mock_file_visitor.table = [mock_report_row]

    builder = Mock(return_value=mock_file_visitor)
    return builder


def _create_writer() -> tuple[DictWriter, io.StringIO]:
    """Create a DictWriter backed by a StringIO buffer."""
    output = io.StringIO()
    fieldnames = ["adcid", "ptid", "module", "visitdate", "stage", "status"]
    writer = DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    return writer, output


class TestHappyPath:
    """Test the end-to-end happy path through main.run()."""

    @patch("gather_submission_status_app.main.read_csv")
    def test_valid_rows_produce_correct_output(self, mock_read_csv: Mock) -> None:
        """CSV with valid rows, projects with matching QC files, correct output
        rows written to DictWriter.

        **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 4.1**
        """
        # Setup read_csv to succeed
        mock_read_csv.return_value = True

        # Create file entries matching QC pattern
        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {"state": "PASS", "data": [], "cleared": []}
                }
            }
        }
        mock_file = _create_mock_file_entry(
            name="PT001_2024-01-15_UDS_qc-status.log", info=file_info
        )

        # Create project with the matching file
        project = _create_mock_project(label="ingest-project", files=[mock_file])

        # Create clustering visitor results
        adcid = 1
        request = _create_mock_request(adcid=adcid, ptid="PT001")
        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={adcid: [project]},
            request_map={adcid: [request]},
        )

        # Create file_visitor_builder
        builder = _create_file_visitor_builder()

        # Create writer
        writer, output = _create_writer()
        error_writer = Mock()

        input_file = io.StringIO("adcid,ptid\n1,PT001\n")

        result = run(
            input_file=input_file,
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is True
        # Verify the file was reloaded
        mock_file.reload.assert_called_once()
        # Verify file_visitor_builder was called
        builder.assert_called_once()
        # Verify output was written
        output_content = output.getvalue()
        assert "PT001" in output_content
        assert "PASS" in output_content

    @patch("gather_submission_status_app.main.read_csv")
    def test_multiple_files_all_processed(self, mock_read_csv: Mock) -> None:
        """Multiple matching files in a project all get processed.

        **Validates: Requirements 1.1, 1.2, 1.3**
        """
        mock_read_csv.return_value = True

        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {"state": "PASS", "data": [], "cleared": []}
                }
            }
        }
        mock_file1 = _create_mock_file_entry(
            name="PT001_2024-01-15_UDS_qc-status.log", info=file_info
        )
        mock_file2 = _create_mock_file_entry(
            name="PT002_2024-02-20_UDS_qc-status.log", info=file_info
        )

        project = _create_mock_project(
            label="ingest-project", files=[mock_file1, mock_file2]
        )

        adcid = 1
        requests = [
            _create_mock_request(adcid=adcid, ptid="PT001"),
            _create_mock_request(adcid=adcid, ptid="PT002"),
        ]
        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={adcid: [project]},
            request_map={adcid: requests},
        )

        # Builder returns distinct visitors for each file
        call_count = {"n": 0}

        def builder_side_effect(file: Any, adcid_arg: int) -> Mock:
            call_count["n"] += 1
            mock_row = Mock()
            mock_row.model_dump.return_value = {
                "adcid": adcid_arg,
                "ptid": file.name.split("_")[0],
                "module": "UDS",
                "visitdate": "2024-01-15",
                "stage": "form-qc-checker",
                "status": "PASS",
            }
            visitor = Mock()
            visitor.visit_details = Mock()
            visitor.table = [mock_row]
            return visitor

        builder = Mock(side_effect=builder_side_effect)

        writer, output = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO("adcid,ptid\n1,PT001\n1,PT002\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is True
        assert builder.call_count == 2
        output_content = output.getvalue()
        assert "PT001" in output_content
        assert "PT002" in output_content


class TestMixedPath:
    """Tests where some files succeed and some fail."""

    @patch("gather_submission_status_app.main.read_csv")
    def test_reload_failure_does_not_block_others(self, mock_read_csv: Mock) -> None:
        """Some files reload successfully, one fails — successful files still
        processed, failed file logged.

        **Validates: Requirements 1.4** / Property 3: Reload Failure Isolation
        """
        mock_read_csv.return_value = True

        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {"state": "PASS", "data": [], "cleared": []}
                }
            }
        }

        # File that reloads successfully
        good_file = _create_mock_file_entry(
            name="PT001_2024-01-15_UDS_qc-status.log", info=file_info
        )

        # File that fails to reload
        bad_file = _create_mock_file_entry(
            name="PT002_2024-02-20_UDS_qc-status.log",
            info=file_info,
            reload_side_effect=RuntimeError("API timeout"),
        )

        project = _create_mock_project(
            label="ingest-project", files=[good_file, bad_file]
        )

        adcid = 1
        requests = [
            _create_mock_request(adcid=adcid, ptid="PT001"),
            _create_mock_request(adcid=adcid, ptid="PT002"),
        ]
        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={adcid: [project]},
            request_map={adcid: requests},
        )

        builder = _create_file_visitor_builder()

        writer, output = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO("adcid,ptid\n1,PT001\n1,PT002\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is True
        # The good file should still be processed
        good_file.reload.assert_called_once()
        builder.assert_called_once()
        output_content = output.getvalue()
        assert "PT001" in output_content


class TestEmptyProject:
    """Tests where projects have no matching files."""

    @patch("gather_submission_status_app.main.read_csv")
    def test_no_matching_files_returns_true(self, mock_read_csv: Mock) -> None:
        """Empty project (no matching files): no output rows, returns True.

        **Validates: Requirements 1.1**
        """
        mock_read_csv.return_value = True

        # Only non-matching files in the project
        non_matching_file = _create_mock_file_entry(name="random_data.csv", info=None)

        project = _create_mock_project(
            label="ingest-project", files=[non_matching_file]
        )

        adcid = 1
        request = _create_mock_request(adcid=adcid, ptid="PT001")
        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={adcid: [project]},
            request_map={adcid: [request]},
        )

        builder = Mock()
        writer, output = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO("adcid,ptid\n1,PT001\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is True
        # No file processing should have happened
        builder.assert_not_called()
        # Output should only contain the header
        lines = output.getvalue().strip().split("\n")
        assert len(lines) == 1  # header only


class TestClusteringFailure:
    """Tests where CSV clustering fails."""

    @patch("gather_submission_status_app.main.read_csv")
    def test_bad_csv_returns_false(self, mock_read_csv: Mock) -> None:
        """Clustering failure (bad CSV): returns False, no file processing
        attempted.

        **Validates: Requirements 4.1**
        """
        mock_read_csv.return_value = False

        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={}, request_map={}
        )
        builder = Mock()
        writer, _ = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO("bad,csv\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is False
        builder.assert_not_called()


class TestReloadWorkersParameter:
    """Tests that reload_workers is properly passed through."""

    @patch("gather_submission_status_app.main.ThreadPoolExecutor")
    @patch("gather_submission_status_app.main.read_csv")
    def test_reload_workers_passed_to_executor(
        self, mock_read_csv: Mock, mock_executor_cls: Mock
    ) -> None:
        """Verify reload_workers parameter is passed to ThreadPoolExecutor.

        **Validates: Requirements 1.2**
        """
        mock_read_csv.return_value = True

        # Setup the mock executor context manager
        mock_pool = Mock()
        mock_executor_cls.return_value.__enter__ = Mock(return_value=mock_pool)
        mock_executor_cls.return_value.__exit__ = Mock(return_value=False)
        mock_pool.submit = Mock()

        # Create a project with no matching files so we don't need full
        # as_completed mocking
        project = _create_mock_project(label="ingest-project", files=[])

        adcid = 1
        request = _create_mock_request(adcid=adcid, ptid="PT001")
        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={adcid: [project]},
            request_map={adcid: [request]},
        )

        builder = Mock()
        writer, _ = _create_writer()
        error_writer = Mock()

        run(
            input_file=io.StringIO("adcid,ptid\n1,PT001\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=5,
        )

        mock_executor_cls.assert_called_once_with(max_workers=5)

    @patch("gather_submission_status_app.main.read_csv")
    def test_reload_workers_1_deterministic_ordering(self, mock_read_csv: Mock) -> None:
        """With reload_workers=1, processing is deterministic (single thread).

        **Validates: Requirements 1.2**
        """
        mock_read_csv.return_value = True

        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {"state": "PASS", "data": [], "cleared": []}
                }
            }
        }
        mock_file = _create_mock_file_entry(
            name="PT001_2024-01-15_UDS_qc-status.log", info=file_info
        )

        project = _create_mock_project(label="ingest-project", files=[mock_file])

        adcid = 1
        request = _create_mock_request(adcid=adcid, ptid="PT001")
        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={adcid: [project]},
            request_map={adcid: [request]},
        )

        builder = _create_file_visitor_builder()
        writer, _output = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO("adcid,ptid\n1,PT001\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is True
        mock_file.reload.assert_called_once()


class TestEmptyPipelineMap:
    """Tests edge case where pipeline_map is empty."""

    @patch("gather_submission_status_app.main.read_csv")
    def test_empty_pipeline_map_returns_false(self, mock_read_csv: Mock) -> None:
        """If clustering produces no projects, run returns False.

        **Validates: Requirements 1.1**
        """
        mock_read_csv.return_value = True

        clustering_visitor = _create_mock_clustering_visitor(
            pipeline_map={}, request_map={}
        )

        builder = Mock()
        writer, _ = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO("adcid,ptid\n1,PT001\n"),
            modules={"UDS"},
            clustering_visitor=clustering_visitor,
            file_visitor_builder=builder,
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is False
        builder.assert_not_called()
