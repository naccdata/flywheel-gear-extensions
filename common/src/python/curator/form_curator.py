import logging
from abc import abstractmethod
from typing import Any, Dict

from dates.dates import get_localized_timestamp
from files.form import Form
from flywheel.models.acquisition import Acquisition
from flywheel.models.file_entry import FileEntry
from flywheel.models.session import Session
from flywheel.models.subject import Subject
from flywheel_gear_toolkit.utils.curator import FileCurator

log = logging.getLogger(__name__)


class FormCurator(FileCurator):
    """Curator for form files."""

    def __init__(self) -> None:
        super().__init__()

    def curate_file(self, file_: Dict[str, Any]):
        """Curate form data.

        Args:
          file_: JSON data for file
        """
        file_entry = self.get_file(file_)
        self.curate_form(file_entry)

    @abstractmethod
    def curate_form(self, file_entry: FileEntry):
        """Curates data for the form.

        Args:
          file_entry: the file entry for the form
        """
        pass

    def get_file(self, file_object: Dict[str, Any]) -> FileEntry:
        """Get the file entry for the file object.

        Args:
          file_object: JSON data for file
        Returns:
          the file entry for the file described
        """
        file_hierarchy = file_object.get("hierarchy")
        assert file_hierarchy
        acquisition = self.context.get_container_from_ref(file_hierarchy)
        assert isinstance(acquisition, Acquisition)

        filename = self.context.get_input_filename("file-input")
        return acquisition.get_file(filename)

    def get_session(self, file_entry: FileEntry) -> Session:
        """Get the session for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Session for the file entry
        """
        client = self.context.client
        assert client
        parents_session = file_entry.parents.get("session")
        return client.get_session(parents_session)

    def get_subject(self, file_entry: FileEntry) -> Subject:
        """Get the subject for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Subject for the file entry
        """
        parents_subject = file_entry.parents.get("subject")
        return self.context.client.get_subject(parents_subject)


def curate_session_timestamp(session: Session, form: Form):
    """Set timestamp attribute for session.

    Args:
        session: the session to curate
        form: the milestone form
    """
    visit_datetime = form.get_form_date()
    if visit_datetime:
        timestamp = get_localized_timestamp(visit_datetime)
        session.update({"timestamp": timestamp})
    else:
        log.warning("Timestamp undetermined for %s", session.label)
