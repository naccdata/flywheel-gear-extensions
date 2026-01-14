"""Unit tests for the main run function."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from event_capture.event_capture import VisitEventCapture
from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from test_mocks.mock_flywheel import MockProject, MockProjectAdaptor
from transactional_event_scraper_app.config import TransactionalEventScraperConfig
from transactional_event_scraper_app.main import run
from transactional_event_scraper_app.models import ProcessingStatistics


@pytest.fixture
def mock_context():
    """Create a mock gear context."""
    context = Mock(spec=GearToolkitContext)
    destination = Mock()
    destination.container_type = "project"
    destination.id = "test-project-id"
    context.get_destination_container.return_value = destination
    return context


@pytest.fixture
def mock_proxy():
    """Create a mock Flywheel proxy."""
    return Mock()


@pytest.fixture
def mock_project():
    """Create a mock project."""
    return MockProject(
        id="test-project-id",
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
    )


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return TransactionalEventScraperConfig(
        dry_run=False,
        event_bucket="test-bucket",
        event_environment="dev",
        apikey_path_prefix="/test/path",
    )


@pytest.fixture
def mock_event_capture():
    """Create a mock event capture."""
    return Mock(spec=VisitEventCapture)


@patch("transactional_event_scraper_app.main.EventScraper")
@patch("transactional_event_scraper_app.main.ProjectAdaptor")
def test_run_success(
    mock_project_adaptor_class,
    mock_event_scraper_class,
    mock_context,
    mock_proxy,
    mock_project,
    mock_config,
    mock_event_capture,
):
    """Test successful run of the scraper."""
    # Setup mocks
    mock_proxy.get_project_by_id.return_value = mock_project
    mock_project_adaptor = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )
    mock_project_adaptor_class.return_value = mock_project_adaptor

    expected_stats = ProcessingStatistics(
        files_processed=5,
        submission_events_created=5,
        pass_qc_events_created=3,
        errors_encountered=0,
        skipped_files=0,
    )
    mock_scraper = Mock()
    mock_scraper.scrape_events.return_value = expected_stats
    mock_event_scraper_class.return_value = mock_scraper

    # Run the scraper
    result = run(
        context=mock_context,
        proxy=mock_proxy,
        config=mock_config,
        event_capture=mock_event_capture,
    )

    # Verify result
    assert result == expected_stats

    # Verify destination was retrieved
    mock_context.get_destination_container.assert_called_once()
    mock_proxy.get_project_by_id.assert_called_once_with("test-project-id")

    # Verify ProjectAdaptor was created
    mock_project_adaptor_class.assert_called_once_with(
        project=mock_project, proxy=mock_proxy
    )

    # Verify EventScraper was created with correct parameters
    mock_event_scraper_class.assert_called_once_with(
        project=mock_project_adaptor,
        event_capture=mock_event_capture,
        dry_run=False,
        date_filter=None,
    )

    # Verify scrape_events was called
    mock_scraper.scrape_events.assert_called_once()


@patch("transactional_event_scraper_app.main.EventScraper")
@patch("transactional_event_scraper_app.main.ProjectAdaptor")
def test_run_dry_run_mode(
    mock_project_adaptor_class,
    mock_event_scraper_class,
    mock_context,
    mock_proxy,
    mock_project,
):
    """Test run in dry-run mode (no event capture)."""
    # Setup config for dry-run
    config = TransactionalEventScraperConfig(
        dry_run=True,
        event_bucket="test-bucket",
        event_environment="dev",
        apikey_path_prefix="/test/path",
    )

    # Setup mocks
    mock_proxy.get_project_by_id.return_value = mock_project
    mock_project_adaptor = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )
    mock_project_adaptor_class.return_value = mock_project_adaptor

    expected_stats = ProcessingStatistics()
    mock_scraper = Mock()
    mock_scraper.scrape_events.return_value = expected_stats
    mock_event_scraper_class.return_value = mock_scraper

    # Run the scraper without event capture
    run(context=mock_context, proxy=mock_proxy, config=config, event_capture=None)

    # Verify EventScraper was created with None for event_capture
    mock_event_scraper_class.assert_called_once()
    call_kwargs = mock_event_scraper_class.call_args.kwargs
    assert call_kwargs["event_capture"] is None
    assert call_kwargs["dry_run"] is True


@patch("transactional_event_scraper_app.main.EventScraper")
@patch("transactional_event_scraper_app.main.ProjectAdaptor")
def test_run_with_date_filters(
    mock_project_adaptor_class,
    mock_event_scraper_class,
    mock_context,
    mock_proxy,
    mock_project,
    mock_event_capture,
):
    """Test run with date filters configured."""
    # Setup config with date filters
    config = TransactionalEventScraperConfig(
        dry_run=False,
        event_bucket="test-bucket",
        event_environment="dev",
        start_date="2024-01-01",
        end_date="2024-12-31",
        apikey_path_prefix="/test/path",
    )

    # Setup mocks
    mock_proxy.get_project_by_id.return_value = mock_project
    mock_project_adaptor = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )
    mock_project_adaptor_class.return_value = mock_project_adaptor

    expected_stats = ProcessingStatistics()
    mock_scraper = Mock()
    mock_scraper.scrape_events.return_value = expected_stats
    mock_event_scraper_class.return_value = mock_scraper

    # Run the scraper
    run(
        context=mock_context,
        proxy=mock_proxy,
        config=config,
        event_capture=mock_event_capture,
    )

    # Verify EventScraper was created with date_filter
    mock_event_scraper_class.assert_called_once()
    call_kwargs = mock_event_scraper_class.call_args.kwargs
    assert call_kwargs["date_filter"] is not None
    assert call_kwargs["date_filter"].start_date == datetime(2024, 1, 1)
    assert call_kwargs["date_filter"].end_date.year == 2024
    assert call_kwargs["date_filter"].end_date.month == 12
    assert call_kwargs["date_filter"].end_date.day == 31


def test_run_no_destination(mock_proxy, mock_config, mock_event_capture):
    """Test run fails when no destination container is found."""
    # Create context that returns None for destination
    context = Mock(spec=GearToolkitContext)
    context.get_destination_container.return_value = None

    with pytest.raises(GearExecutionError, match="No destination container found"):
        run(
            context=context,
            proxy=mock_proxy,
            config=mock_config,
            event_capture=mock_event_capture,
        )


def test_run_wrong_container_type(mock_proxy, mock_config, mock_event_capture):
    """Test run fails when executed on non-project container."""
    # Setup context with subject destination instead of project
    context = Mock(spec=GearToolkitContext)
    destination = Mock()
    destination.container_type = "subject"
    destination.id = "test-subject-id"
    context.get_destination_container.return_value = destination

    with pytest.raises(
        GearExecutionError,
        match="Unsupported container type subject.*must be executed at project level",
    ):
        run(
            context=context,
            proxy=mock_proxy,
            config=mock_config,
            event_capture=mock_event_capture,
        )


def test_run_api_exception(mock_proxy, mock_config, mock_event_capture):
    """Test run handles Flywheel API exceptions."""
    # Create context that raises ApiException
    context = Mock(spec=GearToolkitContext)
    context.get_destination_container.side_effect = ApiException("API error")

    with pytest.raises(GearExecutionError, match="Flywheel API error"):
        run(
            context=context,
            proxy=mock_proxy,
            config=mock_config,
            event_capture=mock_event_capture,
        )


def test_run_project_not_found(
    mock_context, mock_proxy, mock_config, mock_event_capture
):
    """Test run fails when project cannot be found."""
    # Make get_project_by_id return None
    mock_proxy.get_project_by_id.return_value = None

    with pytest.raises(
        GearExecutionError, match="Cannot find project with ID test-project-id"
    ):
        run(
            context=mock_context,
            proxy=mock_proxy,
            config=mock_config,
            event_capture=mock_event_capture,
        )


@patch("transactional_event_scraper_app.main.EventScraper")
@patch("transactional_event_scraper_app.main.ProjectAdaptor")
def test_run_scraper_exception(
    mock_project_adaptor_class,
    mock_event_scraper_class,
    mock_context,
    mock_proxy,
    mock_project,
    mock_config,
    mock_event_capture,
):
    """Test run handles exceptions from EventScraper."""
    # Setup mocks
    mock_proxy.get_project_by_id.return_value = mock_project
    mock_project_adaptor = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )
    mock_project_adaptor_class.return_value = mock_project_adaptor

    # Make scraper raise an exception
    mock_scraper = Mock()
    mock_scraper.scrape_events.side_effect = Exception("Scraping failed")
    mock_event_scraper_class.return_value = mock_scraper

    with pytest.raises(GearExecutionError, match="Transactional Event Scraper failed"):
        run(
            context=mock_context,
            proxy=mock_proxy,
            config=mock_config,
            event_capture=mock_event_capture,
        )


@patch("transactional_event_scraper_app.main.EventScraper")
@patch("transactional_event_scraper_app.main.ProjectAdaptor")
def test_run_logs_project_info(
    mock_project_adaptor_class,
    mock_event_scraper_class,
    mock_context,
    mock_proxy,
    mock_project,
    mock_config,
    mock_event_capture,
    caplog,
):
    """Test that run logs project information."""
    import logging

    caplog.set_level(logging.INFO)

    # Setup mocks
    mock_proxy.get_project_by_id.return_value = mock_project
    mock_project_adaptor = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )
    mock_project_adaptor_class.return_value = mock_project_adaptor

    expected_stats = ProcessingStatistics()
    mock_scraper = Mock()
    mock_scraper.scrape_events.return_value = expected_stats
    mock_event_scraper_class.return_value = mock_scraper

    # Run the scraper
    run(
        context=mock_context,
        proxy=mock_proxy,
        config=mock_config,
        event_capture=mock_event_capture,
    )

    # Verify project info was logged
    assert "Processing project: ingest-form-adrc" in caplog.text
    assert "group: test-center" in caplog.text


@patch("transactional_event_scraper_app.main.EventScraper")
@patch("transactional_event_scraper_app.main.ProjectAdaptor")
def test_run_logs_configuration(
    mock_project_adaptor_class,
    mock_event_scraper_class,
    mock_context,
    mock_proxy,
    mock_project,
    mock_config,
    mock_event_capture,
    caplog,
):
    """Test that run logs configuration details."""
    import logging

    caplog.set_level(logging.INFO)

    # Setup mocks
    mock_proxy.get_project_by_id.return_value = mock_project
    mock_project_adaptor = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )
    mock_project_adaptor_class.return_value = mock_project_adaptor

    expected_stats = ProcessingStatistics()
    mock_scraper = Mock()
    mock_scraper.scrape_events.return_value = expected_stats
    mock_event_scraper_class.return_value = mock_scraper

    # Run the scraper
    run(
        context=mock_context,
        proxy=mock_proxy,
        config=mock_config,
        event_capture=mock_event_capture,
    )

    # Verify configuration was logged
    assert "Configuration:" in caplog.text
    assert "dry_run=False" in caplog.text
    assert "event_bucket=test-bucket" in caplog.text
    assert "event_environment=dev" in caplog.text
