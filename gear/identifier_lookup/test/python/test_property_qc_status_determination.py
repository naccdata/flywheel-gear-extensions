"""Property test for QC status determination.

**Feature: identifier-lookup-refactoring,
  Property 2: QC Status Determination**
**Validates: Requirements 2.2, 2.3**
"""

from typing import Dict, List
from unittest.mock import Mock

from error_logging.qc_status_log_creator import QCStatusLogManager
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


@st.composite
def visit_data_strategy(draw):
    """Generate random visit data for testing.

    Note: PTIDs are generated with uppercase letters and digits to avoid
    issues with clean_ptid() which strips leading zeros. PTIDs like "0" or "00"
    would become empty strings after cleaning.
    """
    ptid = draw(
        st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
        )
    )
    date = draw(st.dates().map(lambda d: d.strftime("%Y-%m-%d")))
    visitnum = draw(st.integers(min_value=1, max_value=99).map(str))
    adcid = draw(st.integers(min_value=1, max_value=999))

    return {
        "ptid": ptid,
        "visitdate": date,
        "visitnum": visitnum,
        "adcid": adcid,
        "packet": "I",
        "formver": "4.0",
    }


@given(visit_data=visit_data_strategy())
@settings(max_examples=100)
def test_qc_status_pass_for_successful_processing(visit_data: Dict[str, str]):
    """Property test: QC visitor creates PASS status for successful processing.

      **Feature: identifier-lookup-refactoring,
    Property 2: QC Status Determination**
      **Validates: Requirements 2.2**

      For any visit processing result where no errors are present, the QC visitor
      should create logs with PASS status.
    """
    # Arrange - Create QC visitor with empty error writer (no errors)
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True
    misc_errors: List[FileError] = []

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="test",
    )

    # Act - Process row with no errors in error writer
    result = qc_visitor.visit_row(visit_data, line_num=1)

    # Assert - Verify PASS status was used
    assert result is True, "visit_row should return True for successful processing"
    assert mock_qc_creator.update_qc_log.called, "QC log should be created"

    call_kwargs = mock_qc_creator.update_qc_log.call_args[1]
    assert call_kwargs["status"] == "PASS", (
        "QC status should be PASS when no errors are present"
    )
    assert len(call_kwargs["errors"].root) == 0, (
        "Error list should be empty for PASS status"
    )


@given(
    visit_data=visit_data_strategy(), error_message=st.text(min_size=1, max_size=100)
)
@settings(max_examples=100)
def test_qc_status_fail_for_failed_processing(
    visit_data: Dict[str, str], error_message: str
):
    """Property test: QC visitor creates FAIL status with error details for
    failures.

      **Feature: identifier-lookup-refactoring,
    Property 2: QC Status Determination**
      **Validates: Requirements 2.3**

      For any visit processing result where errors are present, the QC visitor
      should create logs with FAIL status and include error details.
    """
    # Arrange - Create QC visitor with errors in error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    # Add an error to simulate identifier lookup failure
    test_error = FileError(
        error_type="error",
        error_code="identifier-error",
        location={"line": 1, "column_name": "ptid"},
        value=visit_data.get("ptid", ""),
        message=error_message,
    )
    shared_error_writer.write(test_error)

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="test",
    )

    # Act - Process row with errors in error writer
    result = qc_visitor.visit_row(visit_data, line_num=1)

    # Assert - Verify FAIL status was used with error details
    assert result is True, (
        "visit_row should return True even with errors (graceful handling)"
    )
    assert mock_qc_creator.update_qc_log.called, (
        "QC log should be created even for failures"
    )

    call_kwargs = mock_qc_creator.update_qc_log.call_args[1]
    assert call_kwargs["status"] == "FAIL", (
        "QC status should be FAIL when errors are present"
    )
    assert len(call_kwargs["errors"].root) > 0, (
        "Error details should be included in FAIL status"
    )
    # Verify the error has the expected structure
    first_error = call_kwargs["errors"].root[0]
    assert first_error.error_code == "identifier-error", (
        "Error should have correct error code"
    )


def test_qc_status_determination_boundary_case_empty_visit():
    """Test QC status determination with incomplete visit data.

      **Feature: identifier-lookup-refactoring,
    Property 2: QC Status Determination**
      **Validates: Requirements 2.2, 2.3**

      When visit data is incomplete (missing required fields), the QC visitor
      should skip processing gracefully without creating a QC log.
    """
    # Arrange - Create QC visitor
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="test",
    )

    # Act - Process row with incomplete visit data (missing ptid)
    incomplete_visit = {
        "visitdate": "2024-01-01",
        "visitnum": "1",
        "adcid": 1,
    }
    result = qc_visitor.visit_row(incomplete_visit, line_num=1)

    # Assert - Verify no QC log was created for incomplete visit
    assert result is True, "visit_row should return True (graceful handling)"
    assert not mock_qc_creator.update_qc_log.called, (
        "QC log should not be created for incomplete visit data"
    )
