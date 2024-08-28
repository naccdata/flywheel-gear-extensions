"""Module for working with an enrollment project for a study within a
center."""

import logging
from typing import List

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from enrollment.enrollment_subject import EnrollmentSubject
from enrollment.enrollment_transfer import EnrollmentError, TransferRecord

log = logging.getLogger(__name__)


class TransferInfo(BaseModel):
    """Wrapper class for a list of transfer records."""

    transfers: List[TransferRecord]

    def add(self, record: TransferRecord) -> None:
        """Adds the record to the list of transfers.

        Args:
          record: the transfer record
        """
        self.transfers = self.transfers if self.transfers else []
        self.transfers.append(record)

    def merge(self, transfer_info: 'TransferInfo') -> None:
        """Merges the records into this object."""
        # TODO: decide if OK to have duplicates
        for record in transfer_info.transfers:
            self.transfers.append(record)


class EnrollmentProject(ProjectAdaptor):
    """Defines an adaptor for a project representing study enrollment within a
    center."""

    @classmethod
    def create_from(cls, project: ProjectAdaptor) -> 'EnrollmentProject':
        """Converts the project adaptor to an enrollment project.

        Args:
          project: the project adaptor
        Returns:
          the enrollment project
        """
        # pylint: disable=protected-access
        return EnrollmentProject(project=project._project, proxy=project._fw)

    def get_transfer_info(self) -> TransferInfo:
        """Gets the transfer info object for this project.

        Creates a new one if none exists.

        Returns:
          the transfer info object
        """
        info = self.get_info()
        if not info:
            return TransferInfo(transfers=[])
        if 'transfers' not in info:
            return TransferInfo(transfers=[])

        try:
            return TransferInfo.model_validate(info)
        except ValidationError as error:
            raise EnrollmentError(f"Info in {self.group}/{self.label}"
                                  " does not match expected format") from error

    def update_transfer_info(self, transfer_info: TransferInfo) -> None:
        """Updates the transfer information for this project.

        Args:
          transfer_info: the transfer records for this project
        """
        self.update_info(
            transfer_info.model_dump(by_alias=True, exclude_none=True))

    def add_transfers(self, transfers: TransferInfo) -> None:
        """Adds the transfers in the info object to this project.

        Args:
          transfers: the transfer info object
        """
        transfer_info = self.get_transfer_info()
        transfer_info.merge(transfers)
        self.update_transfer_info(transfer_info)

    @override
    def add_subject(self, label: str) -> EnrollmentSubject:
        """Adds an enrollment subject to this project.

        Args:
          label: the subject label
        Returns:
          the new subject
        """
        return EnrollmentSubject.create_from(
            subject=super().add_subject(label))
