"""Property test for get_submission_qc_summary.

**Feature: nacc-common-data-access,
  Property 1: QC summary faithfully represents FileQCModel**
**Validates: Requirements 3.1, 3.2, 3.3**
"""

from typing import Dict, Optional
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_data import get_submission_qc_summary
from nacc_common.error_models import (
    FileError,
    FileQCModel,
    GearQCModel,
    QCStatus,
    ValidationModel,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Gear names: non-empty, reasonable identifiers (alphanumeric + underscore)
gear_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,29}", fullmatch=True)

qc_status_strategy: st.SearchStrategy[Optional[QCStatus]] = st.sampled_from(
    ["PASS", "FAIL", "IN REVIEW", None]
)

file_error_strategy: st.SearchStrategy[FileError] = st.builds(
    FileError,
    error_type=st.sampled_from(["alert", "error", "warning"]),
    error_code=st.from_regex(r"[A-Z]{2,4}[0-9]{3}", fullmatch=True),
    message=st.text(min_size=1, max_size=50),
)

gear_qc_model_strategy: st.SearchStrategy[GearQCModel] = st.builds(
    GearQCModel,
    validation=st.builds(
        ValidationModel,
        data=st.lists(file_error_strategy, min_size=0, max_size=5),
        state=qc_status_strategy,
        cleared=st.just([]),
    ),
)


@st.composite
def file_qc_model_strategy(draw: st.DrawFn) -> FileQCModel:
    """Generate a FileQCModel with at least one gear."""
    gear_names = draw(st.lists(gear_name_strategy, min_size=1, max_size=5, unique=True))
    qc: Dict[str, GearQCModel] = {}
    for name in gear_names:
        qc[name] = draw(gear_qc_model_strategy)
    return FileQCModel(qc=qc)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(
    file_qc=file_qc_model_strategy(),
    identifier=st.text(min_size=1, max_size=60),
)
@settings(max_examples=100)
def test_qc_summary_faithfully_represents_file_qc_model(
    file_qc: FileQCModel,
    identifier: str,
):
    """Property 1: QC summary faithfully represents FileQCModel.

    **Feature: nacc-common-data-access,
      Property 1: QC summary faithfully represents FileQCModel**
    **Validates: Requirements 3.1, 3.2, 3.3**

    For any valid FileQCModel with at least one gear,
    get_submission_qc_summary SHALL return a dict where:
    - "identifier" equals the input identifier
    - "overall_status" equals FileQCModel.get_file_status()
    - "stages" contains an entry for every gear in the model, where each
      entry's "status" matches gear_model.get_status() and "error_count"
      equals len(gear_model.get_errors())
    """
    # Arrange — build a mock project whose _find_submission returns a
    # FileEntry that produces our generated FileQCModel.
    mock_project = MagicMock()
    mock_file_entry = MagicMock()
    mock_file_entry.reload.return_value = mock_file_entry

    with (
        patch(
            "nacc_common.error_data._find_submission",
            return_value=mock_file_entry,
        ),
        patch(
            "nacc_common.error_data.FileQCModel.create",
            return_value=file_qc,
        ),
    ):
        # Act
        result = get_submission_qc_summary(mock_project, identifier)

    # Assert — result must not be None since file_qc always has ≥1 gear
    assert result is not None, "Expected a dict, got None"

    # 3.1 — identifier matches
    assert result["identifier"] == identifier

    # 3.2 — overall_status matches get_file_status()
    assert result["overall_status"] == file_qc.get_file_status()

    # 3.3 — stages has entry for every gear with correct status & error count
    assert set(result["stages"].keys()) == set(file_qc.qc.keys()), (
        "stages keys must match gear names in the model"
    )

    for gear_name, gear_model in file_qc.qc.items():
        stage = result["stages"][gear_name]
        assert stage["status"] == gear_model.get_status(), (
            f"status mismatch for gear {gear_name}"
        )
        assert stage["error_count"] == len(gear_model.get_errors()), (
            f"error_count mismatch for gear {gear_name}"
        )
