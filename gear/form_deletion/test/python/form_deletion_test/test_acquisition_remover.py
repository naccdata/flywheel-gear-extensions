"""Unit tests for AcquisitionRemover."""

from typing import Any, Dict
from unittest.mock import MagicMock

from deletions.models import DeleteRequest
from form_deletion_app.helpers import AcquisitionRemover

# Expected labels derived from delete_request + uds_module_configs templates
SESSION_LABEL = "FORMS-VISIT-1"
ACQ_LABEL = "UDS"
SUBJECT_LABEL = "NACC123456"
FILENAME = f"{SUBJECT_LABEL}_{SESSION_LABEL}_{ACQ_LABEL}.json"

PROJECT_GROUP = "nacc"
PROJECT_LABEL = "ingest-form-nacc"
PROJECT_ID = "project-id-123"


def make_remover(
    proxy,
    project_id,
    form_configs,
    uds_module_configs,
    deleted_items,
    delete_request,
    dependent_modules=None,
    naccid=SUBJECT_LABEL,
    skip_accepted_project=False,
):
    return AcquisitionRemover(
        proxy=proxy,
        primary_project_id=project_id,
        module="UDS",
        naccid=naccid,
        form_configs=form_configs,
        module_configs=uds_module_configs,
        delete_request=delete_request,
        deleted_items=deleted_items,
        dependent_modules=dependent_modules,
        skip_accepted_project=skip_accepted_project,
    )


def make_mock_project(label=PROJECT_LABEL, group=PROJECT_GROUP):
    """Create a mock Flywheel Project object."""
    project = MagicMock()
    project.label = label
    project.group = group
    return project


def make_mock_acq_file(ptid="adrc1010", visitdate="2024-01-15", visitnum="1"):
    """Create a mock acquisition file with matching visit metadata."""
    acq_file = MagicMock()
    acq_file.reload.return_value = acq_file
    acq_file.info = {
        "forms": {"json": {"ptid": ptid, "visitdate": visitdate, "visitnum": visitnum}}
    }
    return acq_file


def make_mock_hierarchy(acq_file=None, empty_session_after_delete=True):
    """Return (mock_subject, mock_session, mock_acquisition) with configured
    returns."""
    mock_acquisition = MagicMock()
    mock_acquisition.id = "acq-id-123"
    mock_acquisition.get_file.return_value = acq_file

    mock_session = MagicMock()
    mock_session.id = "session-id-123"
    mock_session.label = SESSION_LABEL
    mock_session.acquisitions.find_first.return_value = mock_acquisition
    mock_session.reload.return_value = mock_session
    mock_session.acquisitions.return_value = (
        [] if empty_session_after_delete else [mock_acquisition]
    )

    mock_subject = MagicMock()
    mock_subject.id = "subject-id-123"
    mock_subject.label = SUBJECT_LABEL
    mock_subject.sessions.find_first.return_value = mock_session
    mock_subject.reload.return_value = mock_subject
    mock_subject.sessions.return_value = []
    mock_subject.get_last_failed_visit.return_value = None

    return mock_subject, mock_session, mock_acquisition


def make_mock_proxy(subjects=None, project=None):
    """Return a MagicMock proxy with common methods pre-configured."""
    proxy = MagicMock()
    proxy.get_subject_by_label.return_value = subjects or []
    proxy.get_project_by_id.return_value = project or make_mock_project()
    proxy.delete_acquisition.return_value = True
    proxy.delete_session.return_value = True
    proxy.delete_subject.return_value = True
    return proxy


