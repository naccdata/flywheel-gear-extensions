import re

import pytest
from nacc_common.qc_report import QC_FILENAME_PATTERN


@pytest.fixture
def qc_matcher() -> re.Pattern[str]:
    """Compiled QC filename pattern matcher."""
    return re.compile(QC_FILENAME_PATTERN)
