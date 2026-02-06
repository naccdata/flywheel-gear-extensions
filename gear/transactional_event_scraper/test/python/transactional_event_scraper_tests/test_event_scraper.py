"""Unit tests for the EventScraper class."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from event_capture.event_capture import VisitEventCapture
from event_capture.models import DateRange
from flywheel.models.file_entry import FileEntry
from test_mocks.mock_flywheel import MockFile, MockProjectAdaptor
from transactional_event_scraper_app.event_scraper import EventScraper


@pytest.fixture
def mock_project():
    """Create a mock project with QC status log files."""
    log_files: list[FileEntry] = [
        MockFile(
            name="110001_2024-01-15_uds_qc-status.log",
            created=datetime(2024, 1, 15, 10, 0, 0),
            modified=datetime(2024, 1, 15, 11, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "PASS", "data": []},
                    },
                },
                "visit": {
                    "ptid": "110001",
                    "date": "2024-01-15",
                    "visitnum": "001",
                    "module": "UDS",
                    "packet": "z1x",
                },
            },
        ),
        MockFile(
            name="110002_2024-01-16_uds_qc-status.log",
            created=datetime(2024, 1, 16, 10, 0, 0),
            modified=datetime(2024, 1, 16, 11, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "FAIL", "data": []},
                    },
                },
                "visit": {
                    "ptid": "110002",
                    "date": "2024-01-16",
                    "visitnum": "002",
                    "module": "UDS",
                    "packet": "z1x",
                },
            },
        ),
        MockFile(
            name="110003_2024-01-17_uds_qc-status.log",
            created=datetime(2024, 1, 17, 10, 0, 0),
            modified=datetime(2024, 1, 17, 11, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "PASS", "data": []},
                    },
                },
                "visit": {
                    "ptid": "110003",
                    "date": "2024-01-17",
                    "visitnum": "003",
                    "module": "UDS",
                    "packet": "z1x",
                },
            },
        ),
        # Non-log file to test filtering
        MockFile(
            name="some-other-file.txt",
            created=datetime(2024, 1, 18, 10, 0, 0),
            modified=datetime(2024, 1, 18, 11, 0, 0),
        ),
    ]

    return MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=log_files,
    )


@pytest.fixture
def mock_event_capture():
    """Create a mock event capture."""
    return Mock(spec=VisitEventCapture)


def test_event_scraper_initialization(mock_project):
    """Test EventScraper initialization."""
    scraper = EventScraper(mock_project)
    assert scraper is not None
    assert scraper._project == mock_project  # noqa: SLF001
    assert scraper._event_capture is None  # noqa: SLF001
    assert scraper._dry_run is False  # noqa: SLF001
    assert scraper._date_filter is None  # noqa: SLF001
    # Verify processors are initialized
    assert scraper._submit_processor is not None  # noqa: SLF001
    assert scraper._qc_processor is not None  # noqa: SLF001
    assert scraper._unmatched_events is not None  # noqa: SLF001


def test_event_scraper_initialization_with_options(mock_project, mock_event_capture):
    """Test EventScraper initialization with all options."""
    date_filter = DateRange(
        start_date=datetime(2024, 1, 1), end_date=datetime(2024, 12, 31)
    )
    scraper = EventScraper(
        mock_project,
        event_capture=mock_event_capture,
        dry_run=True,
        date_filter=date_filter,
    )
    assert scraper._project == mock_project  # noqa: SLF001
    assert scraper._event_capture == mock_event_capture  # noqa: SLF001
    assert scraper._dry_run is True  # noqa: SLF001
    assert scraper._date_filter == date_filter  # noqa: SLF001


def test_scrape_events_three_phase_workflow(mock_project, caplog):
    """Test that scrape_events executes the three-phase workflow."""
    import logging

    caplog.set_level(logging.INFO)

    scraper = EventScraper(mock_project, dry_run=True)
    scraper.scrape_events()

    # Verify all three phases are logged
    assert "Phase 1: Processing QC status logs" in caplog.text
    assert "Phase 2: Processing JSON files and matching events" in caplog.text
    assert "Processing complete" in caplog.text


def test_scrape_events_returns_none(mock_project):
    """Test that scrape_events returns None (no longer returns statistics)."""
    scraper = EventScraper(mock_project, dry_run=True)
    scraper.scrape_events()
    # scrape_events returns None, so we just verify it completes without error


def test_scrape_events_logs_unmatched_events(mock_project, caplog):
    """Test that unmatched submit events are logged at completion."""
    import logging

    caplog.set_level(logging.WARNING)

    scraper = EventScraper(mock_project, dry_run=True)
    scraper.scrape_events()

    # Since we only process QC logs and no JSON files, all submit events remain
    #  unmatched
    assert "unmatched submit events" in caplog.text.lower()


def test_scrape_events_empty_project():
    """Test scraping events from project with no log files."""
    empty_project = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )

    scraper = EventScraper(empty_project, dry_run=True)
    # Should complete without errors
    scraper.scrape_events()


def test_scrape_events_completion_message_all_matched(mock_project, caplog):
    """Test completion message when all events are matched."""
    import logging
    from unittest.mock import patch

    caplog.set_level(logging.INFO)

    scraper = EventScraper(mock_project, dry_run=True)

    # Mock get_remaining to return empty list
    with patch.object(
        scraper._unmatched_events,  # noqa: SLF001
        "get_remaining",
        return_value=[],
    ):
        scraper.scrape_events()

    # Should log success message
    assert "all submit events matched and enriched" in caplog.text


def test_scrape_events_completion_message_with_unmatched(mock_project, caplog):
    """Test completion message when unmatched events remain."""
    import logging

    caplog.set_level(logging.WARNING)

    scraper = EventScraper(mock_project, dry_run=True)
    scraper.scrape_events()

    # Should log warning about unmatched events
    assert "unmatched submit events" in caplog.text.lower()
    # Should log sample of unmatched events
    assert "Unmatched:" in caplog.text
