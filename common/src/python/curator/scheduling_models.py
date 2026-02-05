"""Pydantic models to help with scheduling and curation."""

import re
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from data.dataview import ColumnModel, make_builder
from flywheel import DataView
from flywheel.models.subject import Subject
from nacc_attribute_deriver.utils.scope import (
    FormScope,
    ScopeLiterals,
)
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

VISIT_PATTERN = re.compile(
    r"^"
    r"(?P<pass2>.+("
    r"_BDS|_CSF|_NP|_MDS|_MLST|_MEDS|_FTLD|_LBD|"
    r"apoe_genotype|NCRAD-SAMPLES.+|niagads_availability|"
    r"SCAN-MR-QC.+|SCAN-MR-SBM.+|"
    r"SCAN-PET-QC.+|SCAN-AMYLOID-PET-GAAIN.+|SCAN-AMYLOID-PET-NPDKA.+|"
    r"SCAN-FDG-PET-NPDKA.+|SCAN-TAU-PET-NPDKA.+"
    r")\.json)|"
    r"(?P<pass1>.+(_UDS)\.json)|"
    r"(?P<pass0>.+((_CLS|_COVID|MRI-SUMMARY-DATA.+)\.json|"
    r"\.dicom\.zip|\.nii\.gz))"
    r"$"
)

SCOPE_PATTERN = re.compile(
    r"^"
    r"(?P<bds>.+_BDS\.json)|"
    r"(?P<cls>.+_CLS\.json)|"
    r"(?P<csf>.+_CSF\.json)|"
    r"(?P<np>.+_NP\.json)|"
    r"(?P<mds>.+_MDS\.json)|"
    r"(?P<milestone>.+_MLST\.json)|"
    r"(?P<covid>.+_COVID\.json)|"
    r"(?P<apoe>.+apoe_genotype\.json)|"
    r"(?P<ncrad_biosamples>.+NCRAD-SAMPLES.+\.json)|"
    r"(?P<niagads_availability>.+niagads_availability\.json)|"
    r"(?P<scan_mri_qc>.+SCAN-MR-QC.+\.json)|"
    r"(?P<scan_mri_sbm>.+SCAN-MR-SBM.+\.json)|"
    r"(?P<scan_pet_qc>.+SCAN-PET-QC.+\.json)|"
    r"(?P<scan_amyloid_pet_gaain>.+SCAN-AMYLOID-PET-GAAIN.+\.json)|"
    r"(?P<scan_amyloid_pet_npdka>.+SCAN-AMYLOID-PET-NPDKA.+\.json)|"
    r"(?P<scan_fdg_pet_npdka>.+SCAN-FDG-PET-NPDKA.+\.json)|"
    r"(?P<scan_tau_pet_npdka>.+SCAN-TAU-PET-NPDKA.+\.json)|"
    r"(?P<mri_summary>.+MRI-SUMMARY-DATA.+\.json)|"
    r"(?P<mri_dicom>.+MR.+\.dicom\.zip)|"
    r"(?P<mri_nifti>.+MR.+\.nii\.gz)|"
    r"(?P<pet_dicom>.+PET.+\.dicom\.zip)|"
    r"(?P<meds>.+_MEDS\.json)|"
    r"(?P<ftld>.+_FTLD\.json)|"
    r"(?P<lbd>.+_LBD\.json)|"
    r"(?P<uds>.+_UDS\.json)"
    r"$"
)


