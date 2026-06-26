"""Property test for output filename pattern.

Feature: center-form-export, Property 4: Output filename conforms to naming pattern
Validates: Requirements 5.1, 5.2
"""

import re
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

# Regex patterns for valid output filenames
DEFAULT_PATTERN = re.compile(r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-\d{4}-\d{2}-\d{2}\.csv$")
FORMVER_PATTERN = re.compile(
    r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-\d{4}-\d{2}-\d{2}\.csv$"
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
formver_label_strategy = st.text(
    alphabet=_ASCII_ALPHANUM,
    min_size=1,
    max_size=10,
)
date_strategy = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))


class TestOutputFilenamePattern:
    """Property tests for output filename format."""

    @given(
        study_id=study_id_strategy,
        module_name=module_name_strategy,
        today=date_strategy,
    )
    @settings(max_examples=100)
    def test_default_filename_pattern(
        self, study_id: str, module_name: str, today: date
    ):
        """Default filename matches {study_id}-{module}-{YYYY-MM-DD}.csv.

        **Validates: Requirements 5.1**
        """
        filename = f"{study_id}-{module_name}-{today.isoformat()}.csv"
        assert DEFAULT_PATTERN.match(filename), (
            f"Filename {filename!r} does not match expected pattern"
        )

    @given(
        study_id=study_id_strategy,
        module_name=module_name_strategy,
        formver_label=formver_label_strategy,
        today=date_strategy,
    )
    @settings(max_examples=100)
    def test_formver_split_filename_pattern(
        self,
        study_id: str,
        module_name: str,
        formver_label: str,
        today: date,
    ):
        """Formver split filename matches.

        {study_id}-{module}-{formver_label}-{YYYY-MM-DD}.csv.

        **Validates: Requirements 5.2**
        """
        filename = f"{study_id}-{module_name}-{formver_label}-{today.isoformat()}.csv"
        assert FORMVER_PATTERN.match(filename), (
            f"Filename {filename!r} does not match expected pattern"
        )
