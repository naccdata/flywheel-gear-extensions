"""Tests that requested participants with no QC logs are reported."""

import io
from unittest.mock import Mock, patch

from gather_submission_status_app.main import run, run_consolidated
from gather_submission_status_test.test_main_integration import (
    _create_file_visitor_builder,
    _create_mock_clustering_visitor,
    _create_mock_file_entry,
    _create_mock_project,
    _create_mock_request,
    _create_writer,
)

PASSING_INFO = {
    "qc": {
        "form-qc-checker": {"validation": {"state": "PASS", "data": [], "cleared": []}}
    }
}


def _written_errors(error_writer: Mock) -> list:
    return [call.args[0] for call in error_writer.write.call_args_list]


class TestUnmatchedPtids:
    """Unmatched PTIDs produce a non-fatal error per PTID."""

    @patch("gather_submission_status_app.main.read_csv")
    def test_run_reports_ptid_without_matching_file(self, mock_read_csv: Mock):
        mock_read_csv.return_value = True
        project = _create_mock_project(
            label="ingest-project",
            files=[
                _create_mock_file_entry(
                    name="PT001_2024-01-15_UDS_qc-status.log", info=PASSING_INFO
                )
            ],
        )
        clustering = _create_mock_clustering_visitor(
            pipeline_map={1: [project]},
            request_map={
                1: [
                    _create_mock_request(adcid=1, ptid="PT001"),
                    _create_mock_request(adcid=1, ptid="PT002"),
                ]
            },
        )
        writer, _ = _create_writer()
        error_writer = Mock()

        result = run(
            input_file=io.StringIO(""),
            modules={"UDS"},
            clustering_visitor=clustering,
            file_visitor_builder=_create_file_visitor_builder(),
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert result is True
        errors = _written_errors(error_writer)
        assert [error.ptid for error in errors] == ["PT002"]
        assert errors[0].error_code == "no-qc-logs"
        assert errors[0].error_type == "error"
        assert "ingest-project" in errors[0].message
        assert "UDS" in errors[0].message

    @patch("gather_submission_status_app.main.read_csv")
    def test_run_consolidated_reports_ptid_in_wrong_module(self, mock_read_csv: Mock):
        mock_read_csv.return_value = True
        project = _create_mock_project(
            label="ingest-project",
            files=[
                _create_mock_file_entry(
                    name="PT001_2024-01-15_LBD_qc-status.log", info=PASSING_INFO
                )
            ],
        )
        clustering = _create_mock_clustering_visitor(
            pipeline_map={1: [project]},
            request_map={1: [_create_mock_request(adcid=1, ptid="PT001")]},
        )
        error_writer = Mock()

        success, _ = run_consolidated(
            input_file=io.StringIO(""),
            modules={"UDS"},
            clustering_visitor=clustering,
            file_visitor_builder=_create_file_visitor_builder(),
            error_writer=error_writer,
            reload_workers=1,
        )

        assert success is True
        errors = _written_errors(error_writer)
        assert [error.ptid for error in errors] == ["PT001"]

    @patch("gather_submission_status_app.main.read_csv")
    def test_leading_zero_ptid_matches_file(self, mock_read_csv: Mock):
        mock_read_csv.return_value = True
        project = _create_mock_project(
            label="ingest-project",
            files=[
                _create_mock_file_entry(
                    name="1234_2024-01-15_UDS_qc-status.log", info=PASSING_INFO
                )
            ],
        )
        clustering = _create_mock_clustering_visitor(
            pipeline_map={1: [project]},
            request_map={1: [_create_mock_request(adcid=1, ptid="001234")]},
        )
        writer, _ = _create_writer()
        error_writer = Mock()

        run(
            input_file=io.StringIO(""),
            modules={"UDS"},
            clustering_visitor=clustering,
            file_visitor_builder=_create_file_visitor_builder(),
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert not _written_errors(error_writer)

    @patch("gather_submission_status_app.main.read_csv")
    def test_duplicate_requests_reported_once(self, mock_read_csv: Mock):
        mock_read_csv.return_value = True
        project = _create_mock_project(label="ingest-project", files=[])
        clustering = _create_mock_clustering_visitor(
            pipeline_map={1: [project]},
            request_map={
                1: [
                    _create_mock_request(adcid=1, ptid="PT009"),
                    _create_mock_request(adcid=1, ptid="PT009"),
                ]
            },
        )
        writer, _ = _create_writer()
        error_writer = Mock()

        run(
            input_file=io.StringIO(""),
            modules={"UDS"},
            clustering_visitor=clustering,
            file_visitor_builder=_create_file_visitor_builder(),
            writer=writer,
            error_writer=error_writer,
            reload_workers=1,
        )

        assert len(_written_errors(error_writer)) == 1
