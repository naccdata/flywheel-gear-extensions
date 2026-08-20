"""Tests handling of a rejected record for a visit that already has an
acquisition file.

- If the existing visit passed QC, it is left untouched and a note is added to
  the visit error log.
- Otherwise the QC metadata and status tags are cleared from the existing visit
  file. The visit data is never removed.
"""

import logging
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from flywheel.rest import ApiException
from nacc_common.error_models import FileError
from nacc_common.field_names import FieldNames

PASS_QC = {"form-qc-checker": {"validation": {"state": "PASS"}}}
FAIL_QC = {"form-qc-checker": {"validation": {"state": "FAIL"}}}
REVIEW_QC = {"form-qc-checker": {"validation": {"state": "IN REVIEW"}}}

STORED_VISIT = {
    FieldNames.PTID: "110001",
    FieldNames.DATE_COLUMN: "2024-03-15",
    FieldNames.VISITNUM: "2",
    FieldNames.PACKET: "I",
}


def _row(**overrides: Any) -> Dict[str, Any]:
    """Create a valid input row, applying any overrides."""
    row = {
        FieldNames.NACCID: "NACC000001",
        FieldNames.PTID: "110001",
        FieldNames.DATE_COLUMN: "2024-03-15",
        FieldNames.MODULE: "UDS",
        FieldNames.VISITNUM: "2",
        FieldNames.ADCID: 42,
    }
    row.update(overrides)
    return row


def _np_row(**overrides: Any) -> Dict[str, Any]:
    """Create a valid input row for the date-keyed NP module."""
    row = {
        FieldNames.NACCID: "NACC000001",
        FieldNames.PTID: "110001",
        "npformdate": "2024-03-15",
        FieldNames.MODULE: "NP",
        FieldNames.ADCID: 42,
    }
    row.update(overrides)
    return row


def _reject(harness, row: Dict[str, Any], line_num: int = 1) -> List[FileError]:
    """Push a row through the visitor so it is rejected in preprocessing.

    Returns the errors handed to the visit error log.
    """
    with (
        patch("form_csv_app.main.QCStatusLogManager") as log_manager,
        patch("form_csv_app.main.FileVisitAnnotator"),
    ):
        assert harness.visitor.visit_row(row, line_num)
        assert not harness.visitor.process_current_batch()
        update_calls = log_manager.return_value.update_qc_log.call_args_list

    assert len(update_calls) == 1, "expected exactly one visit error log update"
    assert update_calls[0].kwargs["status"] == "FAIL"
    return list(update_calls[0].kwargs["errors"])


def _codes(errors: List[FileError]) -> List[Optional[str]]:
    """Return the error codes for the given errors."""
    return [error.error_code for error in errors]


