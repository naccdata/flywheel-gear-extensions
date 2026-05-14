"""Property test for list_submissions.

**Feature: nacc-common-data-access,
  Property 4: Submission listing filter correctness**
**Validates: Requirements 6.1, 6.2, 6.3, 6.4**
"""

import datetime
from typing import Optional
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_data import list_submissions

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# PTID: printable non-whitespace ASCII chars, 1-10 length
# Matches QC_FILENAME_PATTERN group 1: [!-~]{1,10}
# - Exclude underscore to prevent ambiguity in filename parsing
# - Use alphanumeric chars that won't be altered by normalize_ptid
#   (which strips leading zeros). Start with a letter to avoid
#   all-zero or leading-zero PTIDs that normalize to something different.
ptid_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9]{0,9}", fullmatch=True)

# Module: word characters (\w+), at least 1 char
module_strategy = st.from_regex(r"[A-Za-z][A-Za-z0-9]{0,5}", fullmatch=True)

# Date: YYYY-MM-DD format with 4-digit year (required by QC_FILENAME_PATTERN)
date_strategy = st.dates(
    min_value=datetime.date(1000, 1, 1),
    max_value=datetime.date(9999, 12, 31),
).map(lambda d: d.strftime("%Y-%m-%d"))


@st.composite
def qc_filename_strategy(draw: st.DrawFn) -> tuple[str, str, str, str]:
    """Generate a valid QC log filename and its components.

    Returns (filename, ptid, date, module).
    """
    ptid = draw(ptid_strategy)
    date = draw(date_strategy)
    module = draw(module_strategy)
    filename = f"{ptid}_{date}_{module}_qc-status.log"
    return (filename, ptid, date, module)


def _make_mock_file(filename: str) -> MagicMock:
    """Create a mock FileEntry with the given filename and minimal QC info."""
    mock_file = MagicMock()
    mock_file.name = filename
    mock_file.reload.return_value = mock_file
    # Provide empty qc info so FileQCModel.create succeeds with empty qc
    mock_file.info = {"qc": {}}
    return mock_file


@st.composite
def files_and_filters_strategy(
    draw: st.DrawFn,
) -> tuple[list[tuple[str, str, str, str]], Optional[set[str]], Optional[set[str]]]:
    """Generate a list of QC log file entries and a filter combination.

    Returns (file_entries, modules_filter, ptids_filter).
    """
    file_entries = draw(
        st.lists(
            qc_filename_strategy(),
            min_size=1,
            max_size=10,
            unique_by=lambda entry: entry[0],
        )
    )

    all_ptids = sorted({entry[1] for entry in file_entries})
    all_modules_upper = sorted({entry[3].upper() for entry in file_entries})

    # Choose filter mode: none, modules only, ptids only, both
    mode = draw(st.sampled_from(["none", "modules", "ptids", "both"]))

    modules_filter: Optional[set[str]] = None
    ptids_filter: Optional[set[str]] = None

    if mode in ("modules", "both"):
        # Pick a subset of known modules, possibly with extras
        known_subset = draw(
            st.lists(
                st.sampled_from(all_modules_upper),
                min_size=0,
                max_size=len(all_modules_upper),
                unique=True,
            )
        )
        extra = draw(st.lists(module_strategy, min_size=0, max_size=2, unique=True))
        modules_filter = {m.upper() for m in known_subset} | {m.upper() for m in extra}

    if mode in ("ptids", "both"):
        # Pick a subset of known ptids, possibly with extras
        known_subset = draw(
            st.lists(
                st.sampled_from(all_ptids),
                min_size=0,
                max_size=len(all_ptids),
                unique=True,
            )
        )
        extra = draw(st.lists(ptid_strategy, min_size=0, max_size=2, unique=True))
        ptids_filter = set(known_subset) | set(extra)

    return (file_entries, modules_filter, ptids_filter)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(data=files_and_filters_strategy())
@settings(max_examples=100)
def test_submission_listing_filter_correctness(
    data: tuple[
        list[tuple[str, str, str, str]], Optional[set[str]], Optional[set[str]]
    ],
):
    """Property 4: Submission listing filter correctness.

    **Feature: nacc-common-data-access,
      Property 4: Submission listing filter correctness**
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

    For any set of QC log files and any combination of modules and ptids
    filters, every dict in the list returned by list_submissions SHALL
    have a "ptid" value in the ptids set (when provided) AND a "module"
    value (compared case-insensitively) in the modules set (when provided).
    When neither filter is provided, the result SHALL include all QC log
    files.
    """
    file_entries, modules_filter, ptids_filter = data

    # Arrange — build mock project with mock FileEntry objects
    mock_files = [_make_mock_file(entry[0]) for entry in file_entries]
    mock_project = MagicMock()
    mock_project.files = mock_files

    # Act
    result = list_submissions(mock_project, modules=modules_filter, ptids=ptids_filter)

    # Assert — filter correctness on every result dict
    for item in result:
        if ptids_filter is not None:
            assert item["ptid"] in ptids_filter, (
                f"ptid {item['ptid']!r} not in filter {ptids_filter}"
            )
        if modules_filter is not None:
            assert item["module"].upper() in modules_filter, (
                f"module {item['module']!r} (upper: {item['module'].upper()!r}) "
                f"not in filter {modules_filter}"
            )

    # When no filters are provided, result must include all QC log files
    if modules_filter is None and ptids_filter is None:
        assert len(result) == len(file_entries), (
            f"Expected {len(file_entries)} results with no filters, got {len(result)}"
        )
