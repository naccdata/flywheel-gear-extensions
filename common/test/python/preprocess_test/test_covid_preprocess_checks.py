# ruff: noqa: SLF001
"""Tests the pre-processing checks for a module that accepts more than one
initial visit packet (COVID).

The Flywheel querying is replaced at the FormsStore seam, the store
double below serves a fixed list of visit records for one subject and
derives the dataview rows from them the same way the real store does.
"""

from typing import Any, Dict, List, Optional

import pytest
from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from datastore.forms_store import FormsStore
from keys.keys import MetadataKeys, PreprocessingChecks, SysErrorCodes
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import preprocess_errors
from preprocess.preprocessor import FormPreprocessor
from preprocess.preprocessor_helpers import PreprocessingContext

NACCID = "NACC000000"
MODULE = "COVID"


def visit_record(
    visitdate: str,
    packet: str,
    forms: Optional[List[str]] = None,
    modes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Creates a COVID visit record with the mode variables for `forms` set.

    A module marks a form that was not submitted either by dropping the
    mode variable, which is what the COVID transformations do, or by
    keeping the variable with the value 0. Pass `modes` to set explicit
    mode values.
    """
    record = {
        "naccid": NACCID,
        "ptid": "dummy-ptid",
        "adcid": "0",
        "visitdate": visitdate,
        "packet": packet,
        "formver": "2.0",
        "module": MODULE,
    }
    record.update({f"mode{form}": "1" for form in (forms if forms else [])})
    record.update({f"mode{form}": mode for form, mode in (modes or {}).items()})
    return record


def create_context(
    visitdate: str,
    packet: str,
    forms: Optional[List[str]] = None,
    batch_records: Optional[List[Dict[str, Any]]] = None,
    modes: Optional[Dict[str, str]] = None,
) -> PreprocessingContext:
    """Creates a preprocessing context for the record being submitted."""
    return PreprocessingContext(
        subject_lbl=NACCID,
        input_record=visit_record(visitdate, packet, forms, modes),
        line_num=1,
        batch_records=batch_records if batch_records else [],
    )


class CovidFormsStore(FormsStore):
    """Forms store double serving a fixed list of visits for one subject."""

    LEGACY_PREFIX = "legacy-"

    def __init__(self) -> None:
        self.visits: List[Dict[str, Any]] = []
        self.legacy_visits: List[Dict[str, Any]] = []
        self.visit_reads = 0

    def set_visits(self, visits: List[Dict[str, Any]]) -> None:
        """Sets the existing ingest visits for the subject."""
        self.visits = visits

    def set_legacy_visits(self, visits: List[Dict[str, Any]]) -> None:
        """Sets the existing legacy visits for the subject."""
        self.legacy_visits = visits

    def is_new_subject(self, subject_lbl: str) -> bool:
        return not self.visits and not self.legacy_visits

    def query_form_data(self, **kwargs) -> Optional[List[Dict[str, Any]]]:
        legacy = bool(kwargs.get("legacy"))
        visits = self.legacy_visits if legacy else self.visits
        if not visits:
            return None

        prefix = self.LEGACY_PREFIX if legacy else ""
        columns = [kwargs["search_col"], *(kwargs.get("extra_columns") or [])]
        rows = []
        for index, visit in enumerate(visits):
            row: Dict[str, Any] = {
                "file.name": f"{prefix}visit-{index}.json",
                "file.parents.acquisition": f"{prefix}{index}",
            }
            row.update(
                {MetadataKeys.get_column_key(col): visit[col] for col in columns}
            )
            rows.append(row)

        search_col = MetadataKeys.get_column_key(kwargs["search_col"])
        return sorted(rows, key=lambda row: row[search_col], reverse=True)

    def get_visit_data(self, *, file_name: str, acq_id: str) -> Dict[str, Any] | None:
        self.visit_reads += 1
        if acq_id.startswith(self.LEGACY_PREFIX):
            return self.legacy_visits[int(acq_id.removeprefix(self.LEGACY_PREFIX))]

        return self.visits[int(acq_id)]


def create_processor(module_configs: ModuleConfigs):
    """Creates a COVID preprocessor for testing.

    Returns:
        FormPreprocessor, ListErrorWriter to check the error raised, and the
        forms store to control the existing visits per test
    """
    forms_store = CovidFormsStore()
    error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

    form_configs = FormProjectConfigs(
        primary_key=FieldNames.NACCID,
        accepted_modules=[MODULE],
        module_configs={MODULE: module_configs},
    )
    processor = FormPreprocessor(
        form_configs=form_configs,
        forms_store=forms_store,
        module=MODULE,
        module_configs=module_configs,
        error_writer=error_writer,
    )

    return processor, error_writer, forms_store


def assert_error_raised(
    error_writer: ListErrorWriter,
    error_code: str,
    extra_args: Optional[List[Any]] = None,
) -> None:
    """Ensure the expected error was set in the error writer."""
    assert len(error_writer.errors()) == 1
    file_error = error_writer.errors()[0]

    message = preprocess_errors[error_code]
    if extra_args:
        message = message.format(*extra_args)

    assert file_error.error_code == error_code
    assert file_error.message == message
    error_writer.clear()


class TestCovidInitialVisit:
    """Tests the covid-ivp check."""

    def test_fvp_without_ivp(self, covid_module_configs, covid_pp_context):
        """A follow-up packet requires an existing initial packet."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert not processor._check_covid_ivp(covid_pp_context)
        assert_error_raised(error_writer, SysErrorCodes.MISSING_IVP)

    def test_ivp_for_new_subject(self, covid_module_configs):
        """An initial packet is accepted for a participant with no visits."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert processor._check_covid_ivp(create_context("2020-01-01", "CV"))
        assert not error_writer.errors()

    def test_fvp_after_latest_ivp(self, covid_module_configs):
        """A follow-up packet after all the initial packets is accepted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-01-01", "CV"), visit_record("2020-06-01", "CV")]
        )

        assert processor._check_covid_ivp(create_context("2020-09-01", "FCV"))
        assert not error_writer.errors()

    def test_fvp_on_latest_ivp_date(self, covid_module_configs):
        """A follow-up packet cannot have the date of an initial packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-01-01", "CV"), visit_record("2020-06-01", "CV")]
        )

        assert not processor._check_covid_ivp(create_context("2020-06-01", "FCV"))
        assert_error_raised(error_writer, SysErrorCodes.LOWER_FVP_VISITDATE)

    def test_fvp_before_latest_ivp(self, covid_module_configs):
        """The comparison is against the latest initial packet, not the
        earliest."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-01-01", "CV"), visit_record("2020-06-01", "CV")]
        )

        assert not processor._check_covid_ivp(create_context("2020-03-01", "FCV"))
        assert_error_raised(error_writer, SysErrorCodes.LOWER_FVP_VISITDATE)

    def test_ivp_after_existing_fvp(self, covid_module_configs):
        """An initial packet cannot be dated after a follow-up packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "FCV")])

        assert not processor._check_covid_ivp(create_context("2020-09-01", "CV"))
        assert_error_raised(error_writer, SysErrorCodes.HIGHER_IVP_VISITDATE)

    def test_ivp_on_existing_fvp_date(self, covid_module_configs):
        """An initial packet cannot have the date of a follow-up packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "FCV")])

        assert not processor._check_covid_ivp(create_context("2020-06-01", "CV"))
        assert_error_raised(error_writer, SysErrorCodes.HIGHER_IVP_VISITDATE)

    def test_ivp_before_earliest_fvp(self, covid_module_configs):
        """An initial packet before all the follow-up packets is accepted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-06-01", "FCV"), visit_record("2020-09-01", "FCV")]
        )

        assert processor._check_covid_ivp(create_context("2020-01-01", "CV"))
        assert not error_writer.errors()

    def test_ivp_between_two_fvps(self, covid_module_configs):
        """The comparison is against the earliest follow-up packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-03-01", "FCV"), visit_record("2020-09-01", "FCV")]
        )

        assert not processor._check_covid_ivp(create_context("2020-06-01", "CV"))
        assert_error_raised(error_writer, SysErrorCodes.HIGHER_IVP_VISITDATE)

    def test_ivp_update(self, covid_module_configs):
        """An update to an initial packet with a later follow-up packet is
        accepted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-01-01", "CV"), visit_record("2020-06-01", "FCV")]
        )

        assert processor._check_covid_ivp(create_context("2020-01-01", "CV"))
        assert not error_writer.errors()

    def test_fvp_update(self, covid_module_configs):
        """An update to an existing follow-up packet is accepted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [visit_record("2020-01-01", "CV"), visit_record("2020-06-01", "FCV")]
        )

        assert processor._check_covid_ivp(create_context("2020-06-01", "FCV"))
        assert not error_writer.errors()

    def test_fvp_form_submitted_on_ivp(self, covid_module_configs):
        """A form submitted with the follow-up packet is on the initial
        packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-01-01", "CV", ["f2"])])

        assert processor._check_covid_ivp(create_context("2020-06-01", "FCV", ["f2"]))
        assert not error_writer.errors()

    def test_fvp_form_not_on_any_ivp(self, covid_module_configs):
        """A form that none of the initial packets have is rejected."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [
                visit_record("2020-01-01", "CV", ["f2"]),
                visit_record("2020-06-01", "CV", ["f2"]),
            ]
        )

        assert not processor._check_covid_ivp(
            create_context("2020-09-01", "FCV", ["f2", "f3"])
        )
        assert_error_raised(
            error_writer, SysErrorCodes.MISSING_IVP_FORMS, extra_args=[["f3"]]
        )

    def test_fvp_form_on_earlier_ivp_only(self, covid_module_configs):
        """The form can be on any of the initial packets, not only the
        latest."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits(
            [
                visit_record("2020-01-01", "CV", ["f2"]),
                visit_record("2020-06-01", "CV"),
            ]
        )

        assert processor._check_covid_ivp(create_context("2020-09-01", "FCV", ["f2"]))
        assert not error_writer.errors()

    def test_fvp_form_with_mode_zero_not_submitted(self, covid_module_configs):
        """A mode variable of 0 means the form was not submitted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-01-01", "CV")])

        assert processor._check_covid_ivp(
            create_context("2020-06-01", "FCV", modes={"f2": "0"})
        )
        assert not error_writer.errors()

    def test_ivp_form_with_mode_zero_does_not_satisfy(self, covid_module_configs):
        """An initial packet that marked the form 0 has not submitted it."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-01-01", "CV", modes={"f2": "0"})])

        assert not processor._check_covid_ivp(
            create_context("2020-06-01", "FCV", ["f2"])
        )
        assert_error_raised(
            error_writer, SysErrorCodes.MISSING_IVP_FORMS, extra_args=[["f2"]]
        )

    def test_fvp_without_optional_forms(self, covid_module_configs):
        """No visit file is read when no optional forms are submitted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-01-01", "CV", ["f2"])])

        assert processor._check_covid_ivp(create_context("2020-06-01", "FCV"))
        assert not error_writer.errors()
        assert store.visit_reads == 0

    def test_ivp_in_current_batch(self, covid_module_configs):
        """An initial packet accepted in the current batch satisfies the
        follow-up packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        batch = [visit_record("2020-01-01", "CV", ["f2"])]

        assert processor._check_covid_ivp(
            create_context("2020-06-01", "FCV", ["f2"], batch_records=batch)
        )
        assert not error_writer.errors()
        assert store.visit_reads == 0

    def test_multiple_ivps_in_current_batch(self, covid_module_configs):
        """Forms are collected from all the initial packets in the batch."""
        processor, error_writer, _ = create_processor(covid_module_configs)
        batch = [
            visit_record("2020-01-01", "CV", ["f2"]),
            visit_record("2020-03-01", "CV", ["f3"]),
        ]

        assert processor._check_covid_ivp(
            create_context("2020-06-01", "FCV", ["f2", "f3"], batch_records=batch)
        )
        assert not error_writer.errors()

    def test_fvp_in_current_batch_blocks_ivp(self, covid_module_configs):
        """A follow-up packet accepted in the current batch is compared
        against."""
        processor, error_writer, _ = create_processor(covid_module_configs)
        batch = [visit_record("2020-06-01", "FCV")]

        assert not processor._check_covid_ivp(
            create_context("2020-09-01", "CV", batch_records=batch)
        )
        assert_error_raised(error_writer, SysErrorCodes.HIGHER_IVP_VISITDATE)

    def test_optional_forms_not_defined(self, covid_module_configs):
        """The form check is skipped when no optional forms are configured."""
        module_configs = covid_module_configs.model_copy(
            update={"optional_forms": None}
        )
        processor, error_writer, store = create_processor(module_configs)
        store.set_visits([visit_record("2020-01-01", "CV")])

        assert processor._check_covid_ivp(create_context("2020-06-01", "FCV", ["f2"]))
        assert not error_writer.errors()

    def test_fvp_with_legacy_ivp(self, covid_module_configs):
        """A legacy initial packet satisfies the follow-up packet."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_legacy_visits([visit_record("2020-01-01", "CV")])

        assert processor._check_covid_ivp(create_context("2020-06-01", "FCV"))
        assert not error_writer.errors()

    def test_fvp_before_legacy_ivp(self, covid_module_configs):
        """Legacy initial packets take part in the visit date ordering."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_legacy_visits([visit_record("2020-06-01", "CV")])

        assert not processor._check_covid_ivp(create_context("2020-03-01", "FCV"))
        assert_error_raised(error_writer, SysErrorCodes.LOWER_FVP_VISITDATE)

    def test_fvp_after_latest_of_ingest_and_legacy_ivp(self, covid_module_configs):
        """The latest initial packet can be the ingest one or the legacy
        one."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_legacy_visits([visit_record("2020-01-01", "CV")])
        store.set_visits([visit_record("2020-06-01", "CV")])

        assert processor._check_covid_ivp(create_context("2020-09-01", "FCV"))
        assert not error_writer.errors()

        assert not processor._check_covid_ivp(create_context("2020-03-01", "FCV"))
        assert_error_raised(error_writer, SysErrorCodes.LOWER_FVP_VISITDATE)

    def test_fvp_form_on_legacy_ivp(self, covid_module_configs):
        """A form submitted with a legacy initial packet satisfies the
        check."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_legacy_visits([visit_record("2020-01-01", "CV", ["f2"])])

        assert processor._check_covid_ivp(create_context("2020-06-01", "FCV", ["f2"]))
        assert not error_writer.errors()

    def test_fvp_form_not_on_legacy_ivp(self, covid_module_configs):
        """A form that the legacy initial packet does not have is rejected."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_legacy_visits([visit_record("2020-01-01", "CV", ["f2"])])

        assert not processor._check_covid_ivp(
            create_context("2020-06-01", "FCV", ["f2", "f3"])
        )
        assert_error_raised(
            error_writer, SysErrorCodes.MISSING_IVP_FORMS, extra_args=[["f3"]]
        )

    def test_ivp_with_legacy_ivp_only(self, covid_module_configs):
        """A new initial packet is accepted when only legacy visits exist."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_legacy_visits([visit_record("2020-01-01", "CV")])

        assert processor._check_covid_ivp(create_context("2020-06-01", "CV"))
        assert not error_writer.errors()

    def test_unknown_packet_code(self, covid_module_configs):
        """An unexpected packet code is left to the packet check."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert processor._check_covid_ivp(create_context("2020-06-01", "XX"))
        assert not error_writer.errors()


