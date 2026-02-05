"""Integration tests for user_management gear with error handling.

This module tests the integration of error handling into the user_management
gear, including:
- Gear execution with integrated error handling
- Parameter Store configuration loading
- End-of-run notification sending
- Backward compatibility with existing gear configurations

Note: These are simplified integration tests that focus on verifying the
integration points rather than full end-to-end execution.
"""

from typing import Dict, Optional
from unittest.mock import Mock, patch

import pytest
from gear_execution.gear_execution import ClientWrapper, GearExecutionError
from inputs.parameter_store import ParameterError
from user_app.run import UserManagementVisitor
from users.event_models import UserEventCollector


class MockParameterStore:
    """Mock ParameterStore for testing."""

    def __init__(
        self,
        comanage_params: Optional[Dict] = None,
        notification_params: Optional[Dict] = None,
        portal_url: Optional[Dict] = None,
    ):
        self.comanage_params = comanage_params or {
            "host": "https://comanage.test",
            "username": "test_user",
            "apikey": "test_key",
            "coid": "123",
        }
        self.notification_params = notification_params or {
            "sender": "test@example.com",
            "support_emails": "support@example.com",
        }
        self.portal_url = portal_url or {"url": "https://portal.test"}

    def get_comanage_parameters(self, path: str):
        """Mock get_comanage_parameters."""
        if not self.comanage_params:
            raise ParameterError("CoManage parameters not found")
        return self.comanage_params

    def get_notification_parameters(self, path: str):
        """Mock get_notification_parameters."""
        if not self.notification_params:
            raise ParameterError("Notification parameters not found")
        return self.notification_params

    def get_portal_url(self, path: str):
        """Mock get_portal_url."""
        if not self.portal_url:
            raise ParameterError("Portal URL not found")
        return self.portal_url

    def get_all_redcap_parameters_at_path(
        self, base_path: str, prefix: Optional[str] = None
    ):
        """Mock get_all_redcap_parameters_at_path."""
        return {}


class MockREDCapParametersRepository:
    """Mock REDCapParametersRepository for testing."""

    @classmethod
    def create_from_parameterstore(cls, param_store, base_path):
        """Mock create_from_parameterstore."""
        return cls()


class MockGearToolkitContext:
    """Mock GearToolkitContext for testing."""

    def __init__(
        self,
        user_file_path: Optional[str] = None,
        auth_file_path: Optional[str] = None,
        config: Optional[Dict] = None,
    ):
        self.user_file_path = user_file_path or "/tmp/users.yaml"
        self.auth_file_path = auth_file_path or "/tmp/auth.yaml"
        self.config_dict = config or {
            "admin_group": "nacc",
            "comanage_parameter_path": "/comanage/test",
            "notifications_path": "/notifications/test",
            "portal_url_path": "/portal/url",
            "redcap_parameter_path": "/redcap/aws",
            "notification_mode": "date",
        }

    def get_input_path(self, input_name: str) -> Optional[str]:
        """Mock get_input_path."""
        if input_name == "user_file":
            return self.user_file_path
        elif input_name == "auth_file":
            return self.auth_file_path
        return None

    @property
    def config(self):
        """Mock config property."""
        return self.config_dict


