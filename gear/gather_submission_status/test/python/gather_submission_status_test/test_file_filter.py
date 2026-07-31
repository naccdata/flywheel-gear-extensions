"""Tests for _should_process_file filter equivalence.

Validates: Requirements 6.3 / Property 1: Filter Equivalence
"""

import datetime
import re

from gather_submission_status_app.main import _should_process_file
from hypothesis import given
from hypothesis import strategies as st
from nacc_common.qc_report import QC_FILENAME_PATTERN


class TestShouldProcessFileUnit:
    """Unit tests for _should_process_file."""

    def test_matching_filename_accepted(self, qc_matcher: re.Pattern[str]) -> None:
        """Filename matching QC pattern with ptid in ptid_set and module in
        modules is accepted."""
        filename = "PT001_2024-01-15_UDS_qc-status.log"
        ptid_set = {"PT001"}
        modules = {"UDS"}

        result = _should_process_file(
            filename=filename,
            matcher=qc_matcher,
            ptid_set=ptid_set,
            modules=modules,
        )

        assert result is True

    def test_non_matching_pattern_rejected(self, qc_matcher: re.Pattern[str]) -> None:
        """Filename not matching QC pattern is rejected."""
        filename = "not-a-qc-file.csv"
        ptid_set = {"PT001"}
        modules = {"UDS"}

        result = _should_process_file(
            filename=filename,
            matcher=qc_matcher,
            ptid_set=ptid_set,
            modules=modules,
        )

        assert result is False

    def test_ptid_not_in_set_rejected(self, qc_matcher: re.Pattern[str]) -> None:
        """Filename with ptid NOT in ptid_set is rejected."""
        filename = "PT999_2024-01-15_UDS_qc-status.log"
        ptid_set = {"PT001", "PT002"}
        modules = {"UDS"}

        result = _should_process_file(
            filename=filename,
            matcher=qc_matcher,
            ptid_set=ptid_set,
            modules=modules,
        )

        assert result is False

    def test_module_not_in_modules_rejected(self, qc_matcher: re.Pattern[str]) -> None:
        """Filename with module NOT in modules is rejected."""
        filename = "PT001_2024-01-15_MDS_qc-status.log"
        ptid_set = {"PT001"}
        modules = {"UDS", "LBD"}

        result = _should_process_file(
            filename=filename,
            matcher=qc_matcher,
            ptid_set=ptid_set,
            modules=modules,
        )

        assert result is False

    def test_case_insensitive_module_matching(
        self, qc_matcher: re.Pattern[str]
    ) -> None:
        """Module matching is case-insensitive: 'uds' in filename matches 'UDS'
        in modules."""
        filename = "PT001_2024-01-15_uds_qc-status.log"
        ptid_set = {"PT001"}
        modules = {"UDS"}

        result = _should_process_file(
            filename=filename,
            matcher=qc_matcher,
            ptid_set=ptid_set,
            modules=modules,
        )

        assert result is True


# Hypothesis strategies for generating valid QC filenames
# ptid must match [!-~]{1,10} (ASCII 33-126). Exclude underscore to avoid
# ambiguity with the literal '_' separators in the pattern.
_ptid_alphabet = st.characters(
    min_codepoint=33, max_codepoint=126, blacklist_characters="_"
)
_ptid_strategy = st.text(alphabet=_ptid_alphabet, min_size=1, max_size=10)
_date_strategy = st.dates(
    min_value=datetime.date(1000, 1, 1), max_value=datetime.date(9999, 12, 31)
).map(lambda d: d.strftime("%Y-%m-%d"))
# module must match \w+ — use ASCII letters and digits only to stay in the
# ASCII subset that the regex expects.
_module_alphabet = st.characters(
    min_codepoint=48,
    max_codepoint=122,
    whitelist_categories=("Ll", "Lu", "Nd"),
)
_module_strategy = st.text(alphabet=_module_alphabet, min_size=1, max_size=10)


@given(ptid=_ptid_strategy, date=_date_strategy, module=_module_strategy)
def test_valid_filename_always_accepted(ptid: str, date: str, module: str) -> None:
    """**Validates: Requirements 6.3**

    Property: For any filename matching the QC pattern with ptid in ptid_set
    and module (uppercased) in modules, _should_process_file returns True.
    """
    filename = f"{ptid}_{date}_{module}_qc-status.log"
    matcher = re.compile(QC_FILENAME_PATTERN)
    ptid_set = {ptid}
    modules = {module.upper()}

    result = _should_process_file(
        filename=filename,
        matcher=matcher,
        ptid_set=ptid_set,
        modules=modules,
    )

    assert result is True