class TestExistingVisitPassedQC:
    """The existing visit passed QC, so it must be left alone."""

    def test_visit_file_untouched(self, create_rejection_harness, create_visit_file):
        """No metadata or tag changes are made to a QC passed visit file."""
        visit_file = create_visit_file(
            forms_json=STORED_VISIT,
            qc=PASS_QC,
            tags=["form-qc-checker-PASS", "submission-completed"],
        )
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())

        visit_file.update_info.assert_not_called()
        visit_file.delete_tag.assert_not_called()
        assert "existing-visit-retained" in _codes(errors)

    def test_note_names_the_retained_file(
        self, create_rejection_harness, create_visit_file
    ):
        """The note reports the file that was left in place."""
        visit_file = create_visit_file(forms_json=STORED_VISIT, qc=PASS_QC)
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())
        note = next(
            error for error in errors if error.error_code == "existing-visit-retained"
        )

        assert visit_file.name in note.message
        assert "was not removed or replaced" in note.message
        assert note.error_type == "error"
        assert note.value == visit_file.name
        assert note.ptid == "110001"
        assert note.date == "2024-03-15"
        assert note.visitnum == "2"
        assert note.location.line == 1  # type: ignore[union-attr]
        assert note.location.column_name == "visitdate"  # type: ignore[union-attr]

    def test_note_appends_failure_reason(
        self, create_rejection_harness, create_visit_file
    ):
        """The note carries the reason the record was rejected."""
        visit_file = create_visit_file(forms_json=STORED_VISIT, qc=PASS_QC)
        harness = create_rejection_harness(visit_file=visit_file)

        def fail_with_error(*, input_record, line_num, ivp_record=None):
            harness.visitor._CSVTransformVisitor__error_writer.write(  # noqa: SLF001
                FileError(
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    error_code="preprocess-034",  # pyright: ignore[reportCallIssue]
                    message="PACKET=I is not accepted",
                )
            )
            return False

        harness.preprocessor.preprocess.side_effect = fail_with_error

        errors = _reject(harness, _row())
        note = next(
            error for error in errors if error.error_code == "existing-visit-retained"
        )

        assert "PACKET=I is not accepted" in note.message
        # the note itself is not listed as one of its own reasons
        assert note.message.count("PACKET=I is not accepted") == 1

    def test_note_without_reasons(self, create_rejection_harness, create_visit_file):
        """The note degrades cleanly when the record produced no messages."""
        visit_file = create_visit_file(forms_json=STORED_VISIT, qc=PASS_QC)
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())
        note = next(
            error for error in errors if error.error_code == "existing-visit-retained"
        )

        assert "rejected because" not in note.message
        assert visit_file.name in note.message


class TestExistingVisitNotPassedQC:
    """The existing visit is not accepted data, so its QC status is cleared."""

    @pytest.mark.parametrize("qc_info", [FAIL_QC, REVIEW_QC])
    def test_qc_metadata_and_tags_cleared(
        self, create_rejection_harness, create_visit_file, qc_info
    ):
        """QC metadata, validated timestamp and status tags are removed."""
        visit_file = create_visit_file(
            forms_json=STORED_VISIT,
            qc=qc_info,
            tags=[
                "form-qc-checker-FAIL",
                "submission-completed",
                "some-other-tag",
            ],
        )
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())

        visit_file.update_info.assert_called_once_with(
            {"qc": {}, "validated-timestamp": ""}
        )
        deleted = [call.args[0] for call in visit_file.delete_tag.call_args_list]
        assert sorted(deleted) == ["form-qc-checker-FAIL", "submission-completed"]
        assert "existing-visit-retained" not in _codes(errors)

    def test_never_evaluated_visit_is_reset(
        self, create_rejection_harness, create_visit_file
    ):
        """A visit file with no QC metadata is not treated as QC passed.

        Guards the vacuous PASS returned by FileQCModel for an empty QC
        dict.
        """
        visit_file = create_visit_file(forms_json=STORED_VISIT, tags=[])
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())

        visit_file.update_info.assert_called_once()
        visit_file.delete_tag.assert_not_called()
        assert "existing-visit-retained" not in _codes(errors)

    def test_unreadable_qc_metadata_is_reset(
        self, create_rejection_harness, create_visit_file
    ):
        """Unexpected QC metadata is not treated as QC passed."""
        visit_file = create_visit_file(
            forms_json=STORED_VISIT, qc={"form-qc-checker": "not-a-model"}
        )
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())

        visit_file.update_info.assert_called_once()
        assert "existing-visit-retained" not in _codes(errors)

    def test_reset_failure_logged(
        self, create_rejection_harness, create_visit_file, caplog
    ):
        """A failed reset is logged and does not interrupt processing."""
        visit_file = create_visit_file(forms_json=STORED_VISIT, qc=FAIL_QC)
        visit_file.update_info.side_effect = ApiException(status=500, reason="boom")
        harness = create_rejection_harness(visit_file=visit_file)

        with caplog.at_level(logging.ERROR):
            errors = _reject(harness, _row())

        assert "Failed to reset the QC status" in caplog.text
        assert visit_file.name in caplog.text
        # the visit error log carries no extra entry for a system level problem
        assert not _codes(errors)