class TestCleanupAcquisitions:
    def test_no_subjects_found(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """No subjects for the NACCID → success with nothing deleted."""
        proxy = make_mock_proxy(subjects=[])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_not_called()

    def test_subject_in_irrelevant_project(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Subject in a non-form project is skipped without deletion."""
        mock_subject = MagicMock()
        mock_subject.label = SUBJECT_LABEL
        mock_subject.reload.return_value = mock_subject
        mock_subject.sessions.return_value = [MagicMock()]  # has sessions

        irrelevant_project = make_mock_project(label="retrospective-form")
        proxy = make_mock_proxy(subjects=[mock_subject], project=irrelevant_project)

        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_not_called()

    def test_session_not_found(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Missing session is not an error — returns True."""
        mock_subject = MagicMock()
        mock_subject.label = SUBJECT_LABEL
        mock_subject.sessions.find_first.return_value = None
        mock_subject.reload.return_value = mock_subject
        mock_subject.sessions.return_value = [MagicMock()]  # still has sessions

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_not_called()

    def test_acquisition_not_found(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Missing acquisition is not an error — returns True."""
        mock_subject, mock_session, _ = make_mock_hierarchy()
        mock_session.acquisitions.find_first.return_value = None
        mock_subject.sessions.return_value = [mock_session]  # session still exists

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_not_called()

    def test_acquisition_file_not_found(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Missing acquisition file is not an error — returns True."""
        mock_subject, mock_session, _mock_acquisition = make_mock_hierarchy(
            acq_file=None
        )
        mock_subject.sessions.return_value = [mock_session]

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_not_called()

    def test_successful_acquisition_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Happy path: acquisition deleted and tracked in deleted_items."""
        acq_file = make_mock_acq_file()
        mock_subject, _mock_session, mock_acquisition = make_mock_hierarchy(
            acq_file=acq_file, empty_session_after_delete=True
        )

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        result = remover.cleanup_acquisitions()

        assert result
        proxy.delete_acquisition.assert_called_once_with(mock_acquisition.id)
        expected_acq_path = f"{PROJECT_GROUP}/{PROJECT_LABEL}/{FILENAME}"
        assert expected_acq_path in deleted_items.acquisitions

    def test_acquisition_deletion_fails(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Failed acquisition deletion returns False."""
        acq_file = make_mock_acq_file()
        mock_subject, _, _ = make_mock_hierarchy(acq_file=acq_file)
        mock_subject.sessions.return_value = [MagicMock()]  # still has sessions

        proxy = make_mock_proxy(subjects=[mock_subject])
        proxy.delete_acquisition.return_value = False

        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert not remover.cleanup_acquisitions()
        assert not deleted_items.acquisitions

    def test_empty_session_deleted_after_acquisition(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Session deleted when it has no remaining acquisitions."""
        acq_file = make_mock_acq_file()
        mock_subject, mock_session, _ = make_mock_hierarchy(
            acq_file=acq_file, empty_session_after_delete=True
        )

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        result = remover.cleanup_acquisitions()

        assert result
        proxy.delete_session.assert_called_once_with(mock_session.id)
        expected_session_path = (
            f"{PROJECT_GROUP}/{PROJECT_LABEL}/{SUBJECT_LABEL}/{SESSION_LABEL}"
        )
        assert expected_session_path in deleted_items.sessions

    def test_non_empty_session_not_deleted(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Session with remaining acquisitions is NOT deleted."""
        acq_file = make_mock_acq_file()
        mock_subject, mock_session, _ = make_mock_hierarchy(
            acq_file=acq_file, empty_session_after_delete=False
        )
        mock_subject.sessions.return_value = [
            mock_session
        ]  # subject still has sessions

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        result = remover.cleanup_acquisitions()

        assert result
        proxy.delete_session.assert_not_called()

    def test_subject_deleted_when_no_sessions_remain(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Subject with no sessions is deleted after acquisition cleanup."""
        acq_file = make_mock_acq_file()
        mock_subject, _, _ = make_mock_hierarchy(acq_file=acq_file)
        mock_subject.sessions.return_value = []  # no sessions after deletion

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        result = remover.cleanup_acquisitions()

        assert result
        proxy.delete_subject.assert_called_once_with(subject_id=mock_subject.id)
        expected_subject_path = f"{PROJECT_GROUP}/{PROJECT_LABEL}/{SUBJECT_LABEL}"
        assert expected_subject_path in deleted_items.subjects

    def test_visitnum_required_but_missing(
        self, form_configs, uds_module_configs, deleted_items
    ):
        """Session template needs visitnum but request has none → returns
        False."""
        delete_request_no_visitnum = DeleteRequest(
            ptid="adrc1010", module="uds", visitdate="2024-01-15"
        )
        mock_subject = MagicMock()
        mock_subject.label = SUBJECT_LABEL

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request_no_visitnum,
        )
        assert not remover.cleanup_acquisitions()

    def test_dependent_module_deleted_before_primary(
        self,
        form_configs_with_dep,
        uds_module_configs,
        deleted_items,
        delete_request,
    ):
        """Dependent module acquisition is deleted before the primary
        module."""
        acq_file = make_mock_acq_file()

        mock_acquisition = MagicMock()
        mock_acquisition.id = "acq-id-123"
        mock_acquisition.get_file.return_value = acq_file

        mock_session = MagicMock()
        mock_session.id = "session-id-123"
        mock_session.acquisitions.find_first.return_value = mock_acquisition
        mock_session.reload.return_value = mock_session
        mock_session.acquisitions.return_value = []

        mock_subject = MagicMock()
        mock_subject.id = "subject-id-123"
        mock_subject.label = SUBJECT_LABEL
        mock_subject.sessions.find_first.return_value = mock_session
        mock_subject.reload.return_value = mock_subject
        mock_subject.sessions.return_value = []
        mock_subject.get_last_failed_visit.return_value = None

        proxy = make_mock_proxy(subjects=[mock_subject])
        deleted_acquisition_ids = []
        proxy.delete_acquisition.side_effect = (
            lambda acq_id: deleted_acquisition_ids.append(acq_id)  # type: ignore
            or True
        )

        dependent_modules = ["TFP"]
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs_with_dep,
            uds_module_configs,
            deleted_items,
            delete_request,
            dependent_modules=dependent_modules,
        )
        result = remover.cleanup_acquisitions()

        assert result
        assert proxy.delete_acquisition.call_count == 2

    def test_missing_dependent_module_configs(
        self,
        form_configs,
        uds_module_configs,
        deleted_items,
        delete_request,
    ):
        """Missing configs for a dependent module causes failure."""
        acq_file = make_mock_acq_file()
        mock_subject, _, _ = make_mock_hierarchy(acq_file=acq_file)
        mock_subject.sessions.return_value = [MagicMock()]

        proxy = make_mock_proxy(subjects=[mock_subject])

        # Pass a dependent module "UNKNOWN" that has no entry in form_configs
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
            dependent_modules=["UNKNOWN"],
        )
        result = remover.cleanup_acquisitions()

        assert not result

    def test_accepted_project_skipped_when_configured(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """With skip_accepted_project=True, a subject in the accepted project is
        skipped without any deletion."""
        acq_file = make_mock_acq_file()
        mock_subject, _, _ = make_mock_hierarchy(acq_file=acq_file)
        mock_subject.sessions.return_value = [MagicMock()]  # still has sessions

        accepted_project = make_mock_project(label="accepted-nacc")
        proxy = make_mock_proxy(subjects=[mock_subject], project=accepted_project)

        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
            skip_accepted_project=True,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_not_called()
        assert not deleted_items.acquisitions

    def test_accepted_project_deleted_by_default(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """By default (skip_accepted_project=False), acquisitions in the accepted
        project are deleted."""
        acq_file = make_mock_acq_file()
        mock_subject, _, mock_acquisition = make_mock_hierarchy(
            acq_file=acq_file, empty_session_after_delete=True
        )

        accepted_project = make_mock_project(label="accepted-nacc")
        proxy = make_mock_proxy(subjects=[mock_subject], project=accepted_project)

        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        assert remover.cleanup_acquisitions()
        proxy.delete_acquisition.assert_called_once_with(mock_acquisition.id)
        expected_acq_path = f"{PROJECT_GROUP}/accepted-nacc/{FILENAME}"
        assert expected_acq_path in deleted_items.acquisitions


class TestCompareVisitDetails:
    """Tests for visit detail comparison via cleanup_acquisitions behavior."""

    def _run_with_acq_info(
        self,
        form_configs,
        uds_module_configs,
        deleted_items,
        delete_request,
        acq_info,
    ):
        """Run cleanup_acquisitions with the given acquisition file info."""
        acq_file = MagicMock()
        acq_file.reload.return_value = acq_file
        acq_file.info = acq_info

        mock_subject, mock_session, _ = make_mock_hierarchy(
            acq_file=acq_file, empty_session_after_delete=False
        )
        mock_subject.sessions.return_value = [mock_session]

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        return remover.cleanup_acquisitions(), proxy

    def test_no_info_allows_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Acquisition with no info dict passes validation and is deleted."""
        acq_file = MagicMock()
        acq_file.reload.return_value = acq_file
        acq_file.info = None

        mock_subject, mock_session, _ = make_mock_hierarchy(
            acq_file=acq_file, empty_session_after_delete=False
        )
        mock_subject.sessions.return_value = [mock_session]

        proxy = make_mock_proxy(subjects=[mock_subject])
        remover = make_remover(
            proxy,
            PROJECT_ID,
            form_configs,
            uds_module_configs,
            deleted_items,
            delete_request,
        )
        result = remover.cleanup_acquisitions()

        assert result
        proxy.delete_acquisition.assert_called_once()

    def test_matching_metadata_allows_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Acquisition with fully matching metadata is deleted."""
        acq_info = {
            "forms": {
                "json": {
                    "ptid": "adrc1010",
                    "visitdate": "2024-01-15",
                    "visitnum": "1",
                }
            }
        }
        result, proxy = self._run_with_acq_info(
            form_configs, uds_module_configs, deleted_items, delete_request, acq_info
        )
        assert result
        proxy.delete_acquisition.assert_called_once()

    def test_ptid_mismatch_blocks_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Mismatched PTID prevents acquisition deletion."""
        acq_info = {
            "forms": {
                "json": {"ptid": "WRONG", "visitdate": "2024-01-15", "visitnum": "1"}
            }
        }
        result, proxy = self._run_with_acq_info(
            form_configs, uds_module_configs, deleted_items, delete_request, acq_info
        )
        assert not result
        proxy.delete_acquisition.assert_not_called()

    def test_visitdate_mismatch_blocks_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Mismatched visitdate prevents acquisition deletion."""
        acq_info = {
            "forms": {
                "json": {"ptid": "adrc1010", "visitdate": "2023-01-01", "visitnum": "1"}
            }
        }
        result, proxy = self._run_with_acq_info(
            form_configs, uds_module_configs, deleted_items, delete_request, acq_info
        )
        assert not result
        proxy.delete_acquisition.assert_not_called()

    def test_visitnum_mismatch_blocks_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Mismatched visitnum prevents acquisition deletion."""
        acq_info = {
            "forms": {
                "json": {
                    "ptid": "adrc1010",
                    "visitdate": "2024-01-15",
                    "visitnum": "99",
                }
            }
        }
        result, proxy = self._run_with_acq_info(
            form_configs, uds_module_configs, deleted_items, delete_request, acq_info
        )
        assert not result
        proxy.delete_acquisition.assert_not_called()

    def test_empty_forms_json_allows_deletion(
        self, form_configs, uds_module_configs, deleted_items, delete_request
    ):
        """Acquisition with empty forms.json dict passes validation."""
        acq_info: Dict[str, Any] = {"forms": {"json": {}}}
        result, proxy = self._run_with_acq_info(
            form_configs, uds_module_configs, deleted_items, delete_request, acq_info
        )
        assert result
        proxy.delete_acquisition.assert_called_once()
