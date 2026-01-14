"""Unit tests for the TransactionalEventScraperVisitor class."""

from unittest.mock import Mock, patch

import pytest
from event_capture.event_capture import VisitEventCapture
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from inputs.parameter_store import ParameterStore
from s3.s3_bucket import S3BucketInterface
from transactional_event_scraper_app.config import TransactionalEventScraperConfig
from transactional_event_scraper_app.models import ProcessingStatistics
from transactional_event_scraper_app.run import TransactionalEventScraperVisitor


@pytest.fixture
def mock_context():
    """Create a mock gear context."""
    context = Mock(spec=GearToolkitContext)
    context.config = {
        "dry_run": False,
        "event_bucket": "test-bucket",
        "event_environment": "dev",
        "apikey_path_prefix": "/test/path",
    }
    context.manifest = {"name": "transactional-event-scraper"}
    context.config_json = {"job": {"id": "test-job-id"}}
    return context


@pytest.fixture
def mock_parameter_store():
    """Create a mock parameter store."""
    return Mock(spec=ParameterStore)


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return TransactionalEventScraperConfig(
        dry_run=False,
        event_bucket="test-bucket",
        event_environment="dev",
        apikey_path_prefix="/test/path",
    )


def test_visitor_initialization(mock_config):
    """Test visitor initialization."""
    mock_client = Mock()
    mock_event_capture = Mock(spec=VisitEventCapture)

    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=mock_config, event_capture=mock_event_capture
    )

    assert visitor is not None


def test_visitor_initialization_without_event_capture(mock_config):
    """Test visitor initialization without event capture (dry-run mode)."""
    mock_client = Mock()

    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=mock_config, event_capture=None
    )

    assert visitor is not None


@patch("transactional_event_scraper_app.run.GearBotClient")
@patch("transactional_event_scraper_app.run.S3BucketInterface")
@patch("transactional_event_scraper_app.run.parse_gear_config")
def test_create_visitor_success(
    mock_parse_config,
    mock_s3_bucket,
    mock_gear_bot_client,
    mock_context,
    mock_parameter_store,
    mock_config,
):
    """Test successful visitor creation."""
    # Setup mocks
    mock_parse_config.return_value = mock_config
    mock_client = Mock()
    mock_gear_bot_client.create.return_value = mock_client
    mock_bucket = Mock(spec=S3BucketInterface)
    mock_s3_bucket.create_from_environment.return_value = mock_bucket

    # Create visitor
    visitor = TransactionalEventScraperVisitor.create(
        context=mock_context, parameter_store=mock_parameter_store
    )

    # Verify visitor was created
    assert visitor is not None
    assert isinstance(visitor, TransactionalEventScraperVisitor)

    # Verify dependencies were initialized
    mock_parse_config.assert_called_once_with(mock_context)
    mock_gear_bot_client.create.assert_called_once_with(
        context=mock_context, parameter_store=mock_parameter_store
    )
    mock_s3_bucket.create_from_environment.assert_called_once_with("test-bucket")


@patch("transactional_event_scraper_app.run.GearBotClient")
@patch("transactional_event_scraper_app.run.parse_gear_config")
def test_create_visitor_dry_run_mode(
    mock_parse_config,
    mock_gear_bot_client,
    mock_context,
    mock_parameter_store,
):
    """Test visitor creation in dry-run mode (no S3 initialization)."""
    # Setup mocks for dry-run mode
    dry_run_config = TransactionalEventScraperConfig(
        dry_run=True,
        event_bucket="test-bucket",
        event_environment="dev",
        apikey_path_prefix="/test/path",
    )
    mock_parse_config.return_value = dry_run_config
    mock_client = Mock()
    mock_gear_bot_client.create.return_value = mock_client

    # Create visitor
    visitor = TransactionalEventScraperVisitor.create(
        context=mock_context, parameter_store=mock_parameter_store
    )

    # Verify visitor was created without event capture
    assert visitor is not None


@patch("transactional_event_scraper_app.run.GearBotClient")
@patch("transactional_event_scraper_app.run.parse_gear_config")
def test_create_visitor_missing_parameter_store(
    mock_parse_config, mock_gear_bot_client, mock_context
):
    """Test visitor creation fails without parameter store."""
    with pytest.raises(AssertionError, match="Parameter store expected"):
        TransactionalEventScraperVisitor.create(
            context=mock_context, parameter_store=None
        )


@patch("transactional_event_scraper_app.run.GearBotClient")
@patch("transactional_event_scraper_app.run.parse_gear_config")
def test_create_visitor_config_parsing_error(
    mock_parse_config, mock_gear_bot_client, mock_context, mock_parameter_store
):
    """Test visitor creation fails with invalid configuration."""
    # Make config parsing raise an error
    mock_parse_config.side_effect = GearExecutionError("Invalid configuration")

    with pytest.raises(GearExecutionError, match="Invalid configuration"):
        TransactionalEventScraperVisitor.create(
            context=mock_context, parameter_store=mock_parameter_store
        )


