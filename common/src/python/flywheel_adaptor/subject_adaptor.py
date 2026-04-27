"""This is a wrapper class for flywheel Subject class to simplify building
specialized subject wrappers."""

import logging
from typing import Any, Dict, List, Optional

from flywheel.file_spec import FileSpec
from flywheel.finder import Finder
from flywheel.models.file_entry import FileEntry
from flywheel.models.session import Session
from flywheel.models.subject import Subject
from flywheel.models.subject_parents import SubjectParents
from keys.keys import MetadataKeys
from pydantic import ValidationError
from submissions.models import VisitInfo
from uploads.acquisition import upload_to_acquisition
from utils.decorators import api_retry

log = logging.getLogger(__name__)


class SubjectError(Exception):
    """Exception class for errors related Flywheel subject."""


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

        return self.sessions.find_first(f"label={label}")

    def update(self, info: Dict[str, Any]) -> None:
        """Updates the info object for this subject.

        Args:
          info: the info dictionary for update
        """
        self._subject.update(info=info)

    def get_last_failed_visit(self, module: str) -> Optional[VisitInfo]:
        """Returns the last failed visit for this subject for the given module.

        Args:
            module: module label (Flywheel acquisition label)

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
            raise SubjectError(
                "Incomplete failed visit metadata for subject "
                f"{self.label}/{module} - {error}"
            ) from error

    def set_last_failed_visit(self, module: str, failed_visit: VisitInfo):
        """Update last failed visit info for this subject for the given module.

        Args:
            module: module label (Flywheel acquisition label)
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
            module: module label (Flywheel acquisition label)
        """

        # make sure to load the existing metadata first and then modify
        # update_info() will replace everything under the top-level key
        module_info = self.info.get(module, {})
        module_info[MetadataKeys.FAILED] = {}
        updates = {module: module_info}
        # Note: have to use update_info() here for reset to take effect
        # Using update() will not delete any existing data
        self._subject.update_info(updates)

    @api_retry
    def upload_file(self, file_spec: FileSpec) -> Optional[List[Dict]]:
        """Upload a file to this subject.

        Args:
            file_spec: Flywheel file spec

        Returns:
            Optional[List[Dict]]: Information on the flywheel file

        Raises:
            flywheel.rest.ApiException: if any error occurred while upload
        """
        return self._subject.upload_file(file_spec)

    def upload_acquisition_file(
        self,
        *,
        session_label: str,
        acquisition_label: str,
        filename: str,
        contents: str,
        content_type: str,
        skip_duplicates: bool = True,
    ) -> Optional[FileEntry]:
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
            UploaderError: if any error occurred while upload
        """

        session = self.find_session(session_label)
        if not session:
            log.info(
                "Session %s does not exist in subject %s, creating a new session",
                session_label,
                self.label,
            )
            session = self.add_session(session_label)

        acquisition = session.acquisitions.find_first(f"label={acquisition_label}")
        if not acquisition:
            log.info(
                "Acquisition %s does not exist in session %s, "
                "creating a new acquisition",
                acquisition_label,
                session_label,
            )
            acquisition = session.add_acquisition(label=acquisition_label)

        return upload_to_acquisition(
            acquisition=acquisition,
            filename=filename,
            contents=contents,
            content_type=content_type,
            subject_label=self.label,
            session_label=session_label,
            acquisition_label=acquisition_label,
            skip_duplicates=skip_duplicates,
        )

    def get_acquisition_file_name(
        self,
        *,
        session: str,
        acquisition: str,
        extension: Optional[str] = "json",
        connector: Optional[str] = "_",
    ) -> str:
        """Generate filename in desired format.

        Args:
            session_label: Flywheel session label
            acquisition_label: Flywheel acquisition label
            extension (optional): file extension. Defaults to 'json'.
            connector (optional): connecting character, Defaults to '_'

        Returns:
            str: generated filename
        """
        return f"{self.label}{connector}{session}{connector}{acquisition}.{extension}"

    def find_acquisition_file(
        self, *, session_label: str, acquisition_label: str, filename: str
    ) -> Optional[FileEntry]:
        """Find a file matches with given session/acquisition/filename in this
        subject.

        Args:
            session_label: Flywheel session label
            acquisition_label: Flywheel acquisition label
            filename: file name

        Returns:
            FileEntry(optional): Flywheel container for the file or None
        """

        session = self.find_session(session_label)
        if not session:
            return None

        acquisition = session.acquisitions.find_first(f"label={acquisition_label}")
        if not acquisition:
            return None

        return acquisition.get_file(filename)
