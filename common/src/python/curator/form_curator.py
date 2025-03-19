import logging
from abc import abstractmethod
from typing import Optional

from dates.dates import get_localized_timestamp
from files.form import Form
from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.session import Session
from flywheel.models.subject import Subject
from flywheel_gear_toolkit.utils.curator import Curator

log = logging.getLogger(__name__)


class FormCurator(Curator):
    """Curator for form files."""

    def __init__(self, sdk_client: Optional[Client] = None) -> None:
        super().__init__()  # type: ignore
        self.__sdk_client = sdk_client
        self.__file_entry: Optional[FileEntry] = None

    def set_file_entry(self, file_entry: Optional[FileEntry]) -> None:
        self.__file_entry = file_entry

    def get_file_entry(self) -> Optional[FileEntry]:
        return self.__file_entry

    @abstractmethod
    def get_form(self) -> Optional[Form]:
        """Returns the form for the file entry."""
        return None

    def curate_container(self, file_id: str):
        assert self.__sdk_client
        file_entry = self.__sdk_client.get_file(file_id)
        log.info('curating container %s', file_entry.id)
        self.set_file_entry(file_entry)
        self.curate_file(file_entry)
        subject = self.get_subject(file_entry)
        self.curate_subject(subject)
        self.set_file_entry(None)

    def curate_file(self, file_entry: FileEntry):
        """Curate form data.

        Args:
          file_: JSON data for file
        """
        form = self.get_form()
        if not form:
            return

        self.curate_form(form)

    @abstractmethod
    def curate_form(self, form: Form):
        """Curates data for the form.

        Args:
          file_entry: the file entry for the form
        """
        pass

    @abstractmethod
    def curate_subject(self, subject: Subject):
        """Curates data for the subject.

        Args:
          file_entry: the file entry for the form
        """
        pass

    # commenting this out since it's not used anywhere
    # can't use the gear context object in curator since it's not picklable
    # doesn't work with multiprocessing

    # def get_file(self, file_object: Dict[str, Any]) -> FileEntry:
    #     """Get the file entry for the file object.

    #     Args:
    #       file_object: JSON data for file
    #     Returns:
    #       the file entry for the file described
    #     """
    #     file_hierarchy = file_object.get("hierarchy")
    #     assert file_hierarchy
    #     acquisition = self.context.get_container_from_ref(file_hierarchy)
    #     assert isinstance(acquisition, Acquisition)

    #     filename = self.context.get_input_filename("file-input")
    #     return acquisition.get_file(filename)

    def get_session(self, file_entry: FileEntry) -> Session:
        """Get the session for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Session for the file entry
        """

        assert self.__sdk_client
        parents_session = file_entry.parents.get("session")
        return self.__sdk_client.get_session(parents_session)

    def get_subject(self, file_entry: FileEntry) -> Subject:
        """Get the subject for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Subject for the file entry
        """

        assert self.__sdk_client
        parents_subject = file_entry.parents.get("subject")
        return self.__sdk_client.get_subject(parents_subject)


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
