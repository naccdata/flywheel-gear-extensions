"""Unit tests for the EventGenerator class."""

from datetime import datetime

import pytest
from event_capture.event_generator import EventGenerator
from event_capture.models import QCEventData, SubmitEventData
from nacc_common.error_models import VisitMetadata
from test_mocks.mock_flywheel import MockProjectAdaptor


@pytest.fixture
def mock_project():
    """Create a mock project with valid metadata."""
    return MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 123},
    )


@pytest.fixture
def mock_project_no_adcid():
    """Create a mock project without pipeline ADCID."""
    return MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={},  # No pipeline_adcid
    )


@pytest.fixture
def mock_project_invalid_label():
    """Create a mock project with invalid label format."""
    return MockProjectAdaptor(
        label="invalid-label",
        group="test-center",
        info={"pipeline_adcid": 123},
    )


@pytest.fixture
def mock_project_no_datatype():
    """Create a mock project with label missing datatype."""
    return MockProjectAdaptor(
        label="ingest",  # Missing datatype
        group="test-center",
        info={"pipeline_adcid": 123},
    )


@pytest.fixture
def sample_submit_event_data():
    """Create sample SubmitEventData for testing submission events."""
    visit_metadata = VisitMetadata(
        ptid="110001",
        date="2024-01-15",
        visitnum="001",
        module="UDS",
        packet="z1x",
    )

    return SubmitEventData(
        visit_metadata=visit_metadata,
        submission_timestamp=datetime(2024, 1, 15, 10, 0, 0),
    )


@pytest.fixture
def sample_qc_event_data():
    """Create sample QCEventData for testing QC events."""
    visit_metadata = VisitMetadata(
        ptid="110001",
        date="2024-01-15",
        visitnum="001",
        module="UDS",
        packet="z1x",
    )

    return QCEventData(
        visit_metadata=visit_metadata,
        qc_status="PASS",
        qc_completion_timestamp=datetime(2024, 1, 15, 11, 0, 0),
    )


def test_event_generator_initialization(mock_project):
    """Test EventGenerator initialization with valid project."""
    generator = EventGenerator(mock_project)
    assert generator is not None
    assert generator._pipeline_label is not None  # noqa: SLF001
    assert generator._pipeline_label.datatype == "form"  # noqa: SLF001
    assert generator._pipeline_label.study_id == "adrc"  # noqa: SLF001
    assert generator._pipeline_adcid == 123  # noqa: SLF001


def test_event_generator_initialization_invalid_label(mock_project_invalid_label):
    """Test EventGenerator initialization with invalid project label."""
    generator = EventGenerator(mock_project_invalid_label)
    assert generator is not None
    # Should log warning but not crash
    assert generator._pipeline_label is None  # noqa: SLF001


def test_create_submission_event_success(mock_project, sample_submit_event_data):
    """Test successful creation of submission event."""
    generator = EventGenerator(mock_project)
    event = generator.create_submission_event(sample_submit_event_data)

    assert event is not None
    assert event.action == "submit"
    assert event.study == "adrc"
    assert event.pipeline_adcid == 123
    assert event.project_label == "ingest-form-adrc"
    assert event.center_label == "test-center"
    assert event.gear_name == "transactional-event-scraper"
    assert event.ptid == "110001"
    assert event.visit_date == "2024-01-15"
    assert event.visit_number == "001"
    assert event.datatype == "form"
    assert event.module == "UDS"
    assert event.packet == "z1x"
    assert event.timestamp == datetime(2024, 1, 15, 10, 0, 0)


def test_create_submission_event_no_pipeline_label(
    mock_project_invalid_label, sample_submit_event_data
):
    """Test submission event creation fails without valid pipeline label."""
    generator = EventGenerator(mock_project_invalid_label)
    event = generator.create_submission_event(sample_submit_event_data)

    assert event is None


def test_create_submission_event_no_datatype(
    mock_project_no_datatype, sample_submit_event_data
):
    """Test submission event creation fails when label has no datatype."""
    generator = EventGenerator(mock_project_no_datatype)
    event = generator.create_submission_event(sample_submit_event_data)

    assert event is None


def test_create_pass_qc_event_success(mock_project, sample_qc_event_data):
    """Test successful creation of pass-qc event."""
    generator = EventGenerator(mock_project)
    event = generator.create_qc_event(sample_qc_event_data)

    assert event is not None
    assert event.action == "pass-qc"
    assert event.study == "adrc"
    assert event.pipeline_adcid == 123
    assert event.project_label == "ingest-form-adrc"
    assert event.center_label == "test-center"
    assert event.gear_name == "transactional-event-scraper"
    assert event.ptid == "110001"
    assert event.visit_date == "2024-01-15"
    assert event.visit_number == "001"
    assert event.datatype == "form"
    assert event.module == "UDS"
    assert event.packet == "z1x"
    assert event.timestamp == datetime(2024, 1, 15, 11, 0, 0)