@patch("transactional_event_scraper_app.run.GearBotClient")
@patch("transactional_event_scraper_app.run.S3BucketInterface")
@patch("transactional_event_scraper_app.run.parse_gear_config")
def test_create_visitor_s3_initialization_error(
    mock_parse_config,
    mock_s3_bucket,
    mock_gear_bot_client,
    mock_context,
    mock_parameter_store,
    mock_config,
):
    """Test visitor creation fails when S3 bucket is inaccessible."""
    # Setup mocks
    mock_parse_config.return_value = mock_config
    mock_client = Mock()
    mock_gear_bot_client.create.return_value = mock_client
    # Make S3 bucket creation fail
    mock_s3_bucket.create_from_environment.side_effect = Exception("S3 access denied")

    with pytest.raises(
        GearExecutionError,
        match="Failed to initialize visit event capture.*S3 access denied",
    ):
        TransactionalEventScraperVisitor.create(
            context=mock_context, parameter_store=mock_parameter_store
        )


@patch("transactional_event_scraper_app.run.run")
def test_visitor_run_success(mock_run, mock_context, mock_config):
    """Test successful visitor run."""
    # Setup mocks
    mock_client = Mock()
    mock_event_capture = Mock(spec=VisitEventCapture)
    expected_stats = ProcessingStatistics(
        files_processed=5,
        submission_events_created=5,
        pass_qc_events_created=3,
        errors_encountered=0,
        skipped_files=0,
    )
    mock_run.return_value = expected_stats

    # Create and run visitor
    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=mock_config, event_capture=mock_event_capture
    )
    visitor.run(mock_context)

    # Verify run was called with correct parameters
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert "context" in call_kwargs
    assert "proxy" in call_kwargs
    assert call_kwargs["config"] == mock_config
    assert call_kwargs["event_capture"] == mock_event_capture


@patch("transactional_event_scraper_app.run.run")
def test_visitor_run_with_date_filters(mock_run, mock_context):
    """Test visitor run with date filters configured."""
    # Setup config with date filters
    config = TransactionalEventScraperConfig(
        dry_run=False,
        event_bucket="test-bucket",
        event_environment="dev",
        start_date="2024-01-01",
        end_date="2024-12-31",
        apikey_path_prefix="/test/path",
    )
    mock_client = Mock()
    mock_event_capture = Mock(spec=VisitEventCapture)
    mock_run.return_value = ProcessingStatistics()

    # Create and run visitor
    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=config, event_capture=mock_event_capture
    )
    visitor.run(mock_context)

    # Verify run was called
    mock_run.assert_called_once()


@patch("transactional_event_scraper_app.run.run")
def test_visitor_run_execution_error(mock_run, mock_context, mock_config):
    """Test visitor run handles execution errors."""
    # Setup mocks
    mock_client = Mock()
    mock_event_capture = Mock(spec=VisitEventCapture)
    mock_run.side_effect = Exception("Scraping failed")

    # Create visitor
    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=mock_config, event_capture=mock_event_capture
    )

    # Run should raise GearExecutionError
    with pytest.raises(
        GearExecutionError, match="Transactional Event Scraper execution failed"
    ):
        visitor.run(mock_context)


@patch("transactional_event_scraper_app.run.run")
def test_visitor_run_dry_run_mode(mock_run, mock_context):
    """Test visitor run in dry-run mode."""
    # Setup config for dry-run
    config = TransactionalEventScraperConfig(
        dry_run=True,
        event_bucket="test-bucket",
        event_environment="dev",
        apikey_path_prefix="/test/path",
    )
    mock_client = Mock()
    mock_run.return_value = ProcessingStatistics(
        files_processed=5,
        submission_events_created=5,
        pass_qc_events_created=3,
        errors_encountered=0,
        skipped_files=0,
    )

    # Create and run visitor (no event capture in dry-run mode)
    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=config, event_capture=None
    )
    visitor.run(mock_context)

    # Verify run was called with None for event_capture
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["event_capture"] is None


def test_visitor_inherits_from_gear_execution_environment(mock_config):
    """Test that visitor properly inherits from GearExecutionEnvironment."""
    from gear_execution.gear_execution import GearExecutionEnvironment

    mock_client = Mock()
    visitor = TransactionalEventScraperVisitor(
        client=mock_client, config=mock_config, event_capture=None
    )

    assert isinstance(visitor, GearExecutionEnvironment)
    # Verify proxy is accessible (inherited from GearExecutionEnvironment)
    assert hasattr(visitor, "proxy")


@patch("transactional_event_scraper_app.run.GearBotClient")
@patch("transactional_event_scraper_app.run.S3BucketInterface")
@patch("transactional_event_scraper_app.run.VisitEventCapture")
@patch("transactional_event_scraper_app.run.parse_gear_config")
def test_create_visitor_initializes_event_capture_correctly(
    mock_parse_config,
    mock_visit_event_capture,
    mock_s3_bucket,
    mock_gear_bot_client,
    mock_context,
    mock_parameter_store,
    mock_config,
):
    """Test that visitor correctly initializes VisitEventCapture with S3 bucket
    and environment."""
    # Setup mocks
    mock_parse_config.return_value = mock_config
    mock_client = Mock()
    mock_gear_bot_client.create.return_value = mock_client
    mock_bucket = Mock(spec=S3BucketInterface)
    mock_s3_bucket.create_from_environment.return_value = mock_bucket
    mock_event_capture_instance = Mock(spec=VisitEventCapture)
    mock_visit_event_capture.return_value = mock_event_capture_instance

    # Create visitor
    visitor = TransactionalEventScraperVisitor.create(
        context=mock_context, parameter_store=mock_parameter_store
    )

    # Verify VisitEventCapture was initialized with correct parameters
    mock_visit_event_capture.assert_called_once_with(
        s3_bucket=mock_bucket, environment="dev"
    )
    assert visitor is not None
