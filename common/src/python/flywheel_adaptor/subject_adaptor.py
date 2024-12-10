"""This is a wrapper class for flywheel Subject class to simplify building
specialized subject wrappers."""

import logging
from typing import Any, Dict, List, Optional

from dates.form_dates import DATE_PATTERN
from flywheel.file_spec import FileSpec
from flywheel.finder import Finder
from flywheel.models.file_entry import FileEntry
from flywheel.models.session import Session
from flywheel.models.subject import Subject
from flywheel.models.subject_parents import SubjectParents
from flywheel.rest import ApiException
from keys.keys import FieldNames, MetadataKeys
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field, ValidationError
from serialization.case import kebab_case
from utils.utils import is_duplicate_record

log = logging.getLogger(__name__)


class SubjectError(Exception):
    """Exception class for errors related Flywheel subject."""


class VisitInfo(BaseModel):
    """Class to represent file information for a particpant visit."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))

    filename: str
    file_id: Optional[str] = None  # Flywheel File ID
    visitdate: str = Field(pattern=DATE_PATTERN)


class ParticipantVisits(BaseModel):
    """Class to represent visits for a given participant for a given module."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))

    participant: str  # Flywheel subject label
    module: str  # module label (Flywheel aquisition label)
    visits: List[VisitInfo]

    @classmethod
    def create_from_visit_data(
            cls, *, filename: str, file_id: str,
            input_record: Dict[str, Any]) -> "ParticipantVisits":
        """Create from input data and visit file details.

        Args:
            filename: Flywheel aquisition file name
            file_id: Flywheel aquisition file ID
            input_record: input visit data

        Returns:
            ParticipantVisits object
        """
        visit_info = VisitInfo(filename=filename,
                               file_id=file_id,
                               visitdate=input_record[FieldNames.DATE_COLUMN])
        return ParticipantVisits(
            participant=input_record[FieldNames.NACCID],
            module=input_record[FieldNames.MODULE].upper(),
            visits=[visit_info])

    def add_visit(self, *, filename: str, file_id: str, visitdate: str):
        """Add a new visit to the list of visits for this participant.

        Args:
            filename: Flywheel aquisition file name
            file_id: Flywheel aquisition file ID
            visitdate: visit date
        """
        visit_info = VisitInfo(filename=filename,
                               file_id=file_id,
                               visitdate=visitdate)
        self.visits.append(visit_info)


