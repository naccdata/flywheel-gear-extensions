"""Pydantic models to help with scheduling and curation."""

import re
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from pydantic import BaseModel, field_validator

VISIT_PATTERN = re.compile(
    r"^"
    r"(?P<pass2>.+("
    r"_CLS|_CSF|_NP|_MDS|_MLST|_MEDS|_FTLD|_LBD|"
    r"apoe_genotype|NCRAD-SAMPLES.+|niagads_availability|"
    r"SCAN-MR-QC.+|SCAN-MR-SBM.+|"
    r"SCAN-PET-QC.+|SCAN-AMYLOID-PET-GAAIN.+|SCAN-AMYLOID-PET-NPDKA.+|"
    r"SCAN-FDG-PET-NPDKA.+|SCAN-TAU-PET-NPDKA.+"
    r")\.json)|"
    r"(?P<pass1>.+(_UDS)\.json)|"
    r"(?P<pass0>.+(MRI-SUMMARY-DATA.+\.json|"
    r"\.dicom\.zip|\.nii\.gz))"
    r"$"
)


class FileModel(BaseModel):
    """Defines data model for columns returned from the project form curator
    data model.

    Objects are ordered by order date.
    """

    filename: str
    file_id: str
    acquisition_id: str
    subject_id: str
    modified_date: date
    visit_date: Optional[date]
    study_date: Optional[date]
    scan_date: Optional[date]
    scandate: Optional[date]
    scandt: Optional[date]
    img_study_date: Optional[date]

    @property
    def visit_pass(self) -> Optional[Literal["pass0", "pass1", "pass2", "pass3"]]:
        """Returns the "pass" for the file; determining when the relative order
        of when the file should be visited.

        Passes are based on the dependency of attributes over the files.
        The pass is determined by matching the file with a regular expression.

        Order of curation is indicated by inverse lexicographical ordering on
        the pass name.
        This is done to avoid having to maintain the total ordering without
        having to rename the pass if more constraints are added.

        As it is, imaging data must be curated last (as it relies on all UDS visits
        being known/curated), then UDS, then every other file.
        Historical APOE must be curated before the NCRAD APOE.
        As such, there are currently 4 pass categories.
        """
        # need to handle historic apoe separately as it does not work well with regex
        if "historic_apoe_genotype" in self.filename:
            return "pass3"

        match = VISIT_PATTERN.match(self.filename)
        if not match:
            return None

        groups = match.groupdict()
        names = {key for key in groups if groups.get(key) is not None}
        if len(names) != 1:
            raise ValueError(f"error matching file name {self.filename}")

        return names.pop()  # type: ignore

    @property
    def order_date(self) -> date:
        """Returns the date to be used for ordering this file.

        Checks for form visit date, then scan date, and then file modification date.

        Returns:
          the date to be used to compare this file for ordering
        """
        if self.visit_date:
            return self.visit_date
        if self.study_date:
            return self.study_date
        if self.scan_date:
            return self.scan_date
        if self.scandate:
            return self.scandate
        if self.scandt:
            return self.scandt
        if self.img_study_date:
            return self.img_study_date
        if self.modified_date:
            return self.modified_date

        raise ValueError(f"file {self.filename} {self.file_id} has no associated date")

    def __eq__(self, other) -> bool:
        if not isinstance(other, FileModel):
            return False

        return self.file_id == other.file_id

    def __lt__(self, other) -> bool:
        """Order the objects by order class and date.

        First, use inverse order on order-class: if the class is greater
        than, the object is less than. Second, order by date.
        """
        if not isinstance(other, FileModel):
            return False
        if not self.visit_pass or not other.visit_pass:
            raise ValueError(
                f"Cannot compare values {self.visit_pass} with {other.visit_pass}"
            )

        # Note: this inverts the order on the order_class
        if self.visit_pass > other.visit_pass:
            return True
        if self.visit_pass < other.visit_pass:
            return False

        return self.order_date < other.order_date

    @field_validator(
        "modified_date",
        "visit_date",
        "study_date",
        "scan_date",
        "scandate",
        "scandt",
        "img_study_date",
        mode="before",
    )
    def datetime_to_date(cls, value: Optional[date | str]) -> Optional[date | str]:
        if not value:
            return None

        if isinstance(value, date):
            return value

        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass

        return value


class ViewResponseModel(BaseModel):
    """Defines the data model for a dataview response."""

    data: List[FileModel]

    @field_validator("data", mode="before")
    def trim_data(cls, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove any rows that are completely empty, which can happen if the
        filename pattern does not match.

        Args:
            data: List of retrieved rows from the builder
        Returns:
            Trimmed data
        """
        return [row for row in data if any(x is not None for x in row.values())]


class ProcessedFile(BaseModel):
    """Defines model for a processed file.

    Keeps track of the minimal file info needed to interact with FW and
    curated file info (if successfully curated)
    """

    # unfortunately FW objects are not serializable so we cannot use FileEntry directly
    # minimally store name, file_id, and tags instead
    name: str
    file_id: str
    tags: Optional[List[str]] = None
    scope: Optional[str]
    file_info: Optional[Dict[str, Any]] = None


def generate_curation_failure(
    container: Subject | FileEntry, reason: str
) -> Dict[str, str]:
    """Creates a curation failure dict from either a subject or file."""
    return {"name": container.name, "id": container.id, "reason": reason}  # type: ignore
