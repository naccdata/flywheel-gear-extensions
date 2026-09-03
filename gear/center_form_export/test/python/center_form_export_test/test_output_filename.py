"""Property test for output filename pattern.

Feature: center-form-export, Property 4: Output filename conforms to naming pattern
Validates: Requirements 5.1, 5.2
"""

import re
from datetime import date

from center_form_export_app.run import _output_stamp
from data_requests.data_request import formver_label
from hypothesis import given, settings
from hypothesis import strategies as st

# Regex patterns for valid output filenames. Every name carries a
# study_id and a source_id ahead of the module, so the default shape has
# three leading segments and the formver-split shape four.
#
# The formver segment is the one field permitted a '.' (e.g. LBD "v3.1"):
# it is gear-derived, occupies a fixed non-final position, and so cannot
# be mistaken for a segment boundary the way a '-' would. It may also
# carry letters, since formver_label refuses only values that would break
# the name, and passes odd-but-safe ones through. Every caller-supplied
# segment stays strictly alphanumeric.
_FORMVER_SEGMENT = r"(?:v[A-Za-z0-9.]+|unknown)"
DEFAULT_PATTERN = re.compile(
    r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-\d{4}-\d{2}-\d{2}\.csv$"
)
FORMVER_PATTERN = re.compile(
    r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-"
    + _FORMVER_SEGMENT
    + r"-\d{4}-\d{2}-\d{2}\.csv$"
)
# With a caller-supplied run_id, one segment is appended after the date
RUN_ID_DEFAULT_PATTERN = re.compile(
    r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-\d{4}-\d{2}-\d{2}-[a-zA-Z0-9]+\.csv$"
)
RUN_ID_FORMVER_PATTERN = re.compile(
    r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-"
    + _FORMVER_SEGMENT
    + r"-\d{4}-\d{2}-\d{2}-[a-zA-Z0-9]+\.csv$"
)

# Strategies - restricted to ASCII alphanumeric to match real gear config values
_ASCII_ALPHANUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

study_id_strategy = st.text(
    alphabet=_ASCII_ALPHANUM,
    min_size=1,
    max_size=10,
)
module_name_strategy = st.text(
    alphabet=_ASCII_ALPHANUM,
    min_size=1,
    max_size=10,
)
# The formver segment is not caller-supplied: it comes from the form data
# via formver_label(). Drawing raw form-version values -- valid, missing,
# and malformed -- and labelling them here exercises the function that
# actually produces the segment, rather than asserting that an
# alphanumeric string matches an alphanumeric pattern.
raw_formver_strategy = st.one_of(
    st.integers(min_value=1, max_value=99).map(str),
    st.tuples(
        st.integers(min_value=1, max_value=99), st.integers(min_value=0, max_value=99)
    ).map(lambda pair: f"{pair[0]}.{pair[1]}"),
    st.just(""),
    st.none(),
    st.text(alphabet="abc-_. /", min_size=1, max_size=6),
)
run_id_strategy = st.text(
    alphabet=_ASCII_ALPHANUM,
    min_size=1,
    max_size=32,
)
source_id_strategy = st.text(
    alphabet=_ASCII_ALPHANUM,
    min_size=1,
    max_size=16,
)
date_strategy = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))


class TestOutputFilenamePattern:
    """Property tests for output filename format."""

    @given(
        study_id=study_id_strategy,
        source_id=source_id_strategy,
        module_name=module_name_strategy,
        today=date_strategy,
    )
    @settings(max_examples=100)
    def test_default_filename_pattern(
        self, study_id: str, source_id: str, module_name: str, today: date
    ):
        """Default filename matches.

        {study_id}-{source_id}-{module}-{YYYY-MM-DD}.csv.

        **Validates: Requirements 5.1**
        """
        filename = f"{study_id}-{source_id}-{module_name}-{today.isoformat()}.csv"
        assert DEFAULT_PATTERN.match(filename), (
            f"Filename {filename!r} does not match expected pattern"
        )

    @given(
        study_id=study_id_strategy,
        source_id=source_id_strategy,
        module_name=module_name_strategy,
        raw_formver=raw_formver_strategy,
        today=date_strategy,
    )
    @settings(max_examples=200)
    def test_formver_split_filename_pattern(
        self,
        study_id: str,
        source_id: str,
        module_name: str,
        raw_formver: object,
        today: date,
    ):
        """Formver split filename matches.

        {study_id}-{source_id}-{module}-{formver_label}-{YYYY-MM-DD}.csv.

        The formver segment is produced from raw form data rather than
        supplied by the caller, so no amount of config validation
        constrains it -- the label function is what must keep the name
        parseable, whatever the data holds.

        **Validates: Requirements 5.2**
        """
        filename = (
            f"{study_id}-{source_id}-{module_name}-{formver_label(raw_formver)}"
            f"-{today.isoformat()}.csv"
        )
        assert FORMVER_PATTERN.match(filename), (
            f"Filename {filename!r} does not match expected pattern"
        )


class TestRunIdStampedFilenamePattern:
    """Property tests for filenames stamped with a caller-supplied run_id.

    A well-formed run_id must leave the name parseable: exactly one
    extra '-'-delimited segment after the date, and the preceding
    segments unchanged.
    """

    @given(
        study_id=study_id_strategy,
        source_id=source_id_strategy,
        module_name=module_name_strategy,
        today=date_strategy,
        run_id=run_id_strategy,
    )
    @settings(max_examples=100)
    def test_default_filename_pattern(
        self,
        study_id: str,
        source_id: str,
        module_name: str,
        today: date,
        run_id: str,
    ):
        stamp = _output_stamp(run_date=today.isoformat(), run_id=run_id)
        filename = f"{study_id}-{source_id}-{module_name}-{stamp}.csv"

        assert RUN_ID_DEFAULT_PATTERN.match(filename), (
            f"Filename {filename!r} does not match expected pattern"
        )

    @given(
        study_id=study_id_strategy,
        source_id=source_id_strategy,
        module_name=module_name_strategy,
        raw_formver=raw_formver_strategy,
        today=date_strategy,
        run_id=run_id_strategy,
    )
    @settings(max_examples=200)
    def test_formver_split_filename_pattern(
        self,
        study_id: str,
        source_id: str,
        module_name: str,
        raw_formver: object,
        today: date,
        run_id: str,
    ):
        stamp = _output_stamp(run_date=today.isoformat(), run_id=run_id)
        filename = (
            f"{study_id}-{source_id}-{module_name}-"
            f"{formver_label(raw_formver)}-{stamp}.csv"
        )

        assert RUN_ID_FORMVER_PATTERN.match(filename), (
            f"Filename {filename!r} does not match expected pattern"
        )

    @given(today=date_strategy)
    @settings(max_examples=25)
    def test_empty_run_id_leaves_stamp_as_date(self, today: date):
        """An omitted run_id adds no segment and no trailing separator, so
        existing 4-segment names keep parsing."""
        assert _output_stamp(run_date=today.isoformat(), run_id="") == today.isoformat()
