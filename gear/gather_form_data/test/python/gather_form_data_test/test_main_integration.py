"""Integration tests for the end-to-end gather form data flow.

Tests the complete main.run() function with mocked FlywheelProxy
methods, verifying correct interaction between phases.
"""

from unittest.mock import Mock, patch

from gather_form_data_app.main import run
from outputs.error_writer import ListErrorWriter

from .conftest import (
    create_gather_config,
    create_mock_project,
    create_mock_proxy,
    create_mock_subject,
    make_csv_content,
)


class TestHappyPath:
    """All NACCIDs resolve, correct gatherers populated."""

    def test_all_naccids_resolve_success(self):
        """When all NACCIDs resolve, success is True and gatherers are called
        with correct subject IDs."""
        naccids = ["NACC000001", "NACC000002", "NACC000003"]
        csv_content = make_csv_content(naccids)

        project_id = "proj-1"
        project = create_mock_project(project_id=project_id, label="ingest-form")

        subjects = [
            create_mock_subject(
                label=nid, subject_id=f"subj-{nid}", project_id=project_id
            )
            for nid in naccids
        ]

        proxy = create_mock_proxy(
            projects=[project],
            subjects_by_project={project_id: subjects},
        )

        error_writer = ListErrorWriter(container_id="file-1", fw_path="/test/path")

        with patch("gather_form_data_app.main.ModuleDataGatherer") as MockGatherer:
            mock_gatherer_instance = Mock()
            MockGatherer.return_value = mock_gatherer_instance

            success, gatherers = run(
                request_file=csv_content,
                proxy=proxy,
                config=create_gather_config(),
                error_writer=error_writer,
            )

        assert success is True
        assert len(gatherers) == 1

        # Verify gather_project_data was called with all subject IDs
        mock_gatherer_instance.gather_project_data.assert_called_once()
        call_kwargs = mock_gatherer_instance.gather_project_data.call_args
        called_subject_ids = call_kwargs[1]["subject_ids"]
        expected_ids = [f"subj-{nid}" for nid in naccids]
        assert sorted(called_subject_ids) == sorted(expected_ids)

    def test_multiple_modules_create_multiple_gatherers(self):
        """Each module produces its own gatherer."""
        csv_content = make_csv_content(["NACC000001"])

        project_id = "proj-1"
        project = create_mock_project(project_id=project_id, label="ingest-form")
        subject = create_mock_subject(
            label="NACC000001", subject_id="subj-1", project_id=project_id
        )

        proxy = create_mock_proxy(
            projects=[project],
            subjects_by_project={project_id: [subject]},
        )

        error_writer = ListErrorWriter(container_id="file-1", fw_path="/test/path")

        with patch("gather_form_data_app.main.ModuleDataGatherer") as MockGatherer:
            mock_instance = Mock()
            MockGatherer.return_value = mock_instance

            success, _gatherers = run(
                request_file=csv_content,
                proxy=proxy,
                config=create_gather_config(modules={"UDS", "FTLD", "LBD"}),
                error_writer=error_writer,
            )

        assert success is True
        assert len(_gatherers) == 3


class TestMixedPath:
    """Some NACCIDs resolve, some don't."""

    def test_mixed_resolution_reports_errors_for_unresolved(self):
        """When some NACCIDs don't resolve, errors are reported and
        success=False, but data is still gathered for resolved ones."""
        resolved_naccids = ["NACC000001", "NACC000002"]
        unresolved_naccids = ["NACC000099"]
        all_naccids = resolved_naccids + unresolved_naccids

        csv_content = make_csv_content(all_naccids)

        project_id = "proj-1"
        project = create_mock_project(project_id=project_id, label="ingest-form")

        # Only resolved NACCIDs have subjects
        subjects = [
            create_mock_subject(
                label=nid, subject_id=f"subj-{nid}", project_id=project_id
            )
            for nid in resolved_naccids
        ]

        proxy = create_mock_proxy(
            projects=[project],
            subjects_by_project={project_id: subjects},
        )

        error_writer = ListErrorWriter(container_id="file-1", fw_path="/test/path")

        with patch("gather_form_data_app.main.ModuleDataGatherer") as MockGatherer:
            mock_instance = Mock()
            MockGatherer.return_value = mock_instance

            success, _gatherers = run(
                request_file=csv_content,
                proxy=proxy,
                config=create_gather_config(),
                error_writer=error_writer,
            )

        # Success is False due to unresolved NACCIDs
        assert success is False

        # Verify error was reported for unresolved NACCID
        errors = error_writer.errors()
        no_participant_errors = [e for e in errors if e.error_code == "no-participant"]
        assert len(no_participant_errors) == 1
        assert "NACC000099" in no_participant_errors[0].message

        # But data was still gathered for resolved subjects
        mock_instance.gather_project_data.assert_called_once()
        called_subject_ids = mock_instance.gather_project_data.call_args[1][
            "subject_ids"
        ]
        assert len(called_subject_ids) == 2


class TestEmptyCSV:
    """Empty CSV produces no errors and no output."""

    def test_empty_csv_no_data_rows(self):
        """A CSV with only a header produces no errors and empty gatherers."""
        csv_content = make_csv_content([])

        proxy = create_mock_proxy(projects=[])
        error_writer = ListErrorWriter(container_id="file-1", fw_path="/test/path")

        success, gatherers = run(
            request_file=csv_content,
            proxy=proxy,
            config=create_gather_config(),
            error_writer=error_writer,
        )

        assert success is True
        assert len(gatherers) == 1
        assert not error_writer.has_errors()


class TestAllInvalidCSV:
    """All NACCIDs are invalid."""

    def test_all_invalid_produces_errors_and_fails(self):
        """When all rows have invalid NACCIDs, all produce malformed-file
        errors and success=False."""
        invalid_ids = ["BAD001", "INVALID", "NACC12"]  # None match pattern
        csv_content = make_csv_content(invalid_ids)

        proxy = create_mock_proxy(projects=[])
        error_writer = ListErrorWriter(container_id="file-1", fw_path="/test/path")

        success, _gatherers = run(
            request_file=csv_content,
            proxy=proxy,
            config=create_gather_config(),
            error_writer=error_writer,
        )

        assert success is False

        errors = error_writer.errors()
        malformed_errors = [e for e in errors if e.error_code == "malformed-file"]
        assert len(malformed_errors) == len(invalid_ids)


class TestBatchSizeAndWorkersPropagation:
    """Verify batch_size and reload_workers are passed through to
    gather_project_data."""

    def test_parameters_passed_to_gatherer(self):
        """batch_size and reload_workers from config are forwarded to
        gather_project_data."""
        csv_content = make_csv_content(["NACC000001"])

        project_id = "proj-1"
        project = create_mock_project(project_id=project_id, label="ingest-form")
        subject = create_mock_subject(
            label="NACC000001", subject_id="subj-1", project_id=project_id
        )

        proxy = create_mock_proxy(
            projects=[project],
            subjects_by_project={project_id: [subject]},
        )

        error_writer = ListErrorWriter(container_id="file-1", fw_path="/test/path")

        with patch("gather_form_data_app.main.ModuleDataGatherer") as MockGatherer:
            mock_instance = Mock()
            MockGatherer.return_value = mock_instance

            run(
                request_file=csv_content,
                proxy=proxy,
                config=create_gather_config(batch_size=50, reload_workers=5),
                error_writer=error_writer,
            )

        call_kwargs = mock_instance.gather_project_data.call_args[1]
        assert call_kwargs["batch_size"] == 50
        assert call_kwargs["reload_workers"] == 5