class TestVisitMatching:
    """Only an exact ptid/date/visitnum match counts as the same visit."""

    def test_leading_zeros_in_ptid_match(
        self, create_rejection_harness, create_visit_file
    ):
        """PTIDs are compared without leading zeros."""
        visit_file = create_visit_file(
            forms_json={**STORED_VISIT, FieldNames.PTID: "0110001"}, qc=PASS_QC
        )
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row(ptid="110001"))

        assert "existing-visit-retained" in _codes(errors)

    def test_different_packet_still_matches(
        self, create_rejection_harness, create_visit_file
    ):
        """The packet code is not part of the visit identity."""
        visit_file = create_visit_file(
            forms_json={**STORED_VISIT, FieldNames.PACKET: "I"}, qc=PASS_QC
        )
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row(packet="F"))

        assert "existing-visit-retained" in _codes(errors)

    @pytest.mark.parametrize(
        "stored_overrides",
        [
            pytest.param({FieldNames.DATE_COLUMN: "2024-04-20"}, id="date"),
            pytest.param({FieldNames.VISITNUM: "3"}, id="visitnum"),
            pytest.param({FieldNames.PTID: "110002"}, id="ptid"),
            pytest.param({FieldNames.DATE_COLUMN: None}, id="missing-date"),
            pytest.param({FieldNames.VISITNUM: None}, id="missing-visitnum"),
            pytest.param({FieldNames.PTID: None}, id="missing-ptid"),
        ],
    )
    def test_mismatch_leaves_visit_file_alone(
        self, create_rejection_harness, create_visit_file, stored_overrides
    ):
        """A mismatching or incomplete file is not the same visit."""
        visit_file = create_visit_file(
            forms_json={**STORED_VISIT, **stored_overrides}, qc=PASS_QC
        )
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())

        visit_file.update_info.assert_not_called()
        assert "existing-visit-retained" not in _codes(errors)

    @pytest.mark.parametrize(
        "file_kwargs",
        [
            pytest.param({"info": {}}, id="no-info"),
            pytest.param({"include_forms": False, "qc": PASS_QC}, id="no-forms-json"),
            pytest.param({"forms_json": {}}, id="empty-forms-json"),
        ],
    )
    def test_missing_metadata_is_not_a_match(
        self, create_rejection_harness, create_visit_file, file_kwargs
    ):
        """An exact match cannot be satisfied by absent metadata."""
        visit_file = create_visit_file(**file_kwargs)
        harness = create_rejection_harness(visit_file=visit_file)

        errors = _reject(harness, _row())

        visit_file.update_info.assert_not_called()
        assert "existing-visit-retained" not in _codes(errors)


class TestNoExistingVisit:
    """Without an existing acquisition the behaviour is unchanged."""

    def test_no_acquisition_file(self, create_rejection_harness):
        """Only the preprocessing errors reach the visit error log."""
        harness = create_rejection_harness(visit_file=None)

        errors = _reject(harness, _row())

        assert "existing-visit-retained" not in _codes(errors)

    def test_no_subject(self, create_rejection_harness):
        """A participant with no subject container has no existing visit."""
        harness = create_rejection_harness(subject_found=False)

        errors = _reject(harness, _row())

        harness.subject.find_acquisition_file.assert_not_called()
        assert "existing-visit-retained" not in _codes(errors)


class TestLookupFailure:
    """A lookup that cannot be completed is logged, never assumed."""

    def test_api_exception_logged(self, create_rejection_harness, caplog):
        """An API failure during lookup is logged, not assumed to be a miss."""
        harness = create_rejection_harness(lookup_error=True)

        with caplog.at_level(logging.ERROR):
            errors = _reject(harness, _row())

        assert "Failed to check whether an existing visit file" in caplog.text
        assert "existing-visit-retained" not in _codes(errors)
        # a system level problem is not reported to the submitter
        assert not _codes(errors)

    def test_unresolvable_label_logged(self, create_rejection_harness, caplog):
        """A record that cannot produce container labels is logged."""
        harness = create_rejection_harness()

        # visitnum is part of the session template, dropping it breaks it
        row = _row()
        del row[FieldNames.VISITNUM]

        with (
            caplog.at_level(logging.ERROR),
            patch("form_csv_app.main.QCStatusLogManager") as log_manager,
            patch("form_csv_app.main.FileVisitAnnotator"),
        ):
            harness.visitor._CSVTransformVisitor__handle_rejected_visit(  # noqa: SLF001
                input_record=row, line_num=1
            )
            calls = log_manager.return_value.update_qc_log.call_args_list

        assert "Failed to check whether an existing visit file" in caplog.text
        assert not _codes(list(calls[0].kwargs["errors"]))


