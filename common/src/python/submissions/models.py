"""Data models for form data upload requests."""

from typing import Any, Dict, List, Optional

from nacc_common.field_names import FieldNames
from nacc_common.form_dates import DATE_PATTERN
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from serialization.case import kebab_case


class VisitInfo(BaseModel):
    """Class to represent file information for a participant visit."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    filename: str
    file_id: Optional[str] = None  # Flywheel File ID
    visitdate: str = Field(pattern=DATE_PATTERN)
    visitnum: Optional[str] = None
    validated_timestamp: Optional[str] = None


class ParticipantVisits(BaseModel):
    """Class to represent visits for a given participant for a given module."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    participant: str  # Flywheel subject label
    module: str  # module label (Flywheel acquisition label)
    visits: List[VisitInfo]

    @classmethod
    def create_from_visit_data(
        cls,
        *,
        filename: str,
        file_id: str,
        input_record: Dict[str, Any],
        visitdate_key: str = FieldNames.DATE_COLUMN,
    ) -> "ParticipantVisits":
        """Create from input data and visit file details.

        Args:
            filename: Flywheel acquisition file name
            file_id: Flywheel acquisition file ID
            input_record: input visit data
            visitdate_key: Key to get visitdate from - defaults to `visitdate`

        Returns:
            ParticipantVisits object
        """
        visit_info = VisitInfo(
            filename=filename,
            file_id=file_id,
            visitdate=input_record[visitdate_key],
        )
        return ParticipantVisits(
            participant=input_record[FieldNames.NACCID],
            module=input_record[FieldNames.MODULE].upper(),
            visits=[visit_info],
        )

    def add_visit(self, *, filename: str, file_id: str, visitdate: str):
        """Add a new visit to the list of visits for this participant.

        Args:
            filename: Flywheel acquisition file name
            file_id: Flywheel acquisition file ID
            visitdate: visit date
        """
        visit_info = VisitInfo(filename=filename, file_id=file_id, visitdate=visitdate)
        self.visits.append(visit_info)