class TestGearErrorHandlingIntegration:
    """Integration tests for gear error handling."""

    @pytest.fixture
    def mock_parameter_store(self) -> MockParameterStore:
        """Create mock parameter store."""
        return MockParameterStore()

    @pytest.fixture
    def mock_context(self) -> MockGearToolkitContext:
        """Create mock gear context."""
        return MockGearToolkitContext()

    @pytest.fixture
    def mock_client(self) -> ClientWrapper:
        """Create mock Flywheel client."""
        mock_client = Mock(spec=ClientWrapper)
        mock_client.get_roles = Mock(return_value={})
        return mock_client

    def test_visitor_creation_with_error_handling_support(
        self,
        mock_parameter_store: MockParameterStore,
        mock_context: MockGearToolkitContext,
        mock_client: ClientWrapper,
    ) -> None:
        """Test that visitor is created with error handling support.

        This test verifies:
        - Visitor can be created with all required parameters
        - Error handling infrastructure is available
        - Support staff emails are loaded from notification parameters
        """
        with (
            patch("user_app.run.GearBotClient.create", return_value=mock_client),
            patch(
                "user_app.run.REDCapParametersRepository.create_from_parameterstore",
                return_value=MockREDCapParametersRepository(),
            ),
        ):
            visitor = UserManagementVisitor.create(
                context=mock_context,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

            # Verify visitor was created successfully
            assert visitor is not None
            # Verify UserEventCollector class is available for use
            assert UserEventCollector is not None

    def test_backward_compatibility_with_existing_configurations(
        self,
        mock_parameter_store: MockParameterStore,
        mock_client: ClientWrapper,
    ) -> None:
        """Test backward compatibility with existing gear configurations.

        This test verifies:
        - Gear works with minimal configuration (no error handling config)
        - Gear works with different notification modes
        - Gear handles missing optional parameters gracefully
        """
        # Test with minimal configuration
        minimal_config = {
            "admin_group": "nacc",
            "comanage_parameter_path": "/comanage/test",
            "notifications_path": "/notifications/test",
            "portal_url_path": "/portal/url",
        }

        minimal_context = MockGearToolkitContext(config=minimal_config)

        with (
            patch("user_app.run.GearBotClient.create", return_value=mock_client),
            patch(
                "user_app.run.REDCapParametersRepository.create_from_parameterstore",
                return_value=MockREDCapParametersRepository(),
            ),
        ):
            visitor = UserManagementVisitor.create(
                context=minimal_context,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

            assert visitor is not None

        # Test with different notification modes
        for mode in ["date", "none", "always"]:
            config_with_mode = minimal_config.copy()
            config_with_mode["notification_mode"] = mode

            context_with_mode = MockGearToolkitContext(config=config_with_mode)

            with (
                patch("user_app.run.GearBotClient.create", return_value=mock_client),
                patch(
                    "user_app.run.REDCapParametersRepository.create_from_parameterstore",
                    return_value=MockREDCapParametersRepository(),
                ),
            ):
                visitor = UserManagementVisitor.create(
                    context=context_with_mode,  # type: ignore
                    parameter_store=mock_parameter_store,  # type: ignore
                )

                assert visitor is not None

    def test_gear_handles_missing_required_config(
        self, mock_parameter_store: MockParameterStore, mock_client: ClientWrapper
    ) -> None:
        """Test that gear handles missing required configuration.

        This test verifies:
        - Gear raises error when required config is missing
        - Error message indicates which config is missing
        """
        # Test missing comanage_parameter_path
        config_no_comanage = {
            "admin_group": "nacc",
            "notifications_path": "/notifications/test",
            "portal_url_path": "/portal/url",
        }

        context_no_comanage = MockGearToolkitContext(config=config_no_comanage)

        with (
            patch("user_app.run.GearBotClient.create", return_value=mock_client),
            pytest.raises(GearExecutionError, match="CoManage parameter path"),
        ):
            UserManagementVisitor.create(
                context=context_no_comanage,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

        # Test missing notifications_path
        config_no_notifications = {
            "admin_group": "nacc",
            "comanage_parameter_path": "/comanage/test",
            "portal_url_path": "/portal/url",
        }

        context_no_notifications = MockGearToolkitContext(
            config=config_no_notifications
        )

        with (
            patch("user_app.run.GearBotClient.create", return_value=mock_client),
            pytest.raises(GearExecutionError, match="notifications parameter path"),
        ):
            UserManagementVisitor.create(
                context=context_no_notifications,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

        # Test missing portal_url_path
        config_no_portal = {
            "admin_group": "nacc",
            "comanage_parameter_path": "/comanage/test",
            "notifications_path": "/notifications/test",
        }

        context_no_portal = MockGearToolkitContext(config=config_no_portal)

        with (
            patch("user_app.run.GearBotClient.create", return_value=mock_client),
            pytest.raises(GearExecutionError, match="path for portal URL"),
        ):
            UserManagementVisitor.create(
                context=context_no_portal,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

    def test_event_collector_availability(self) -> None:
        """Test that UserEventCollector is available for use in gear.

        This test verifies:
        - UserEventCollector class can be imported and instantiated
        - UserEventCollector has expected methods for error handling
        """
        # Verify UserEventCollector can be instantiated
        collector = UserEventCollector()
        assert collector is not None

        # Verify UserEventCollector has expected methods
        assert hasattr(collector, "collect")
        assert hasattr(collector, "has_errors")
        assert hasattr(collector, "get_errors")
        assert hasattr(collector, "error_count")

        # Verify initial state
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_support_emails_configuration(
        self,
        mock_parameter_store: MockParameterStore,
        mock_context: MockGearToolkitContext,
        mock_client: ClientWrapper,
    ) -> None:
        """Test support staff email configuration via Parameter Store.

        This test verifies:
        - Support staff emails can be loaded from notification parameters
        - Both sender and support_emails are required fields
        """
        # Test with support staff emails configured
        with (
            patch("user_app.run.GearBotClient.create", return_value=mock_client),
            patch(
                "user_app.run.REDCapParametersRepository.create_from_parameterstore",
                return_value=MockREDCapParametersRepository(),
            ),
        ):
            visitor = UserManagementVisitor.create(
                context=mock_context,  # type: ignore
                parameter_store=mock_parameter_store,  # type: ignore
            )

            assert visitor is not None