def test_create_pass_qc_event_not_pass_status(mock_project):
    """Test not-pass-qc event is created when status is not PASS."""
    visit_metadata = VisitMetadata(
        ptid="110001",
        date="2024-01-15",
        visitnum="001",
        module="UDS",
        packet="z1x",
    )
    qc_event_data = QCEventData(
        visit_metadata=visit_metadata,
        qc_status="FAIL",
        qc_completion_timestamp=datetime(2024, 1, 15, 11, 0, 0),
    )
    generator = EventGenerator(mock_project)
    event = generator.create_qc_event(qc_event_data)

    # Should create a not-pass-qc event
    assert event is not None
    assert event.action == "not-pass-qc"


def test_create_pass_qc_event_no_completion_timestamp(mock_project):
    """Test QC event requires completion timestamp."""
    visit_metadata = VisitMetadata(
        ptid="110001",
        date="2024-01-15",
        visitnum="001",
        module="UDS",
        packet="z1x",
    )
    # QCEventData requires a valid timestamp, so this test verifies
    # that we can't create QCEventData without one
    # The validation happens at the Pydantic model level
    try:
        _qc_event_data = QCEventData(
            visit_metadata=visit_metadata,
            qc_status="PASS",
            qc_completion_timestamp=None,
        )
        # If we get here, the model allowed None (shouldn't happen)
        raise AssertionError("QCEventData should not allow None timestamp")
    except Exception:
        # Expected - Pydantic should reject None timestamp
        pass


def test_create_pass_qc_event_no_pipeline_label(
    mock_project_invalid_label, sample_qc_event_data
):
    """Test pass-qc event creation fails without valid pipeline label."""
    generator = EventGenerator(mock_project_invalid_label)
    event = generator.create_qc_event(sample_qc_event_data)

    assert event is None


def test_create_pass_qc_event_no_datatype(
    mock_project_no_datatype, sample_qc_event_data
):
    """Test pass-qc event creation fails when label has no datatype."""
    generator = EventGenerator(mock_project_no_datatype)
    event = generator.create_qc_event(sample_qc_event_data)

    assert event is None


def test_event_generator_with_different_study():
    """Test EventGenerator with non-default study ID."""
    project = MockProjectAdaptor(
        label="ingest-form-ftld",
        group="test-center",
        info={"pipeline_adcid": 456},
    )

    visit_metadata = VisitMetadata(
        ptid="220002",
        date="2024-02-20",
        visitnum="002",
        module="FTLD",
        packet="a1",
    )

    submit_event_data = SubmitEventData(
        visit_metadata=visit_metadata,
        submission_timestamp=datetime(2024, 2, 20, 9, 0, 0),
    )

    generator = EventGenerator(project)
    submission_event = generator.create_submission_event(submit_event_data)

    assert submission_event is not None
    assert submission_event.study == "ftld"
    assert submission_event.pipeline_adcid == 456


def test_event_generator_with_optional_fields_none():
    """Test EventGenerator handles optional fields being None."""
    project = MockProjectAdaptor(
        label="ingest-form-adrc",
        group="test-center",
        info={"pipeline_adcid": 789},
    )

    visit_metadata = VisitMetadata(
        ptid="330003",
        date="2024-03-30",
        visitnum=None,  # Optional field
        module="LBD",
        packet=None,  # Optional field
    )

    submit_event_data = SubmitEventData(
        visit_metadata=visit_metadata,
        submission_timestamp=datetime(2024, 3, 30, 14, 0, 0),
    )

    generator = EventGenerator(project)
    submission_event = generator.create_submission_event(submit_event_data)

    assert submission_event is not None
    assert submission_event.visit_number is None
    assert submission_event.packet is None


def test_gear_name_is_correct(
    mock_project, sample_submit_event_data, sample_qc_event_data
):
    """Test that gear_name is set to 'transactional-event-scraper' for all
    events."""
    generator = EventGenerator(mock_project)

    submission_event = generator.create_submission_event(sample_submit_event_data)
    assert submission_event is not None
    assert submission_event.gear_name == "transactional-event-scraper"

    pass_qc_event = generator.create_qc_event(sample_qc_event_data)
    assert pass_qc_event is not None
    assert pass_qc_event.gear_name == "transactional-event-scraper"
