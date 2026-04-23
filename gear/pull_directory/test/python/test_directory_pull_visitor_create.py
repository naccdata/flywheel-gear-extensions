"""Unit tests for refactored DirectoryPullVisitor.create().

Tests that the create() method uses REDCapConnection (not REDCapReportConnection),
REDCapProject, and export_records with the derived field list, and that errors
are properly wrapped in GearExecutionError. Also tests date range passing
based on preceding_hours configuration.

Requirements: 1.1, 1.3, 2.2, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.4, 5.1
"""

import logging
from contextlib import contextmanager
from typing import Optional
from unittest.mock import Mock, patch

import pytest
from conftest import MockGearContext, MockParameterStore
from directory_app.run import DirectoryPullVisitor
from gear_execution.gear_execution import GearExecutionError
from inputs.parameter_store import ParameterError
from redcap_api.redcap_connection import REDCapConnectionError
from redcap_api.redcap_parameter_store import REDCapParameters
from users.nacc_directory import get_directory_field_names


@contextmanager
def patched_redcap(
    *,
    connection: Optional[Mock] = None,
    project: Optional[Mock] = None,
    export_return: Optional[list] = None,
    export_side_effect: Optional[Exception] = None,
    connection_side_effect: Optional[Exception] = None,
):
    """Context manager that patches REDCapConnection, REDCapProject, and
    ContextClient with configurable mocks.

    Args:
        connection: Mock connection object (default: new Mock).
        project: Mock project object (default: new Mock with export_records).
        export_return: Return value for export_records (default: []).
        export_side_effect: Side effect for export_records.
        connection_side_effect: Side effect for REDCapConnection.create_from.
    """
    mock_connection = connection or Mock()
    mock_project = project or Mock()

    if export_side_effect:
        mock_project.export_records.side_effect = export_side_effect
    elif export_return is not None:
        mock_project.export_records.return_value = export_return
    else:
        mock_project.export_records.return_value = []

    if connection_side_effect:
        connection_patch = patch(
            "directory_app.run.REDCapConnection.create_from",
            side_effect=connection_side_effect,
        )
    else:
        connection_patch = patch(
            "directory_app.run.REDCapConnection.create_from",
            return_value=mock_connection,
        )

    with (
        connection_patch as mock_create_from,
        patch(
            "directory_app.run.REDCapProject.create",
            return_value=mock_project,
        ) as mock_project_create,
        patch("directory_app.run.ContextClient.create", return_value=Mock()),
    ):
        yield {
            "connection": mock_connection,
            "project": mock_project,
            "create_from": mock_create_from,
            "project_create": mock_project_create,
        }