class TestCovidForms:
    """Tests the covid-forms check."""

    def test_no_forms_submitted(self, covid_module_configs):
        """A packet without any of the optional forms is rejected."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert not processor._check_covid_forms(create_context("2020-06-01", "CV"))
        assert_error_raised(
            error_writer,
            SysErrorCodes.COVID_FORMS_REQUIRED,
            extra_args=[["f2", "f3"]],
        )

    def test_all_modes_zero(self, covid_module_configs):
        """A form marked 0 does not count as submitted."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert not processor._check_covid_forms(
            create_context("2020-06-01", "CV", modes={"f2": "0", "f3": "0"})
        )
        assert_error_raised(
            error_writer,
            SysErrorCodes.COVID_FORMS_REQUIRED,
            extra_args=[["f2", "f3"]],
        )

    def test_one_form_submitted(self, covid_module_configs):
        """One of the optional forms is enough."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert processor._check_covid_forms(create_context("2020-06-01", "CV", ["f3"]))
        assert not error_writer.errors()

    def test_all_forms_submitted(self, covid_module_configs):
        """All of the optional forms is accepted."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert processor._check_covid_forms(
            create_context("2020-06-01", "FCV", ["f2", "f3"])
        )
        assert not error_writer.errors()

    def test_optional_forms_not_defined(self, covid_module_configs):
        """The check is skipped when no optional forms are configured."""
        module_configs = covid_module_configs.model_copy(
            update={"optional_forms": None}
        )
        processor, error_writer, _ = create_processor(module_configs)

        assert processor._check_covid_forms(create_context("2020-06-01", "CV"))
        assert not error_writer.errors()

    def test_unknown_packet_code(self, covid_module_configs):
        """An unexpected packet code is left to the packet check."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert processor._check_covid_forms(create_context("2020-06-01", "XX"))
        assert not error_writer.errors()


class TestCovidVisitConflict:
    """Tests the covid-visit-conflict check."""

    def test_no_existing_visits(self, covid_module_configs):
        """A participant with no visits has no conflict."""
        processor, error_writer, _ = create_processor(covid_module_configs)

        assert processor._check_covid_visit_conflict(create_context("2020-06-01", "CV"))
        assert not error_writer.errors()

    def test_no_visit_on_same_date(self, covid_module_configs):
        """A visit on a different date is not a conflict."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-01-01", "CV")])

        assert processor._check_covid_visit_conflict(
            create_context("2020-06-01", "FCV")
        )
        assert not error_writer.errors()

    def test_same_date_different_packet(self, covid_module_configs):
        """A different packet code on the same date is rejected."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV")])

        assert not processor._check_covid_visit_conflict(
            create_context("2020-06-01", "FCV")
        )
        assert_error_raised(error_writer, SysErrorCodes.DIFF_PACKET, extra_args=["CV"])

    def test_same_date_same_forms(self, covid_module_configs):
        """An update with the same forms is accepted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", ["f2"])])

        assert processor._check_covid_visit_conflict(
            create_context("2020-06-01", "CV", ["f2"])
        )
        assert not error_writer.errors()

    def test_same_date_form_added(self, covid_module_configs):
        """An update that adds a form is accepted."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", ["f2"])])

        assert processor._check_covid_visit_conflict(
            create_context("2020-06-01", "CV", ["f2", "f3"])
        )
        assert not error_writer.errors()

    def test_same_date_form_removed(self, covid_module_configs):
        """An update that drops a previously submitted form is rejected."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", ["f2", "f3"])])

        assert not processor._check_covid_visit_conflict(
            create_context("2020-06-01", "CV", ["f2"])
        )
        assert_error_raised(
            error_writer,
            SysErrorCodes.COVID_FORM_CONFLICT,
            extra_args=[["f2", "f3"], ["f2"]],
        )

    def test_same_date_form_swapped(self, covid_module_configs):
        """A submission with a different form for the same visit is
        rejected."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", ["f2"])])

        assert not processor._check_covid_visit_conflict(
            create_context("2020-06-01", "CV", ["f3"])
        )
        assert_error_raised(
            error_writer,
            SysErrorCodes.COVID_FORM_CONFLICT,
            extra_args=[["f2"], ["f3"]],
        )

    def test_same_date_form_set_to_mode_zero(self, covid_module_configs):
        """Marking a previously submitted form 0 is a removal."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", ["f2"])])

        assert not processor._check_covid_visit_conflict(
            create_context("2020-06-01", "CV", modes={"f2": "0"})
        )
        assert_error_raised(
            error_writer,
            SysErrorCodes.COVID_FORM_CONFLICT,
            extra_args=[["f2"], []],
        )

    def test_same_date_mode_zero_on_both(self, covid_module_configs):
        """A form marked 0 in both submissions is not a removal."""
        processor, error_writer, store = create_processor(covid_module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", modes={"f2": "0"})])

        assert processor._check_covid_visit_conflict(
            create_context("2020-06-01", "CV", modes={"f2": "0"})
        )
        assert not error_writer.errors()

    def test_optional_forms_not_defined(self, covid_module_configs):
        """Only the packet codes are compared when no optional forms are
        configured."""
        module_configs = covid_module_configs.model_copy(
            update={"optional_forms": None}
        )
        processor, error_writer, store = create_processor(module_configs)
        store.set_visits([visit_record("2020-06-01", "CV", ["f2"])])

        assert processor._check_covid_visit_conflict(create_context("2020-06-01", "CV"))
        assert not error_writer.errors()


class TestCovidCheckRegistration:
    """Tests the new checks are registered and reportable."""

    def test_checks_are_defined(self):
        """The check names are accepted in the module configurations."""
        assert PreprocessingChecks.is_check_defined(PreprocessingChecks.COVID_FORMS)
        assert PreprocessingChecks.is_check_defined(
            PreprocessingChecks.COVID_VISIT_CONFLICT
        )
        assert PreprocessingChecks.is_check_defined(PreprocessingChecks.COVID_IVP)

    def test_check_evaluation_order(self, covid_module_configs):
        """The COVID checks are evaluated in the required order.

        The forms check comes first, the other two compare the forms in
        the record. The visit conflict check comes before the IVP check,
        a follow-up packet submitted for the date of an existing initial
        packet fails both and the packet conflict is the more actionable
        error.
        """
        processor, _, _ = create_processor(covid_module_configs)
        checks = [
            check.__name__ for check in processor._FormPreprocessor__preprocess_checks
        ]

        assert (
            checks.index("_check_covid_forms")
            < checks.index("_check_covid_visit_conflict")
            < checks.index("_check_covid_ivp")
        )

    @pytest.mark.parametrize(
        "error_code",
        [
            SysErrorCodes.HIGHER_IVP_VISITDATE,
            SysErrorCodes.MISSING_IVP_FORMS,
            SysErrorCodes.DIFF_PACKET,
            SysErrorCodes.COVID_FORM_CONFLICT,
            SysErrorCodes.COVID_FORMS_REQUIRED,
        ],
    )
    def test_error_message_defined(self, error_code):
        """Every new error code has a message, some call sites index the
        message dictionary directly."""
        assert preprocess_errors[error_code]