class SubjectAdaptor:
    """Base wrapper class for flywheel subject."""

    def __init__(self, subject: Subject) -> None:
        self._subject = subject

    @property
    def info(self) -> Dict[str, Any]:
        """Returns the info object for this subject."""
        self._subject = self._subject.reload()
        return self._subject.info

    @property
    def label(self) -> str:
        """Returns the label for this subject."""
        return self._subject.label

    @property
    def sessions(self) -> Finder:
        """Returns the finder object for the sessions of this subject."""
        return self._subject.sessions

    @property
    def subject(self) -> Subject:
        """Returns the subject object."""
        return self._subject

    @property
    def id(self) -> str:
        """Returns the ID for this subject."""
        return self._subject.id

    @property
    def parents(self) -> SubjectParents:
        """Returns parents for this subject."""
        return self._subject.parents

    def add_session(self, label: str) -> Session:
        """Adds and returns a new session for this subject.

        Args:
          label: the label for the session
        Returns:
          the added session
        """
        return self._subject.add_session(label=label)

    def find_session(self, label: str) -> Optional[Session]:
        """Finds the session with specified label.

        Args:
          label: the label for the session

        Returns:
          Session container or None
        """

        return self.sessions.find_first(f'label={label}')

    def update(self, info: Dict[str, Any]) -> None:
        """Updates the info object for this subject.

        Args:
          info: the info dictionary for update
        """
        self._subject.update(info=info)

    def get_last_failed_visit(self, module: str) -> Optional[VisitInfo]:
        """Returns the last failed visit for this subject for the given module.

        Args:
            module: module label (Flywheel aquisition label)

        Returns:
            Optional[VisitInfo]: Last failed visit if exists

         Raises:
          SubjectError if required metadata is missing
        """

        module_info = self.info.get(module, {})
        last_failed = module_info.get(MetadataKeys.FAILED, None)
        if not last_failed:
            return None

        try:
            return VisitInfo.model_validate(last_failed)
        except ValidationError as error:
            raise SubjectError('Incomplete failed visit metadata for subject '
                               f'{self.label}/{module} - {error}') from error

    def set_last_failed_visit(self, module: str, failed_visit: VisitInfo):
        """Update last failed visit info for this subject for the given module.

        Args:
            module: module label (Flywheel aquisition label)
            failed_visit: failed visit info
        """

        # make sure to load the existing metadata first and then modify
        # update_info() will replace everything under the top-level key
        module_info = self.info.get(module, {})
        module_info[MetadataKeys.FAILED] = failed_visit.model_dump()
        updates = {module: module_info}
        self._subject.update_info(updates)

    def reset_last_failed_visit(self, module: str):
        """Reset last failed visit info for this subject for the given module.

        Args:
            module: module label (Flywheel aquisition label)
        """

        # make sure to load the existing metadata first and then modify
        # update_info() will replace everything under the top-level key
        module_info = self.info.get(module, {})
        module_info[MetadataKeys.FAILED] = {}
        updates = {module: module_info}
        # Note: have to use update_info() here for reset to take effect
        # Using update() will not delete any exsisting data
        self._subject.update_info(updates)

    def upload_file(self, file_spec: FileSpec) -> Optional[List[Dict]]:
        """Upload a file to this subject.

        Args:
            file_spec: Flywheel file spec

        Returns:
            Optional[List[Dict]]: Information on the flywheel file

        Raises:
            SubjectError: if any error occurred while upload
        """
        try:
            return self._subject.upload_file(file_spec)
        except ApiException as error:
            raise SubjectError(
                f'Failed to upload file {file_spec.name} to {self.label} - {error}'
            ) from error

    def upload_acquisition_file(
            self,
            *,
            session_label: str,
            acquisition_label: str,
            filename: str,
            contents: str,
            content_type: str,
            skip_duplicates: bool = True) -> Optional[FileEntry]:
        """Uploads a file to a given session/acquisition in this subject.
        Creates new containers if session/acquisition does not exist.

        Args:
            session_label: Flywheel session label
            acquisition_label: Flywheel acquisition label
            filename: file name
            contents: file contents
            content_type: contents type
            skip_duplicates: whether to skip upload if a duplicate file already exists

        Returns:
            FileEntry(optional): Flywheel container for the newly uploaded file or None

        Raises:
            SubjectError: if any error occurred while upload
        """

        session = self.find_session(session_label)
        if not session:
            log.info(
                'Session %s does not exist in subject %s, creating a new session',
                session_label, self.label)
            session = self.add_session(session_label)

        acquisition = session.acquisitions.find_first(
            f'label={acquisition_label}')
        if not acquisition:
            log.info(
                'Acquisition %s does not exist in session %s, '
                'creating a new acquisition', acquisition_label, session_label)
            acquisition = session.add_acquisition(label=acquisition_label)

        if skip_duplicates:
            existing_file = acquisition.get_file(filename)
            if existing_file and is_duplicate_record(
                    contents, existing_file.read(), content_type):
                log.warning('Duplicate file %s already exists at %s/%s/%s',
                            filename, self.label, session_label,
                            acquisition_label)
                return None

        record_file_spec = FileSpec(name=filename,
                                    contents=contents,
                                    content_type=content_type)

        try:
            acquisition.upload_file(record_file_spec)
            acquisition = acquisition.reload()
            return acquisition.get_file(filename)
        except ApiException as error:
            raise SubjectError(
                f'Failed to upload file {filename} to '
                '{self.label}/{session_label}/{acquisition_label}: {error}'
            ) from error
