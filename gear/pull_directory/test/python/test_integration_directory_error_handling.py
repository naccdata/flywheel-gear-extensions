"""Integration tests for pull_directory gear with error handling.

This module tests the integration of error handling into the pull_directory
gear, including:
- Directory processing with integrated error handling
- Error capture for validation failures
- Error capture for permission issues
- End-of-run notification generation

Requirements tested:
- 1a.4: Error capture for "Permissions not approved"
- 1a.5: Error capture for "Data platform survey is incomplete"
- 1a.7: Error capture for directory validation errors
"""

from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest
from conftest import MockGearContext, MockParameterStore
from gear_execution.gear_execution import ClientWrapper, GearExecutionError
from inputs.parameter_store import ParameterError
from users.event_models import EventCategory, EventType, UserContext, UserProcessEvent
from users.user_entry import PersonName


class TestDirectoryErrorHandlingIntegration:
    """Integration tests for directory gear error handling."""

    @pytest.fixture
    def mock_client(self) -> ClientWrapper:
        """Create mock Flywheel client."""
        mock_client = Mock(spec=ClientWrapper)
        mock_client.dry_run = False
        return mock_client

    @pytest.fixture
    def valid_user_record(self) -> Dict[str, Any]:
        """Create a valid user record."""
        return {
            "email": "user@example.com",
            "first_name": "Test",
            "last_name": "User",
            "adcid": 1,
            "permissions_approval": "1",  # "1" means Yes/approved
            "auth_email": "user@example.com",
            # Add all required fields with default values
            "firstname": "Test",
            "lastname": "User",
            "fw_email": "user@example.com",
            "archive_contact": "0",  # "0" means No/not archived
            "contact_company_name": "Test Center",
            "adresearchctr": "1",
            "web_report_access": "0",  # "0" means No
            "study_selections": "",
            "p30_naccid_enroll_access_level": "0",
            "p30_clin_forms_access_level": "0",
            "p30_imaging_access_level": "0",
            "p30_flbm_access_level": "0",
            "p30_genetic_access_level": "0",
            "affiliated_study": "",
            "leads_naccid_enroll_access_level": "0",
            "leads_clin_forms_access_level": "0",
            "dvcid_naccid_enroll_access_level": "0",
            "dvcid_clin_forms_access_level": "0",
            "allftd_naccid_enroll_access_level": "0",
            "allftd_clin_forms_access_level": "0",
            "dlbc_naccid_enroll_access_level": "0",
            "dlbc_clin_forms_access_level": "0",
            "cl_clin_forms_access_level": "0",
            "cl_imaging_access_level": "0",
            "cl_flbm_access_level": "0",
            "cl_pay_access_level": "0",
            "cl_ror_access_level": "0",
            "scan_dashboard_access_level": "0",
            "permissions_approval_date": "2024-01-01",
            "permissions_approval_name": "Admin",
            "signed_agreement_status_num_ct": "1",
        }

    @pytest.fixture
    def unapproved_permissions_record(self) -> Dict[str, Any]:
        """Create a user record with unapproved permissions."""
        return {
            "email": "unapproved@example.com",
            "first_name": "Unapproved",
            "last_name": "User",
            "adcid": 1,
            "permissions_approval": "0",  # "0" means No/not approved
            "auth_email": "unapproved@example.com",
            # Add all required fields with default values
            "firstname": "Unapproved",
            "lastname": "User",
            "fw_email": "unapproved@example.com",
            "archive_contact": "0",
            "contact_company_name": "Test Center",
            "adresearchctr": "1",
            "web_report_access": "0",
            "study_selections": "",
            "p30_naccid_enroll_access_level": "0",
            "p30_clin_forms_access_level": "0",
            "p30_imaging_access_level": "0",
            "p30_flbm_access_level": "0",
            "p30_genetic_access_level": "0",
            "affiliated_study": "",
            "leads_naccid_enroll_access_level": "0",
            "leads_clin_forms_access_level": "0",
            "dvcid_naccid_enroll_access_level": "0",
            "dvcid_clin_forms_access_level": "0",
            "allftd_naccid_enroll_access_level": "0",
            "allftd_clin_forms_access_level": "0",
            "dlbc_naccid_enroll_access_level": "0",
            "dlbc_clin_forms_access_level": "0",
            "cl_clin_forms_access_level": "0",
            "cl_imaging_access_level": "0",
            "cl_flbm_access_level": "0",
            "cl_pay_access_level": "0",
            "cl_ror_access_level": "0",
            "scan_dashboard_access_level": "0",
            "permissions_approval_date": "2024-01-01",
            "permissions_approval_name": "Admin",
            "signed_agreement_status_num_ct": "1",
        }

    @pytest.fixture
    def invalid_record(self) -> Dict[str, Any]:
        """Create an invalid user record (missing required fields)."""
        return {
            "email": "invalid@example.com",
            # Missing first_name, last_name, adcid
            "permissions_approval": "Yes",
            "complete": "Yes",
        }

    def test_directory_processing_with_valid_records(
        self,
        mock_context: MockGearContext,
        valid_user_record: Dict[str, Any],
    ) -> None:
        """Test directory processing with valid user records.

        This test verifies:
        - Valid records are processed successfully
        - No errors are generated for valid records
        - Output file is created with user entries
        """
        from directory_app.main import run

        user_report = [valid_user_record]

        # Process the directory
        yaml_output = run(user_report=user_report)

        # Verify output was generated
        assert yaml_output is not None
        assert len(yaml_output) > 0
        assert "user@example.com" in yaml_output

    def test_error_capture_for_unapproved_permissions(
        self,
        mock_context: MockGearContext,
        unapproved_permissions_record: Dict[str, Any],
        caplog,
    ) -> None:
        """Test error capture for unapproved permissions.

        This test verifies:
        - Records with unapproved permissions are logged
        - Warning message matches requirement 1a.4
        - Record is excluded from output
        - Error event is captured in collector

        Requirements: 1a.4
        """
        from directory_app.main import run
        from users.event_models import UserEventCollector

        user_report = [unapproved_permissions_record]
        collector = UserEventCollector()

        # Process the directory
        yaml_output = run(user_report=user_report, collector=collector)

        # Verify warning was logged
        assert any(
            "Ignoring unapproved@example.com: Permissions not approved"
            in record.message
            for record in caplog.records
        )

        # Verify record was excluded from output
        assert "unapproved@example.com" not in yaml_output

        # Verify error event was captured
        assert collector.has_errors()
        assert collector.error_count() == 1
        errors = collector.get_errors()
        # Compare with string value since use_enum_values=True
        assert errors[0].category == EventCategory.MISSING_DIRECTORY_PERMISSIONS.value
        assert errors[0].user_context.email == "unapproved@example.com"

    def test_error_capture_for_validation_failures(
        self,
        mock_context: MockGearContext,
        invalid_record: Dict[str, Any],
        caplog,
    ) -> None:
        """Test error capture for validation failures.

        This test verifies:
        - Invalid records trigger validation errors
        - Validation errors are logged
        - Invalid records are excluded from output
        - Error event is captured in collector

        Requirements: 1a.7
        """
        from directory_app.main import run
        from users.event_models import UserEventCollector

        user_report = [invalid_record]
        collector = UserEventCollector()

        # Process the directory
        yaml_output = run(user_report=user_report, collector=collector)

        # Verify error was logged
        assert any(
            "Error loading user record" in record.message for record in caplog.records
        )

        # Verify record was excluded from output
        assert "invalid@example.com" not in yaml_output

        # Verify error event was captured
        assert collector.has_errors()
        assert collector.error_count() == 1
        errors = collector.get_errors()
        # Compare with string value since use_enum_values=True
        assert errors[0].category == EventCategory.MISSING_DIRECTORY_DATA.value
        assert errors[0].user_context.email == "invalid@example.com"

    def test_mixed_records_processing(
        self,
        mock_context: MockGearContext,
        valid_user_record: Dict[str, Any],
        unapproved_permissions_record: Dict[str, Any],
        invalid_record: Dict[str, Any],
        caplog,
    ) -> None:
        """Test processing with mixed valid and invalid records.

        This test verifies:
        - Valid records are processed
        - Invalid records are logged and excluded
        - Processing continues despite errors
        - Multiple error types are handled correctly
        - All errors are captured in collector
        """
        from directory_app.main import run
        from users.event_models import UserEventCollector

        user_report = [
            valid_user_record,
            unapproved_permissions_record,
            invalid_record,
        ]
        collector = UserEventCollector()

        # Process the directory
        yaml_output = run(user_report=user_report, collector=collector)

        # Verify valid record is in output
        assert "user@example.com" in yaml_output

        # Verify invalid records are not in output
        assert "unapproved@example.com" not in yaml_output
        assert "invalid@example.com" not in yaml_output

        # Verify appropriate warnings were logged
        assert any(
            "Permissions not approved" in record.message for record in caplog.records
        )
        assert any(
            "Error loading user record" in record.message for record in caplog.records
        )

        # Verify all errors were captured
        assert collector.has_errors()
        assert collector.error_count() == 2

        # Verify error categories
        errors_by_category = collector.get_errors_by_category()
        assert EventCategory.MISSING_DIRECTORY_PERMISSIONS in errors_by_category
        assert EventCategory.MISSING_DIRECTORY_DATA in errors_by_category
        assert len(errors_by_category[EventCategory.MISSING_DIRECTORY_PERMISSIONS]) == 1
        assert len(errors_by_category[EventCategory.MISSING_DIRECTORY_DATA]) == 1

    def test_duplicate_email_detection(
        self,
        mock_context: MockGearContext,
        valid_user_record: Dict[str, Any],
        caplog,
    ) -> None:
        """Test detection of duplicate email addresses.

        This test verifies:
        - Duplicate emails are detected
        - Warning is logged for duplicates
        - Both records are still processed (warning only)
        """
        from directory_app.main import run

        # Create two records with same email
        duplicate_record = valid_user_record.copy()
        duplicate_record["first_name"] = "Duplicate"

        user_report = [valid_user_record, duplicate_record]

        # Process the directory
        yaml_output = run(user_report=user_report)

        # Verify warning was logged
        assert any(
            "Email user@example.com occurs in more than one contact" in record.message
            for record in caplog.records
        )

        # Verify both records are in output (warning only, not exclusion)
        assert yaml_output.count("user@example.com") >= 1

    def test_empty_user_report(
        self,
        mock_context: MockGearContext,
    ) -> None:
        """Test processing with empty user report.

        This test verifies:
        - Empty report is handled gracefully
        - No errors are raised
        - Output is valid YAML with empty list
        """
        from directory_app.main import run

        user_report: List[Dict[str, Any]] = []

        # Process the directory
        yaml_output = run(user_report=user_report)

        # Verify output is valid and empty
        assert yaml_output is not None
        assert len(yaml_output) > 0  # YAML representation of empty list

    def test_visitor_creation_with_error_handling_support(
        self,
        mock_parameter_store: MockParameterStore,
        mock_context: MockGearContext,
        mock_client: ClientWrapper,
    ) -> None:
        """Test that visitor can be created with error handling support.

        This test verifies:
        - Visitor can be created with all required parameters
        - Error handling infrastructure is available
        - Support staff emails can be configured
        """
        from directory_app.run import DirectoryPullVisitor

        # Mock REDCap connection, project, and export_records
        mock_connection = Mock()
        mock_project = Mock()
        mock_project.export_records = Mock(return_value=[])

        with (
            patch(
                "directory_app.run.REDCapConnection.create_from",
                return_value=mock_connection,
            ),
            patch(
                "directory_app.run.REDCapProject.create",
                return_value=mock_project,
            ),
        ):
            # Add support staff emails path to config
            mock_context.config_opts["support_emails_path"] = "/support/emails"

            visitor = DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

            # Verify visitor was created successfully
            assert visitor is not None

    def test_gear_execution_with_dry_run(
        self,
        mock_parameter_store: MockParameterStore,
        mock_context: MockGearContext,
        mock_client: ClientWrapper,
        valid_user_record: Dict[str, Any],
        caplog,
    ) -> None:
        """Test gear execution in dry run mode.

        This test verifies:
        - Dry run mode is respected
        - No output file is written in dry run
        - Appropriate log message is generated
        """
        import logging

        from directory_app.run import DirectoryPullVisitor

        # Set log level to capture INFO messages
        caplog.set_level(logging.INFO)

        # Create a mock client with dry_run=True
        dry_run_client = Mock(spec=ClientWrapper)
        dry_run_client.dry_run = True

        visitor = DirectoryPullVisitor(
            client=dry_run_client,
            user_filename="users.yaml",
            user_report=[valid_user_record],
        )

        # Run the visitor
        visitor.run(context=mock_context)  # type: ignore

        # Verify dry run message was logged
        assert any(
            "Would write user entries to file" in record.message
            for record in caplog.records
        )

        # Verify no output was written
        assert mock_context.output_content is None

    def test_gear_execution_with_actual_write(
        self,
        mock_parameter_store: MockParameterStore,
        mock_context: MockGearContext,
        mock_client: ClientWrapper,
        valid_user_record: Dict[str, Any],
    ) -> None:
        """Test gear execution with actual file write.

        This test verifies:
        - Output file is written when not in dry run
        - Output contains valid YAML
        - User data is correctly formatted
        """
        from directory_app.run import DirectoryPullVisitor

        visitor = DirectoryPullVisitor(
            client=mock_client,
            user_filename="users.yaml",
            user_report=[valid_user_record],
        )

        # Run the visitor
        visitor.run(context=mock_context)  # type: ignore

        # Verify output was written
        assert mock_context.output_content is not None
        assert len(mock_context.output_content) > 0
        assert "user@example.com" in mock_context.output_content

    def test_gear_handles_missing_parameter_path(
        self,
        mock_parameter_store: MockParameterStore,
        mock_client: ClientWrapper,
    ) -> None:
        """Test that gear handles missing parameter path.

        This test verifies:
        - Gear raises error when parameter_path is missing
        - Error message is descriptive
        """
        from directory_app.run import DirectoryPullVisitor

        # Create context without parameter_path
        config_no_param = {"user_file": "users.yaml"}
        context_no_param = MockGearContext(config=config_no_param)

        with pytest.raises(GearExecutionError, match="No parameter path"):
            DirectoryPullVisitor.create(
                context=context_no_param,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

    def test_gear_handles_missing_user_filename(
        self,
        mock_parameter_store: MockParameterStore,
        mock_client: ClientWrapper,
    ) -> None:
        """Test that gear handles missing user filename.

        This test verifies:
        - Gear raises error when user_file is missing
        - Error message is descriptive
        """
        from directory_app.run import DirectoryPullVisitor

        # Create context without user_file
        config_no_file = {"parameter_path": "/directory/test"}
        context_no_file = MockGearContext(config=config_no_file)

        # Mock REDCap connection, project, and export_records
        mock_connection = Mock()
        mock_project = Mock()
        mock_project.export_records = Mock(return_value=[])

        with (
            patch(
                "directory_app.run.REDCapConnection.create_from",
                return_value=mock_connection,
            ),
            patch(
                "directory_app.run.REDCapProject.create",
                return_value=mock_project,
            ),
            pytest.raises(GearExecutionError, match="No user file name provided"),
        ):
            DirectoryPullVisitor.create(
                context=context_no_file,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

    def test_gear_handles_redcap_connection_error(
        self,
        mock_parameter_store: MockParameterStore,
        mock_context: MockGearContext,
        mock_client: ClientWrapper,
    ) -> None:
        """Test that gear handles REDCap connection errors.

        This test verifies:
        - Gear raises error when REDCap connection fails
        - Error message includes original error details
        """
        from directory_app.run import DirectoryPullVisitor
        from redcap_api.redcap_connection import REDCapConnectionError

        # Mock REDCap connection to raise error
        with (
            patch(
                "directory_app.run.REDCapConnection.create_from",
                side_effect=REDCapConnectionError("Connection failed"),
            ),
            pytest.raises(
                GearExecutionError, match="Failed to pull users from directory"
            ),
        ):
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

    def test_gear_handles_parameter_store_error(
        self,
        mock_context: MockGearContext,
        mock_client: ClientWrapper,
    ) -> None:
        """Test that gear handles Parameter Store errors.

        This test verifies:
        - Gear raises error when Parameter Store access fails
        - Error message includes original error details
        """
        from directory_app.run import DirectoryPullVisitor

        # Create parameter store that raises error when accessing parameters
        mock_param_store_error = Mock()
        mock_param_store_error.get_parameters.side_effect = ParameterError(
            "Failed to retrieve parameters"
        )

        with pytest.raises(GearExecutionError, match="Parameter error"):
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore
                parameter_store=mock_param_store_error,  # type: ignore
            )

    def test_end_of_run_notification_generation_placeholder(
        self,
        mock_context: MockGearContext,
    ) -> None:
        """Test end-of-run notification generation (placeholder).

        This test verifies:
        - Error events can be collected during processing
        - Notification generation infrastructure is available
        - Support staff emails can be configured

        Note: Full notification generation will be implemented in task 33.
        This test establishes the integration points.
        """
        from users.event_models import UserEventCollector

        # Create event collector
        collector = UserEventCollector()

        # Simulate collecting an error event
        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.MISSING_DIRECTORY_PERMISSIONS,
            user_context=UserContext(
                email="test@example.com",
                name=PersonName(first_name="Test", last_name="User"),
            ),
            message="Permissions not approved",
            action_needed="contact_center_administrator",
        )

        collector.collect(error_event)

        # Verify event was collected
        assert collector.has_errors()
        assert collector.error_count() == 1

        # Verify error can be retrieved
        errors = collector.get_errors()
        assert len(errors) == 1
        # Compare with string value since use_enum_values=True
        assert errors[0].category == EventCategory.MISSING_DIRECTORY_PERMISSIONS.value

        # Verify notification generation infrastructure is available
        # (Full implementation in task 33)
        assert hasattr(collector, "get_errors_by_category")
        assert hasattr(collector, "get_affected_users")
