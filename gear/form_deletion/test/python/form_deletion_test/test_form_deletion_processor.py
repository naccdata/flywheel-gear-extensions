"""Unit tests for FormDeletionProcessor."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from configs.ingest_configs import FormProjectConfigs
from deletions.models import DeleteRequest
from form_deletion_app.delete import FormDeletionProcessor
from form_deletion_test.conftest import MockProjectAdaptorForDeletion


def create_processor(
    mock_project,
    delete_request,
    form_configs,
    request_time,
    error_writer,
    identifier=None,
    adcid=42,
    qcm_log_name="primary.json",
    qcm_side_effect=None,
):
    """Create a FormDeletionProcessor with a patched QCStatusLogManager.

    The QCStatusLogManager is patched at construction time. The
    resulting mock instance persists inside the processor after the
    patch context exits, so process_request() will use the configured
    return values.
    """
    mock_qcm = MagicMock()
    if qcm_side_effect is not None:
        mock_qcm.get_qc_log_filename.side_effect = qcm_side_effect
    else:
        mock_qcm.get_qc_log_filename.return_value = qcm_log_name

    with (
        patch("form_deletion_app.delete.QCStatusLogManager", return_value=mock_qcm),
        patch("form_deletion_app.delete.ErrorLogTemplate"),
        patch("form_deletion_app.delete.FileVisitAnnotator"),
    ):
        return FormDeletionProcessor(
            project=mock_project,
            adcid=adcid,
            delete_request=delete_request,
            request_time=request_time,
            form_configs=form_configs,
            error_writer=error_writer,
            identifier=identifier,
            check_sbsq_visits=True,
        )


class TestProcessRequest:
    def test_inactive_participant_rejected(
        self,
        mock_project,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        inactive_identifier,
        error_log_name,
    ):
        """Inactive participant causes immediate rejection with an error."""
        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            identifier=inactive_identifier,
            qcm_log_name=error_log_name,
        )
        assert not processor.process_request()
        assert error_writer.errors().list()

    def test_no_error_log_name(
        self, mock_project, delete_request, form_configs, request_time, error_writer
    ):
        """If the log filename cannot be derived, the request is rejected."""
        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            qcm_log_name=None,  # type: ignore
        )
        assert not processor.process_request()
        assert error_writer.errors().list()

    def test_error_log_file_not_found(
        self,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        error_log_name,
    ):
        """Missing error log file causes rejection."""
        empty_project = MockProjectAdaptorForDeletion(label="ingest-form-nacc")
        processor = create_processor(
            empty_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            qcm_log_name=error_log_name,
        )
        assert not processor.process_request()
        assert error_writer.errors().list()

    def test_log_modified_after_request(
        self,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        new_error_log_file,
        error_log_name,
    ):
        """Log file modified after the request timestamp causes rejection."""
        project = MockProjectAdaptorForDeletion(label="ingest-form-nacc")
        project.add_file(new_error_log_file)
        processor = create_processor(
            project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            qcm_log_name=error_log_name,
        )
        assert not processor.process_request()
        assert error_writer.errors().list()

    def test_no_naccid_log_cleanup_success(
        self,
        mock_project,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        error_log_name,
    ):
        """No identifier means no subject lookup; proceeds to log cleanup."""
        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            identifier=None,
            qcm_log_name=error_log_name,
        )
        result = processor.process_request()
        assert result
        assert error_log_name in processor.deleted_items.logs

    def test_naccid_subject_not_in_project(
        self,
        mock_project,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """Subject not found for NACCID — skip acquisition deletion, clean up
        log."""
        mock_project.find_subject = MagicMock(return_value=None)
        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        result = processor.process_request()
        assert result
        assert error_log_name in processor.deleted_items.logs

    def test_longitudinal_subsequent_visits_rejected(
        self,
        mock_project,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """Longitudinal module with subsequent QC-passed visits causes
        rejection."""
        mock_subject = MagicMock()
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        mock_project.proxy.get_matching_acquisition_files_info.return_value = [
            {"file.name": "later-visit.json"}
        ]

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        assert not processor.process_request()
        assert error_writer.errors().list()

    def test_non_longitudinal_skips_subsequent_check(
        self,
        mock_project,
        delete_request,
        request_time,
        error_writer,
        active_identifier,
        uds_module_configs,
        error_log_name,
    ):
        """Non-longitudinal module skips the subsequent visit check
        entirely."""
        non_long_configs = uds_module_configs.model_copy(update={"longitudinal": False})
        configs = FormProjectConfigs(
            primary_key="ptid",
            accepted_modules=["UDS"],
            module_configs={"UDS": non_long_configs},
        )

        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        mock_project.proxy.get_matching_acquisition_files_info.return_value = [
            {"file.name": "match.json", "file.file_id": "xyz"}
        ]

        processor = create_processor(
            mock_project,
            delete_request,
            configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            result = processor.process_request()

        assert result

    def test_no_module_configs_for_subject(
        self,
        mock_project,
        delete_request,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """Missing module config when subject exists causes rejection."""
        empty_configs = FormProjectConfigs(
            primary_key="ptid",
            accepted_modules=[],
            module_configs={},
        )

        mock_subject = MagicMock()
        mock_project.set_subject(active_identifier.naccid, mock_subject)

        processor = create_processor(
            mock_project,
            delete_request,
            empty_configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        assert not processor.process_request()
        assert error_writer.errors().list()

    def test_acquisition_remover_fails(
        self,
        mock_project,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """AcquisitionRemover failure propagates as overall failure."""
        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        call_count = {"n": 0}

        def side_effect(**_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [{"file.name": "match.json", "file.file_id": "xyz"}]
            return []

        mock_project.proxy.get_matching_acquisition_files_info.side_effect = side_effect

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = False
            result = processor.process_request()

        assert not result
        assert error_writer.errors().list()

    def test_full_success_with_subject(
        self,
        mock_project,
        delete_request,
        form_configs,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """Full happy path: acquisitions removed, log deleted, items
        tracked."""
        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        mock_project.proxy.find_projects.return_value = []
        call_count = {"n": 0}

        def side_effect(**_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [{"file.name": "match.json", "file.file_id": "xyz"}]
            return []

        mock_project.proxy.get_matching_acquisition_files_info.side_effect = side_effect

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            result = processor.process_request()

        assert result
        assert error_log_name in processor.deleted_items.logs
        assert not error_writer.errors().list()


class TestOrphanedNpMlstRemoval:
    """Tests for orphaned NP/MLST removal triggered after clinical form
    deletion."""

    def test_non_clinical_module_skips_orphan_check(
        self,
        mock_project,
        request_time,
        error_writer,
        active_identifier,
        np_module_configs,
    ):
        """Deleting a non-clinical module (NP itself) never triggers the orphan
        check."""
        np_request = DeleteRequest(ptid="adrc1010", module="np", visitdate="2024-01-01")
        np_configs = FormProjectConfigs(
            primary_key="ptid",
            accepted_modules=["NP"],
            module_configs={"NP": np_module_configs},
        )
        np_log_name = "adrc1010_2024-01-01_np_qc-status.log"
        np_log_file = MagicMock()
        np_log_file.name = np_log_name
        np_log_file.modified = datetime(2024, 1, 10, tzinfo=timezone.utc)
        mock_project.add_file(np_log_file)

        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        mock_project.proxy.get_matching_acquisition_files_info.return_value = [
            {"file.name": "match.json", "file.file_id": "xyz"}
        ]

        processor = create_processor(
            mock_project,
            np_request,
            np_configs,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=np_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            result = processor.process_request()

        assert result
        mock_acq_cls.return_value.cleanup_orphaned_acquisitions.assert_not_called()

    def test_clinical_module_remaining_forms_skips_orphan_removal(
        self,
        mock_project,
        delete_request,
        form_configs_with_np_mlst,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """When clinical forms still remain after deletion, orphan removal is
        skipped."""
        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        # First call: has_matching_acquisitions → 1 match (deletion proceeds).
        # Second call: subsequent-visit check → no results (deletion proceeds).
        # Third call: remaining-clinical-forms check → forms found (skip
        # orphan removal).
        call_count = {"n": 0}

        def side_effect(**_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [{"file.name": "match.json", "file.file_id": "xyz"}]
            if call_count["n"] == 2:
                return []
            return [{"file.name": "remaining-uds.json", "file.file_id": "abc"}]

        mock_project.proxy.get_matching_acquisition_files_info.side_effect = side_effect

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs_with_np_mlst,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            result = processor.process_request()

        assert result
        mock_acq_cls.return_value.cleanup_orphaned_acquisitions.assert_not_called()

    def test_clinical_module_no_remaining_forms_removes_orphans(
        self,
        mock_project,
        delete_request,
        form_configs_with_np_mlst,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """When no clinical forms remain, cleanup_orphaned_acquisitions is
        called with NP and MLST."""
        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        mock_project.proxy.find_projects.return_value = []
        # First call: has_matching_acquisitions → 1 match (deletion proceeds).
        # Subsequent calls: subsequent-visit and remaining-clinical-forms checks
        # → no results (no retro project configured).
        call_count = {"n": 0}

        def side_effect(**_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [{"file.name": "match.json", "file.file_id": "xyz"}]
            return []

        mock_project.proxy.get_matching_acquisition_files_info.side_effect = side_effect

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs_with_np_mlst,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            mock_acq_cls.return_value.cleanup_orphaned_acquisitions.return_value = True
            result = processor.process_request()

        assert result
        mock_acq_cls.return_value.cleanup_orphaned_acquisitions.assert_called_once()
        called_modules = (
            mock_acq_cls.return_value.cleanup_orphaned_acquisitions.call_args[0][0]
        )
        assert set(called_modules) == {"NP", "MLST"}

    def test_orphan_acquisition_removal_failure_returns_false(
        self,
        mock_project,
        delete_request,
        form_configs_with_np_mlst,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """Failure in cleanup_orphaned_acquisitions propagates as overall
        failure with an error."""
        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)
        mock_project.proxy.find_projects.return_value = []
        call_count = {"n": 0}

        def side_effect(**_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [{"file.name": "match.json", "file.file_id": "xyz"}]
            return []

        mock_project.proxy.get_matching_acquisition_files_info.side_effect = side_effect

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs_with_np_mlst,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            mock_acq_cls.return_value.cleanup_orphaned_acquisitions.return_value = False
            result = processor.process_request()

        assert not result
        assert error_writer.errors().list()

    def test_retrospective_form_clinical_found_skips_orphan_removal(
        self,
        mock_project,
        delete_request,
        form_configs_with_np_mlst,
        request_time,
        error_writer,
        active_identifier,
        error_log_name,
    ):
        """A UDS acquisition in retrospective-form counts as a remaining
        clinical form — orphan removal is skipped."""
        mock_subject = MagicMock()
        mock_subject.id = "subj-001"
        mock_project.set_subject(active_identifier.naccid, mock_subject)

        mock_retro_project = MagicMock()
        mock_retro_subject = MagicMock()
        mock_retro_subject.id = "retro-subj-001"
        mock_retro_project.subjects.find_first.return_value = mock_retro_subject
        mock_project.proxy.find_projects.return_value = [mock_retro_project]

        # Call 1: has_matching_acquisitions → 1 match (deletion proceeds).
        # Call 2: subsequent-visit check → no results (deletion proceeds).
        # Call 3: has_remaining_clinical_forms (ingest) → no results.
        # Call 4: has_remaining_clinical_forms (retro) → found retro UDS
        #         → skip orphan removal.
        call_count = {"n": 0}

        def side_effect(**_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [{"file.name": "match.json", "file.file_id": "xyz"}]
            if call_count["n"] in (2, 3):
                return []
            return [{"file.name": "retro-uds.json", "file.file_id": "xyz"}]

        mock_project.proxy.get_matching_acquisition_files_info.side_effect = side_effect

        processor = create_processor(
            mock_project,
            delete_request,
            form_configs_with_np_mlst,
            request_time,
            error_writer,
            identifier=active_identifier,
            qcm_log_name=error_log_name,
        )
        with patch("form_deletion_app.delete.AcquisitionRemover") as mock_acq_cls:
            mock_acq_cls.return_value.cleanup_acquisitions.return_value = True
            result = processor.process_request()

        assert result
        mock_acq_cls.return_value.cleanup_orphaned_acquisitions.assert_not_called()

    def test_dep_module_log_delete_fails(
        self,
        mock_project,
        delete_request,
        form_configs_with_dep,
        request_time,
        error_writer,
        error_log_name,
    ):
        """Dependent module log deletion failure returns False."""
        dep_log_name = "adrc1010_2024-01-15_1_tfp_qc-status.log"
        dep_log_file = MagicMock()
        dep_log_file.name = dep_log_name
        dep_log_file.modified = datetime(2024, 1, 14, tzinfo=timezone.utc)

        mock_project.add_file(dep_log_file)
        mock_project.set_delete_result(dep_log_name, False)

        # Both primary and dep log names returned by QCStatusLogManager in order:
        # 1st call: primary module (UDS) in process_request
        # 2nd call: dep module (TFP) in __cleanup_log_files
        processor = create_processor(
            mock_project,
            delete_request,
            form_configs_with_dep,
            request_time,
            error_writer,
            identifier=None,
            qcm_side_effect=[error_log_name, dep_log_name],
        )
        result = processor.process_request()

        assert not result
        assert error_writer.errors().list()
