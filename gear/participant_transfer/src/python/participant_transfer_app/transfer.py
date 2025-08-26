"""Module for processing a participant transfer."""

from typing import Optional

from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import EnrollmentRecord, TransferRecord
from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository


class TransferProcessor:
    """This class process a participant transfer request.

    - Updates identifiers database
    - Adds the subject to enrollment project
    - Soft link participant data from previous center to new center
    """

    def __init__(
        self,
        *,
        transfer_record: TransferRecord,
        enroll_project: EnrollmentProject,
        identifiers_repo: IdentifiersLambdaRepository,
    ) -> None:
        """Initialize the Transfer Processor."""
        self.__transfer_record = transfer_record
        self.__enroll_project = enroll_project
        self.__identifiers_repo = identifiers_repo

    def update_identifiers_database(self) -> Optional[EnrollmentRecord]:
        return None
