"""Tests for session timestamp handling in
SubjectAdaptor.upload_acquisition_file."""

import logging
from datetime import datetime
from unittest.mock import Mock, patch

import pytz
from flywheel.rest import ApiException
from flywheel_adaptor.subject_adaptor import SubjectAdaptor

SESSION_LABEL = "FORMS-VISIT-2"
VISIT_TIMESTAMP = datetime(2024, 3, 15, 12, 0, tzinfo=pytz.utc)
OTHER_TIMESTAMP = datetime(2024, 3, 14, 12, 0, tzinfo=pytz.utc)


def create_session(*, timestamp=None, has_acquisition=True):
    """Creates a mock session container."""
    session = Mock()
    session.timestamp = timestamp
    session.acquisitions.find_first.return_value = Mock() if has_acquisition else None
    return session


def create_subject(*, session=None, new_session=None):
    """Creates a mock subject whose session lookup returns `session`."""
    subject = Mock()
    subject.label = "110001"
    subject.sessions.find_first.return_value = session
    subject.add_session.return_value = (
        new_session if new_session is not None else create_session()
    )
    return subject


def upload(subject, timestamp=VISIT_TIMESTAMP):
    """Runs upload_acquisition_file with the file upload itself stubbed out."""
    with patch("flywheel_adaptor.subject_adaptor.upload_to_acquisition") as mock_upload:
        mock_upload.return_value = "file-entry"
        return SubjectAdaptor(subject).upload_acquisition_file(
            session_label=SESSION_LABEL,
            acquisition_label="UDS",
            filename="110001_2024-03-15_2_UDS.json",
            contents="{}",
            content_type="application/json",
            session_timestamp=timestamp,
        )


class TestNewSession:
    def test_timestamp_set_on_creation(self):
        """A new session carries the visit timestamp and its timezone."""
        subject = create_subject()

        assert upload(subject) == "file-entry"

        subject.add_session.assert_called_once_with(
            label=SESSION_LABEL, timestamp=VISIT_TIMESTAMP, timezone="UTC"
        )

    def test_no_timestamp_passes_label_only(self):
        """Callers that supply no timestamp keep the original call shape.

        Regression guard for the enrollment path, which shares this
        method.
        """
        subject = create_subject()

        assert upload(subject, timestamp=None) == "file-entry"

        subject.add_session.assert_called_once_with(label=SESSION_LABEL)


class TestExistingSession:
    def test_missing_timestamp_set(self):
        """A session created before timestamps were set gets one."""
        session = create_session(timestamp=None)
        subject = create_subject(session=session)

        assert upload(subject) == "file-entry"

        subject.add_session.assert_not_called()
        session.update.assert_called_once_with(
            {"timestamp": VISIT_TIMESTAMP, "timezone": "UTC"}
        )

    def test_existing_timestamp_not_overwritten(self):
        """An existing timestamp is left as is.

        The visit date cannot change for an existing session without the
        session being deleted first.
        """
        session = create_session(timestamp=OTHER_TIMESTAMP)
        subject = create_subject(session=session)

        assert upload(subject) == "file-entry"

        session.update.assert_not_called()

    def test_no_timestamp_leaves_session_alone(self):
        """Without a timestamp to set, an existing session is not touched."""
        session = create_session(timestamp=None)
        subject = create_subject(session=session)

        assert upload(subject, timestamp=None) == "file-entry"

        session.update.assert_not_called()

    def test_update_failure_does_not_fail_upload(self, caplog):
        """The timestamp is supplementary, a failure to set it is only
        logged."""
        session = create_session(timestamp=None)
        session.update.side_effect = ApiException(status=500, reason="error")
        subject = create_subject(session=session)

        with caplog.at_level(logging.WARNING):
            assert upload(subject) == "file-entry"

        assert "Failed to set the timestamp for session" in caplog.text


class TestAcquisitionUnaffected:
    def test_existing_acquisition_reused(self):
        """Setting a session timestamp does not disturb acquisition lookup."""
        session = create_session(timestamp=VISIT_TIMESTAMP)
        subject = create_subject(session=session)

        upload(subject)

        session.add_acquisition.assert_not_called()

    def test_missing_acquisition_created_without_timestamp(self):
        """Acquisitions are still created with a label only."""
        session = create_session(timestamp=VISIT_TIMESTAMP, has_acquisition=False)
        subject = create_subject(session=session)

        upload(subject)

        session.add_acquisition.assert_called_once_with(label="UDS")
