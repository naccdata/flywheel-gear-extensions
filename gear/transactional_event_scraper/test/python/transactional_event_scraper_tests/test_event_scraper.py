"""Unit tests for the EventScraper class."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from event_capture.event_capture import VisitEventCapture
from event_capture.models import DateRange, SubmitEventData
from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import VisitMetadata
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


def test_discover_log_files(mock_project):
    """Test discovery of QC status log files."""
    scraper = EventScraper(mock_project)
    log_files = scraper._discover_log_files()  # noqa: SLF001

    # Should find 3 log files (excluding the .txt file)
    assert len(log_files) == 3
    assert all(file.name.endswith("_qc-status.log") for file in log_files)


def test_scrape_events_dry_run(mock_project):
    """Test scraping events in dry-run mode."""
    scraper = EventScraper(mock_project, dry_run=True)
    stats = scraper.scrape_events()

    # Should process 3 log files
    assert stats.files_processed == 3
    # Should create 3 submission events (one per file)
    assert stats.submission_events_created == 3
    # Should not create QC events (QC events come from event processor, not log files)
    assert stats.pass_qc_events_created == 0
    assert stats.errors_encountered == 0
    assert stats.skipped_files == 0


def test_scrape_events_with_capture(mock_project, mock_event_capture):
    """Test scraping events with event capture."""
    scraper = EventScraper(mock_project, event_capture=mock_event_capture)
    stats = scraper.scrape_events()

    # Should process 3 log files
    assert stats.files_processed == 3
    assert stats.submission_events_created == 3
    # Should not create QC events (QC events come from event processor, not log files)
    assert stats.pass_qc_events_created == 0

    # Should have called capture_event 3 times (3 submission events only)
    assert mock_event_capture.capture_event.call_count == 3


def test_scrape_events_with_date_filter(mock_project):
    """Test scraping events with date filter."""
    # Filter to only include files from Jan 16 onwards
    date_filter = DateRange(start_date=datetime(2024, 1, 16))
    scraper = EventScraper(mock_project, dry_run=True, date_filter=date_filter)
    stats = scraper.scrape_events()

    # Should process 2 log files (Jan 16 and Jan 17)
    assert stats.files_processed == 2
    assert stats.submission_events_created == 2
    # Should not create QC events (QC events come from event processor, not log files)
    assert stats.pass_qc_events_created == 0
    # Should skip 1 file (Jan 15)
    assert stats.skipped_files == 1


def test_scrape_events_with_date_range(mock_project):
    """Test scraping events with start and end date filter."""
    # Filter to only include files from Jan 16
    date_filter = DateRange(
        start_date=datetime(2024, 1, 16), end_date=datetime(2024, 1, 16, 23, 59, 59)
    )
    scraper = EventScraper(mock_project, dry_run=True, date_filter=date_filter)
    stats = scraper.scrape_events()

    # Should process 1 log file (Jan 16 only)
    assert stats.files_processed == 1
    assert stats.submission_events_created == 1
    # Should not create QC events (QC events come from event processor, not log files)
    assert stats.pass_qc_events_created == 0
    # Should skip 2 files (Jan 15 and Jan 17)
    assert stats.skipped_files == 2


def test_scrape_events_error_resilience(mock_project, mock_event_capture):
    """Test that scraper continues processing after individual file errors."""
    scraper = EventScraper(mock_project, event_capture=mock_event_capture)

    # Mock extract_event_from_log to fail on the second file
    with patch(
        "transactional_event_scraper_app.event_scraper.extract_event_from_log"
    ) as mock_extract:
        # First call succeeds, second raises exception, third succeeds
        mock_extract.side_effect = [
            SubmitEventData(
                visit_metadata=VisitMetadata(
                    ptid="110001",
                    date="2024-01-15",
                    visitnum="001",
                    module="UDS",
                    packet="z1x",
                ),
                submission_timestamp=datetime(2024, 1, 15, 10, 0, 0),
            ),
            Exception("Simulated extraction error"),
            SubmitEventData(
                visit_metadata=VisitMetadata(
                    ptid="110003",
                    date="2024-01-17",
                    visitnum="003",
                    module="UDS",
                    packet="z1x",
                ),
                submission_timestamp=datetime(2024, 1, 17, 10, 0, 0),
            ),
        ]

        stats = scraper.scrape_events()

        # Should process 2 files successfully despite 1 error
        assert stats.files_processed == 2
        assert stats.errors_encountered == 1
        # Should still create events for successful files
        assert stats.submission_events_created == 2
        # Should not create QC events
        assert stats.pass_qc_events_created == 0


def test_scrape_events_extraction_failure(mock_project):
    """Test handling of extraction failures (returns None)."""
    scraper = EventScraper(mock_project, dry_run=True)

    # Mock extract_event_from_log to return None for all files
    with patch(
        "transactional_event_scraper_app.event_scraper.extract_event_from_log"
    ) as mock_extract:
        mock_extract.return_value = None

        stats = scraper.scrape_events()

        # Should skip all files due to extraction failure
        assert stats.files_processed == 0
        assert stats.skipped_files == 3
        assert stats.submission_events_created == 0
        assert stats.pass_qc_events_created == 0


def test_scrape_events_empty_project():
    """Test scraping events from project with no log files."""
    empty_project = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
        files=[],
    )

    scraper = EventScraper(empty_project, dry_run=True)
    stats = scraper.scrape_events()

    assert stats.files_processed == 0
    assert stats.submission_events_created == 0
    assert stats.pass_qc_events_created == 0
    assert stats.skipped_files == 0
    assert stats.errors_encountered == 0


def test_scrape_events_event_creation_failure(mock_project, mock_event_capture):
    """Test handling when event creation fails."""
    scraper = EventScraper(mock_project, event_capture=mock_event_capture)

    # Mock event generator to return None for all events
    with (
        patch.object(
            scraper._event_generator,  # noqa: SLF001
            "create_submission_event",
            return_value=None,
        ),
        patch.object(
            scraper._event_generator,  # noqa: SLF001
            "create_qc_event",
            return_value=None,
        ),
    ):
        stats = scraper.scrape_events()

        # Should process files but create no events
        assert stats.files_processed == 3
        assert stats.submission_events_created == 0
        assert stats.pass_qc_events_created == 0
        # Should not call capture_event if no events created
        assert mock_event_capture.capture_event.call_count == 0


def test_scrape_events_capture_failure(mock_project, mock_event_capture):
    """Test handling when event capture fails."""
    # Make capture_event raise an exception
    mock_event_capture.capture_event.side_effect = Exception("S3 write failed")

    scraper = EventScraper(mock_project, event_capture=mock_event_capture)
    stats = scraper.scrape_events()

    # Should encounter errors but continue processing
    assert stats.errors_encountered > 0
    # Some files may have been processed before errors
    assert stats.files_processed >= 0


def test_scrape_events_logs_summary(mock_project, caplog):
    """Test that scraper logs summary statistics."""
    import logging

    caplog.set_level(logging.INFO)

    scraper = EventScraper(mock_project, dry_run=True)
    stats = scraper.scrape_events()

    # Check that summary was logged
    assert "Processing complete" in caplog.text
    assert f"{stats.files_processed} files processed" in caplog.text
    assert f"{stats.submission_events_created} submission events" in caplog.text
    assert f"{stats.pass_qc_events_created} pass-qc events" in caplog.text
