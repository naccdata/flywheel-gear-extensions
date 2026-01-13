"""Property test for error resilience in EventAccumulator.

**Feature: form-scheduler-event-logging-refactor,
  Property 7: Error Resilience**
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from form_scheduler_app.event_accumulator import EventAccumulator
from hypothesis import given
from hypothesis import strategies as st


class TestErrorResilience:
    """Test that EventAccumulator handles errors gracefully without failing
    pipeline processing."""

    @given(
        file_name=st.text(min_size=1, max_size=50),
        has_info=st.booleans(),
        has_forms=st.booleans(),
        has_json=st.booleans(),
        has_module=st.booleans(),
    )
    def test_missing_qc_status_log_files_handled_gracefully(
        self, file_name, has_info, has_forms, has_json, has_module
    ):
        """Test that missing QC status log files are handled gracefully.

              **Feature: form-scheduler-event-logging-refactor,
        Property 7: Error Resilience**
              **Validates: Requirements 5.1**
        """
        # Create mock event logger
        mock_event_capture = Mock()
        accumulator = EventAccumulator(mock_event_capture)

        # Create mock JSON file with varying levels of metadata
        mock_json_file = Mock(spec=FileEntry)
        mock_json_file.name = file_name

        if has_info:
            info = {}
            if has_forms:
                forms = {}
                if has_json:
                    json_data = {}
                    if has_module:
                        json_data["module"] = "UDS"
                    forms["json"] = json_data
                info["forms"] = forms
            mock_json_file.info = info
        else:
            mock_json_file.info = None

        # Create mock project that will fail to find QC status log
        mock_project = Mock(spec=ProjectAdaptor)
        mock_project.get_file.side_effect = Exception("File not found")

        # This should not raise an exception - errors should be handled gracefully
        try:
            accumulator.capture_events(mock_json_file, mock_project)
            # If we get here, the error was handled gracefully
            assert True
        except Exception as e:
            pytest.fail(
                f"EventAccumulator should handle missing QC status logs "
                f"gracefully, but raised: {e}"
            )

        # Event logger should not be called when QC status log is missing
        mock_event_capture.capture_event.assert_not_called()

    @given(
        qc_content=st.one_of(
            st.none(),
            st.text(),
            st.binary(),
            st.just("invalid json"),
            st.just("{}"),  # Empty JSON
            st.just('{"invalid": "structure"}'),  # Invalid structure
        )
    )
    def test_invalid_visit_metadata_extraction_handled_gracefully(self, qc_content):
        """Test that invalid visit metadata extraction is handled gracefully.

              **Feature: form-scheduler-event-logging-refactor,
        Property 7: Error Resilience**
              **Validates: Requirements 5.2**
        """
        # Create mock event logger
        mock_event_capture = Mock()
        accumulator = EventAccumulator(mock_event_capture)

        # Create mock JSON file with valid metadata
        mock_json_file = Mock(spec=FileEntry)
        mock_json_file.name = "test.json"
        mock_json_file.info = {
            "forms": {
                "json": {
                    "module": "UDS",
                    "ptid": "110001",
                    "visitdate": "2024-01-15",
                }
            }
        }

        # Create mock QC status file with invalid content
        mock_qc_file = Mock(spec=FileEntry)
        mock_qc_file.name = "qc_status.json"
        mock_qc_file.info = None  # No custom info
        mock_qc_file.read.return_value = qc_content
        mock_qc_file.modified = datetime.now()

        # Create mock project
        mock_project = Mock(spec=ProjectAdaptor)
        mock_project.get_file.return_value = mock_qc_file

        # This should not raise an exception - errors should be handled gracefully
        try:
            accumulator.capture_events(mock_json_file, mock_project)
            # If we get here, the error was handled gracefully
            assert True
        except Exception as e:
            pytest.fail(
                f"EventAccumulator should handle invalid metadata "
                f"gracefully, but raised: {e}"
            )

        # Event logger should not be called when metadata extraction fails
        mock_event_capture.capture_event.assert_not_called()

    def test_s3_event_logging_failures_handled_gracefully(self):
        """Test that S3 event logging failures are handled gracefully.

              **Feature: form-scheduler-event-logging-refactor,
        Property 7: Error Resilience**
              **Validates: Requirements 5.3**
        """
        # Create mock event logger that fails
        mock_event_capture = Mock()
        mock_event_capture.capture_event.side_effect = Exception("S3 connection failed")

        accumulator = EventAccumulator(mock_event_capture)

        # Create valid mock JSON file
        mock_json_file = Mock(spec=FileEntry)
        mock_json_file.name = "test.json"
        mock_json_file.info = {
            "forms": {
                "json": {
                    "module": "UDS",
                    "ptid": "110001",
                    "visitnum": "01",
                    "visitdate": "2024-01-15",
                }
            }
        }

        # Create valid mock QC status file with PASS status
        mock_qc_file = Mock(spec=FileEntry)
        mock_qc_file.name = "qc_status.json"
        mock_qc_file.info = {
            "qc": {"form-qc-checker": {"validation": {"state": "PASS", "data": []}}},
            "visit": {
                "ptid": "110001",
                "visitnum": "01",
                "date": "2024-01-15",
                "module": "UDS",
                "packet": "I",
            },
        }
        mock_qc_file.modified = datetime.now()

        # Create mock project with valid label
        mock_project = Mock(spec=ProjectAdaptor)
        mock_project.get_file.return_value = mock_qc_file
        mock_project.label = "ingest-form-test"
        mock_project.group = "test_center"
        mock_project.get_pipeline_adcid.return_value = "123"

        # This should not raise an exception - S3 failures should be handled gracefully
        try:
            accumulator.capture_events(mock_json_file, mock_project)
            # If we get here, the S3 error was handled gracefully
            assert True
        except Exception as e:
            pytest.fail(
                f"EventAccumulator should handle S3 failures gracefully, "
                f"but raised: {e}"
            )

        # Event logger should have been called (even though it failed)
        mock_event_capture.capture_event.assert_called_once()

    @given(
        json_file_none=st.booleans(),
        project_none=st.booleans(),
    )
    def test_warnings_logged_but_processing_continues(
        self, json_file_none, project_none
    ):
        """Test that warnings are logged but processing continues.

              **Feature: form-scheduler-event-logging-refactor,
        Property 7: Error Resilience**
              **Validates: Requirements 5.4**
        """
        # Create mock event logger
        mock_event_capture = Mock()
        accumulator = EventAccumulator(mock_event_capture)

        # Create inputs based on test parameters
        json_file = None if json_file_none else Mock(spec=FileEntry)
        if json_file:
            json_file.name = "test.json"

        project = None if project_none else Mock(spec=ProjectAdaptor)

        # Capture log messages
        with patch("form_scheduler_app.event_accumulator.log") as mock_log:
            # This should not raise an exception
            try:
                accumulator.capture_events(json_file, project)  # type: ignore[arg-type]
                # If we get here, the error was handled gracefully
                assert True
            except Exception as e:
                pytest.fail(
                    f"EventAccumulator should handle invalid inputs "
                    f"gracefully, but raised: {e}"
                )

            # Should have logged warnings for invalid inputs
            if json_file_none or project_none:
                mock_log.warning.assert_called()

        # Event logger should not be called with invalid inputs
        mock_event_capture.capture_event.assert_not_called()

    def test_validation_errors_handled_gracefully(self):
        """Test that Pydantic validation errors are handled gracefully."""
        # Create mock event logger
        mock_event_capture = Mock()
        accumulator = EventAccumulator(mock_event_capture)

        # Create mock JSON file with invalid metadata that will cause validation errors
        mock_json_file = Mock(spec=FileEntry)
        mock_json_file.name = "test.json"
        mock_json_file.info = {
            "forms": {
                "json": {
                    "module": "UDS",
                    "ptid": None,  # Invalid - should be string
                    "visitdate": "invalid-date",  # Invalid date format
                }
            }
        }

        # Create mock QC status file
        mock_qc_file = Mock(spec=FileEntry)
        mock_qc_file.name = "qc_status.json"
        mock_qc_file.info = {
            "visit": {
                "ptid": 12345,  # Invalid - should be string
                "date": "not-a-date",  # Invalid date
                "module": None,  # Invalid - should be string
            }
        }
        mock_qc_file.read.return_value = '{"file_status": "PASS"}'
        mock_qc_file.modified = datetime.now()

        # Create mock project
        mock_project = Mock(spec=ProjectAdaptor)
        mock_project.get_file.return_value = mock_qc_file

        # This should not raise an exception - validation errors should be
        # handled gracefully
        try:
            accumulator.capture_events(mock_json_file, mock_project)
            # If we get here, the validation errors were handled gracefully
            assert True
        except Exception as e:
            pytest.fail(
                f"EventAccumulator should handle validation errors "
                f"gracefully, but raised: {e}"
            )

        # Event logger should not be called when validation fails
        mock_event_capture.capture_event.assert_not_called()