class TestDateKeyedModule:
    """Modules without visitnum only compare ptid and their date field."""

    def test_stale_visitnum_ignored(
        self, create_rejection_harness, create_visit_file, np_module_configs
    ):
        """A visitnum that is not required is not compared."""
        visit_file = create_visit_file(
            forms_json={
                FieldNames.PTID: "110001",
                "npformdate": "2024-03-15",
                FieldNames.VISITNUM: "99",
            },
            qc=PASS_QC,
            name="NACC000001_NP-RECORD-2024-03-15_NP.json",
        )
        harness = create_rejection_harness(
            visit_file=visit_file, module_configs=np_module_configs, module="NP"
        )

        errors = _reject(harness, _np_row())
        note = next(
            error for error in errors if error.error_code == "existing-visit-retained"
        )

        assert "visit number" not in note.message
        assert note.location.column_name == "npformdate"  # type: ignore[union-attr]


class TestTransformFailure:
    """The transform failure branch gets the same handling."""

    def test_passed_qc_visit_retained(
        self, create_rejection_harness, create_visit_file
    ):
        """A QC passed visit is left alone when transformation fails."""
        visit_file = create_visit_file(
            forms_json=STORED_VISIT, qc=PASS_QC, tags=["form-qc-checker-PASS"]
        )
        harness = create_rejection_harness(
            visit_file=visit_file, transform_result=False
        )

        with (
            patch("form_csv_app.main.QCStatusLogManager") as log_manager,
            patch("form_csv_app.main.FileVisitAnnotator"),
        ):
            assert not harness.visitor.visit_row(_row(), 1)
            calls = log_manager.return_value.update_qc_log.call_args_list

        errors = list(calls[0].kwargs["errors"])
        visit_file.update_info.assert_not_called()
        visit_file.delete_tag.assert_not_called()
        assert "existing-visit-retained" in _codes(errors)

    def test_failed_qc_visit_reset(self, create_rejection_harness, create_visit_file):
        """A visit that has not passed QC is reset when transformation
        fails."""
        visit_file = create_visit_file(forms_json=STORED_VISIT, qc=FAIL_QC)
        harness = create_rejection_harness(
            visit_file=visit_file, transform_result=False
        )

        with (
            patch("form_csv_app.main.QCStatusLogManager"),
            patch("form_csv_app.main.FileVisitAnnotator"),
        ):
            assert not harness.visitor.visit_row(_row(), 1)

        visit_file.update_info.assert_called_once()


class TestUnaffectedPaths:
    """Records that are accepted must not trigger any lookup."""

    def test_successful_record_skips_lookup(
        self, create_rejection_harness, create_visit_file
    ):
        """No visit file lookup happens when the record is accepted."""
        visit_file = create_visit_file(forms_json=STORED_VISIT, qc=PASS_QC)
        harness = create_rejection_harness(
            visit_file=visit_file, preprocess_result=True
        )

        with (
            patch("form_csv_app.main.QCStatusLogManager") as log_manager,
            patch("form_csv_app.main.FileVisitAnnotator"),
        ):
            log_manager.return_value.get_qc_log_filename.return_value = "log.log"
            assert harness.visitor.visit_row(_row(), 1)
            assert harness.visitor.process_current_batch()

        harness.project.find_subject.assert_not_called()
        visit_file.update_info.assert_not_called()
        assert len(harness.visitor.transformed_records) == 1