class TestDirectoryPullVisitorCreate:
    """Tests for DirectoryPullVisitor.create()."""

    def test_uses_redcap_connection_not_report_connection(
        self,
        mock_context: MockGearContext,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """Verify REDCapConnection.create_from is called.

        Requirements: 3.1
        """
        with patched_redcap() as mocks:
            visitor = DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            assert visitor is not None
            mocks["create_from"].assert_called_once()

    def test_creates_redcap_project_from_connection(
        self,
        mock_context: MockGearContext,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """Verify REDCapProject.create is called with the connection.

        Requirements: 3.2
        """
        mock_connection = Mock()

        with patched_redcap(connection=mock_connection) as mocks:
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mocks["project_create"].assert_called_once_with(mock_connection)

    def test_export_records_called_with_directory_field_names(
        self,
        mock_context: MockGearContext,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """Verify export_records is called with
        fields=get_directory_field_names().

        Requirements: 1.1, 3.3
        """
        with patched_redcap() as mocks:
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mocks["project"].export_records.assert_called_once_with(
                fields=get_directory_field_names()
            )

    def test_filter_approved_records_applied(
        self,
        mock_context: MockGearContext,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """Verify filter_approved_records() is applied to exported records.

        Requirements: 1.1, 3.4
        """
        raw_records = [
            {"email": "a@test.com", "permissions_approval": "1"},
            {"email": "b@test.com", "permissions_approval": "0"},
            {"email": "c@test.com", "permissions_approval": "1"},
        ]

        with (
            patched_redcap(export_return=raw_records),
            patch(
                "directory_app.run.filter_approved_records",
                return_value=[raw_records[0], raw_records[2]],
            ) as mock_filter,
        ):
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mock_filter.assert_called_once_with(raw_records)

    def test_redcap_connection_error_wrapped_in_gear_execution_error(
        self,
        mock_context: MockGearContext,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """REDCapConnectionError from export_records is wrapped in
        GearExecutionError.

        Requirements: 1.3, 5.1
        """
        with (
            patched_redcap(
                export_side_effect=REDCapConnectionError("Connection failed"),
            ),
            pytest.raises(
                GearExecutionError, match="Failed to pull users from directory"
            ),
        ):
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

    def test_parameter_error_wrapped_in_gear_execution_error(self) -> None:
        """ParameterError from get_parameters is wrapped in GearExecutionError.

        Requirements: 3.4, 5.1
        """
        context = MockGearContext()
        param_store = Mock()
        param_store.get_parameters.side_effect = ParameterError("Missing token")

        with pytest.raises(GearExecutionError, match="Parameter error"):
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=param_store,  # type: ignore[arg-type]
            )

    def test_get_parameters_called_with_redcap_parameters_type(
        self,
        mock_context: MockGearContext,
    ) -> None:
        """Verify get_parameters is called with param_type=REDCapParameters.

        Requirements: 3.3, 3.4
        """
        param_store = Mock()
        param_store.get_parameters.return_value = {
            "url": "https://redcap.test",
            "token": "test_token",
        }
        param_store.get_notification_parameters.return_value = {
            "sender": "noreply@example.com",
            "support_emails": "support@example.com",
        }

        with patched_redcap():
            DirectoryPullVisitor.create(
                context=mock_context,  # type: ignore[arg-type]
                parameter_store=param_store,  # type: ignore[arg-type]
            )

            param_store.get_parameters.assert_called_once_with(
                param_type=REDCapParameters,
                parameter_path="/directory/test",
            )


class TestDirectoryPullVisitorCreateDateRange:
    """Tests for date range passing in DirectoryPullVisitor.create().

    Validates: Requirements 2.2, 3.3, 3.4, 4.1, 4.2, 4.4
    """

    def test_export_records_called_with_date_range_when_preceding_hours_positive(
        self,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """When preceding_hours > 0, export_records receives date_range_begin
        and date_range_end kwargs.

        Validates: Requirements 3.3
        """
        context = MockGearContext(
            config={
                "parameter_path": "/directory/test",
                "user_file": "users.yaml",
                "notifications_path": "/prod/notifications",
                "preceding_hours": 6,
            }
        )

        with patched_redcap() as mocks:
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            call_kwargs = mocks["project"].export_records.call_args
            assert "date_range_begin" in call_kwargs.kwargs
            assert "date_range_end" in call_kwargs.kwargs
            assert call_kwargs.kwargs["fields"] == get_directory_field_names()

    def test_export_records_called_without_date_range_when_preceding_hours_zero(
        self,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """When preceding_hours == 0, export_records is called without
        date_range_begin or date_range_end kwargs.

        Validates: Requirements 3.4, 4.1
        """
        context = MockGearContext(
            config={
                "parameter_path": "/directory/test",
                "user_file": "users.yaml",
                "notifications_path": "/prod/notifications",
                "preceding_hours": 0,
            }
        )

        with patched_redcap() as mocks:
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mocks["project"].export_records.assert_called_once_with(
                fields=get_directory_field_names()
            )

    def test_filter_approved_records_called_with_preceding_hours(
        self,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """filter_approved_records is called regardless of preceding_hours
        setting.

        Validates: Requirements 4.2
        """
        raw_records = [
            {"email": "a@test.com", "permissions_approval": "1"},
            {"email": "b@test.com", "permissions_approval": "0"},
        ]

        context_with_preceding_hours = MockGearContext(
            config={
                "parameter_path": "/directory/test",
                "user_file": "users.yaml",
                "notifications_path": "/prod/notifications",
                "preceding_hours": 6,
            }
        )

        with (
            patched_redcap(export_return=raw_records),
            patch(
                "directory_app.run.filter_approved_records",
                return_value=[raw_records[0]],
            ) as mock_filter,
        ):
            DirectoryPullVisitor.create(
                context=context_with_preceding_hours,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mock_filter.assert_called_once_with(raw_records)

    def test_filter_approved_records_called_without_preceding_hours(
        self,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """filter_approved_records is called when preceding_hours is 0.

        Validates: Requirements 4.2
        """
        raw_records = [
            {"email": "a@test.com", "permissions_approval": "1"},
            {"email": "b@test.com", "permissions_approval": "0"},
        ]

        context_no_preceding_hours = MockGearContext(
            config={
                "parameter_path": "/directory/test",
                "user_file": "users.yaml",
                "notifications_path": "/prod/notifications",
                "preceding_hours": 0,
            }
        )

        with (
            patched_redcap(export_return=raw_records),
            patch(
                "directory_app.run.filter_approved_records",
                return_value=[raw_records[0]],
            ) as mock_filter,
        ):
            DirectoryPullVisitor.create(
                context=context_no_preceding_hours,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mock_filter.assert_called_once_with(raw_records)

    def test_negative_preceding_hours_raises_gear_execution_error(
        self,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """Negative preceding_hours raises GearExecutionError.

        Validates: Requirements 2.2
        """
        context = MockGearContext(
            config={
                "parameter_path": "/directory/test",
                "user_file": "users.yaml",
                "notifications_path": "/prod/notifications",
                "preceding_hours": -5,
            }
        )

        with (
            patched_redcap(),
            pytest.raises(
                GearExecutionError,
                match="Invalid preceding_hours configuration",
            ),
        ):
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

    def test_default_config_no_preceding_hours_key_behaves_as_full_pull(
        self,
        mock_parameter_store: MockParameterStore,
    ) -> None:
        """When preceding_hours is absent from config, export_records is called
        without date range kwargs (full pull behavior).

        Validates: Requirements 4.4
        """
        # Default MockGearContext has no preceding_hours key
        context = MockGearContext()

        with patched_redcap() as mocks:
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

            mocks["project"].export_records.assert_called_once_with(
                fields=get_directory_field_names()
            )


class TestDirectoryPullVisitorCreateLogging:
    """Tests for logging behavior in DirectoryPullVisitor.create().

    Validates: Requirements 6.1, 6.2
    """

    def test_logs_incremental_pull_with_preceding_hours(
        self,
        mock_parameter_store: MockParameterStore,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When preceding_hours > 0, log message includes preceding_hours value
        and computed date range.

        Validates: Requirements 6.1
        """
        context = MockGearContext(
            config={
                "parameter_path": "/directory/test",
                "user_file": "users.yaml",
                "notifications_path": "/prod/notifications",
                "preceding_hours": 6,
            }
        )

        with caplog.at_level(logging.INFO), patched_redcap():
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

        log_messages = " ".join(caplog.messages)
        assert "Incremental pull" in log_messages
        assert "preceding_hours=6" in log_messages
        assert "date range" in log_messages

    def test_logs_full_pull_when_preceding_hours_zero(
        self,
        mock_parameter_store: MockParameterStore,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When preceding_hours == 0, log message indicates full pull with no
        date filtering.

        Validates: Requirements 6.2
        """
        context = MockGearContext()

        with caplog.at_level(logging.INFO), patched_redcap():
            DirectoryPullVisitor.create(
                context=context,  # type: ignore[arg-type]
                parameter_store=mock_parameter_store,  # type: ignore[arg-type]
            )

        log_messages = " ".join(caplog.messages)
        assert "Pulling all records" in log_messages
        assert "no date filtering" in log_messages