class FileModel(BaseModel):
    """Defines data model for columns returned from the project form curator
    data model.

    Objects are ordered by order date.
    """

    filename: str
    file_id: str
    file_info: Dict[str, Any]
    file_tags: List[str]
    session_id: str
    modified_date: date

    # determined from file_info
    visitdate: Optional[date] = Field(default=None, init=False)
    study_date: Optional[date] = Field(default=None, init=False)
    scan_date: Optional[date] = Field(default=None, init=False)
    scandate: Optional[date] = Field(default=None, init=False)
    scandt: Optional[date] = Field(default=None, init=False)
    img_study_date: Optional[date] = Field(default=None, init=False)

    # determined from filename
    scope: Optional[ScopeLiterals] = Field(default=None, init=False)

    # updated if there is a corresponding UDS visit with the same session
    uds_visitdate: Optional[date] = Field(default=None, init=False)

    @classmethod
    def __check_date(cls, value: Optional[str | date]) -> Optional[date]:
        if not value:
            return None

        if isinstance(value, date):
            return value

        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass

        return None

    @field_validator("modified_date", mode="before")
    def datetime_to_date(cls, value: str | date) -> date:
        result = cls.__check_date(value)
        if not result:
            raise ValidationError("modified date not found")

        return result

    @model_validator(mode="after")
    def set_dates(self) -> "FileModel":
        """Set the dates that come from file.info."""
        form_data = self.file_info.get("forms", {}).get("json", {})
        raw_data = self.file_info.get("raw", {})
        dicom_data = self.file_info.get("header", {}).get("dicom", {})

        self.visitdate = self.__check_date(form_data.get("visitdate"))
        self.study_date = self.__check_date(raw_data.get("study_date"))
        self.scan_date = self.__check_date(raw_data.get("scan_date"))
        self.scandate = self.__check_date(raw_data.get("scandate"))
        self.scandt = self.__check_date(raw_data.get("scandt"))
        self.img_study_date = self.__check_date(dicom_data.get("StudyDate"))

        return self

    @model_validator(mode="after")
    def determine_scope(self) -> "FileModel":
        """Determine the file's scope."""
        if "historic_apoe_genotype" in self.filename:
            self.scope = "historic_apoe"
            return self

        match = SCOPE_PATTERN.match(self.filename)
        if not match:
            self.scope = None
            return self

        groups = match.groupdict()
        names = {key for key in groups if groups.get(key) is not None}
        if len(names) != 1:
            raise ValidationError(f"error matching file name {self.filename} to scope")

        self.scope = names.pop()  # type: ignore
        return self

    @property
    def visit_pass(self) -> Optional[Literal["pass0", "pass1", "pass2", "pass3"]]:
        """Returns the "pass" for the file; determining when the relative order
        of when the file should be visited.

        Passes are based on the dependency of attributes over the files.
        The pass is determined by matching the file with a regular expression.

        Order of curation is indicated by inverse lexicographical ordering on
        the pass name. This is done to avoid having to maintain the total
        ordering without having to rename the pass if more constraints are added.

        pass3: Historic APOE data (which mainly just needs to be done before
               NCRAD APOE data)
        pass2: All other data
        pass1: UDS data
        pass0: Data that relies on fully curated UDS data
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
        if self.visitdate:
            return self.visitdate
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
        if self.uds_visitdate:
            return self.uds_visitdate
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

    @classmethod
    def create_dataview(cls, filename_patterns: List[str]) -> DataView:
        """Create DataView corresponding to FileModels."""
        builder = make_builder(
            label="Curation DataView",
            description="Curation DataView for FileModels",
            columns=[
                ColumnModel(data_key="file.name", label="filename"),
                ColumnModel(data_key="file.file_id", label="file_id"),
                ColumnModel(data_key="file.tags", label="file_tags"),
                ColumnModel(data_key="file.info", label="file_info"),
                ColumnModel(data_key="file.modified", label="modified_date"),
                ColumnModel(data_key="file.parents.session", label="session_id"),
            ],
            container="acquisition",
            missing_data_strategy="none",
        )
        if filename_patterns:
            builder.file_filter(value="|".join(filename_patterns), regex=True)
            builder.file_container("acquisition")

        return builder.build()


class ViewResponseModel(BaseModel):
    """Defines the data model for a dataview response."""

    data: List[FileModel]
    invalid_visits: Optional[List[FileModel]] = Field(default=None, init=False)

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

    @model_validator(mode="after")
    def sanitize_data(self) -> "ViewResponseModel":
        """Remove duplicates, e.g. two forms with the same visitdate in the
        same scope, which isn't allowed to happen, then link files with a
        corresponding UDS session."""
        counts: Dict[ScopeLiterals, Dict[date, int]] = {}
        uds_sessions: Dict[str, date] = {}

        for file in self.data:
            if file.visitdate:
                scope = file.scope
                visitdate = file.visitdate

                if scope not in counts:
                    counts[scope] = {}

                current_count = counts[scope].get(visitdate, 0)
                counts[scope][visitdate] = current_count + 1

                if scope == FormScope.UDS:
                    uds_sessions[file.session_id] = visitdate

        # collapse to visitdates where count is > 2
        conflicting_visits = {}
        for scope, scope_counts in counts.items():
            conflicting_visits[scope] = [
                visitdate for visitdate, count in scope_counts.items() if count > 1
            ]

        # move any where count > 1 to invalid visits
        filtered_data = []
        for file in self.data:
            if file.visitdate not in conflicting_visits.get(file.scope, []):
                file.uds_visitdate = uds_sessions.get(file.session_id, None)
                filtered_data.append(file)
            else:
                if self.invalid_visits is None:
                    self.invalid_visits = []

                self.invalid_visits.append(file)

        self.data = filtered_data
        return self


def generate_curation_failure(
    container: Subject | FileModel, reason: str
) -> Dict[str, str]:
    """Creates a curation failure dict from either a subject or file."""
    if isinstance(container, FileModel):
        return {"name": container.filename, "id": container.file_id, "reason": reason}

    return {"name": container.label, "id": container.id, "reason": reason}  # type: ignore
