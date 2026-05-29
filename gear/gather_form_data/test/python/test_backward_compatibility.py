"""Backward compatibility tests for participant_list mode.

Verifies that existing behavior is unchanged when `execution_mode` is
`participant_list` or unset, and that `input_file` is still required in
participant_list mode.

Validates: Requirements 9.1, 9.2, 9.3, 9.4
"""

from unittest.mock import MagicMock, patch

import pytest
from gather_form_data_app.run import GatherFormDataVisitor, ProjectModeVisitor, main


@pytest.fixture
def mock_gear_engine():
    """Create a mock GearEngine that captures the gear_type passed to run."""
    with patch("gather_form_data_app.run.GearEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine_cls.return_value.create_with_parameter_store.return_value = (
            mock_engine
        )
        yield mock_engine


@pytest.fixture
def mock_gear_context():
    """Create a mock GearContext as a context manager."""
    with patch("gather_form_data_app.run.GearContext") as mock_ctx_cls:
        mock_context = MagicMock()
        mock_ctx_cls.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_context


class TestDefaultModeUsesParticipantList:
    """When execution_mode is not set, the gear uses GatherFormDataVisitor.

    Validates: Requirement 9.1
    """

    def test_default_mode_uses_participant_list(
        self, mock_gear_engine: MagicMock, mock_gear_context: MagicMock
    ):
        """When execution_mode is absent from config, default to
        participant_list and use GatherFormDataVisitor."""
        mock_gear_context.config.opts = {}
        mock_gear_context.config.get_input_path.return_value = "/path/to/input.csv"

        main()

        mock_gear_engine.run.assert_called_once_with(gear_type=GatherFormDataVisitor)


class TestExplicitParticipantListMode:
    """When execution_mode is explicitly 'participant_list',
    GatherFormDataVisitor is used.

    Validates: Requirement 9.2
    """

    def test_explicit_participant_list_mode(
        self, mock_gear_engine: MagicMock, mock_gear_context: MagicMock
    ):
        """When execution_mode is 'participant_list', use
        GatherFormDataVisitor."""
        mock_gear_context.config.opts = {"execution_mode": "participant_list"}
        mock_gear_context.config.get_input_path.return_value = "/path/to/input.csv"

        main()

        mock_gear_engine.run.assert_called_once_with(gear_type=GatherFormDataVisitor)


class TestParticipantListModeRequiresInputFile:
    """When execution_mode is 'participant_list' and input_file is not
    provided, the gear logs an error and exits with failure.

    Validates: Requirement 9.4
    """

    def test_participant_list_mode_requires_input_file(
        self, mock_gear_engine: MagicMock, mock_gear_context: MagicMock
    ):
        """When input_file is None in participant_list mode, sys.exit(1) is
        called."""
        mock_gear_context.config.opts = {"execution_mode": "participant_list"}
        mock_gear_context.config.get_input_path.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_gear_engine.run.assert_not_called()

    def test_default_mode_requires_input_file(
        self, mock_gear_engine: MagicMock, mock_gear_context: MagicMock
    ):
        """When execution_mode is unset and input_file is None, sys.exit(1) is
        called."""
        mock_gear_context.config.opts = {}
        mock_gear_context.config.get_input_path.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_gear_engine.run.assert_not_called()


class TestProjectModeDoesNotRequireInputFile:
    """When execution_mode is 'project', no error about missing input_file.

    Validates: Requirement 3.2
    """

    def test_project_mode_does_not_require_input_file(
        self, mock_gear_engine: MagicMock, mock_gear_context: MagicMock
    ):
        """When execution_mode is 'project' and input_file is None, the gear
        proceeds without error."""
        mock_gear_context.config.opts = {"execution_mode": "project"}
        mock_gear_context.config.get_input_path.return_value = None

        main()

        mock_gear_engine.run.assert_called_once_with(gear_type=ProjectModeVisitor)


class TestInvalidModeExitsWithError:
    """When execution_mode is an invalid value, error is logged and sys.exit(1)
    is called.

    Validates: Requirement 1.4
    """

    def test_invalid_mode_exits_with_error(
        self,
        mock_gear_engine: MagicMock,
        mock_gear_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """When execution_mode is invalid, log error and exit."""
        mock_gear_context.config.opts = {"execution_mode": "invalid_mode"}
        mock_gear_context.config.get_input_path.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert "Invalid execution_mode" in caplog.text
        mock_gear_engine.run.assert_not_called()
