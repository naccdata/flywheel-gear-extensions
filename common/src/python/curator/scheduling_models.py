"""Pydantic models to help with scheduling and curation."""

import re
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from data.dataview import ColumnModel, make_builder
from flywheel import DataView
from nacc_attribute_deriver.utils.scope import (
    FormScope,
    ScopeLiterals,
)
from pydantic import (
    BaseModel,
    PrivateAttr,
    field_validator,
    model_validator,
)

ALL_FORM_SCOPES = frozenset(e.value for e in FormScope)
VISIT_PASS_LITERALS = Literal["pass0", "pass1", "pass2", "pass3"]

VISIT_PATTERN = re.compile(
    r"^"
    r"(?P<pass2>.+("
    r"_BDS|_CSF|_NP|_MDS|_MLST|_MEDS|_FTLD|_LBD|_B1A|"
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
    r"(?P<b1a>.+_B1A\.json)|"
    r"(?P<uds>.+_UDS\.json)"
    r"$"
)


class FileModel(BaseModel):
    """Defines the data model for columns returned from the project form
    curator data view execution, plus some computed fields."""

    # from data view execution
    filename: str
    file_id: str
    file_info: Dict[str, Any]
    file_tags: List[str]
    session_id: str
    modified_date: date

    # flag to see if this file model has been processed or not
    processed: bool = False

    # private attributes to be computed
    _file_date: Optional[date] = PrivateAttr(default=None)
    _scope: Optional[ScopeLiterals] = PrivateAttr(default=None)
    _visit_pass: Optional[VISIT_PASS_LITERALS] = PrivateAttr(default=None)
    _uds_visitdate: Optional[str] = PrivateAttr(default=None)

    @property
    def file_date(self) -> date:
        if not self._file_date:
            raise ValueError(
                f"file {self.filename} {self.file_id} has no associated date"
            )

        return self._file_date

    @property
    def scope(self) -> Optional[ScopeLiterals]:
        return self._scope

    @property
    def visit_pass(self) -> Optional[VISIT_PASS_LITERALS]:
        return self._visit_pass

    @property
    def uds_visitdate(self) -> Optional[str]:
        return self._uds_visitdate

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
            raise ValueError("modified date not found")

        return result

    @model_validator(mode="after")
    def compute_values(self) -> "FileModel":
        """Compute values that need to be derived from other fields."""
        self._file_date = self.__determine_file_date()
        self._scope = self.__determine_scope()
        self._visit_pass = self.__determine_visit_pass()

        return self

    def __determine_scope(self) -> Optional[ScopeLiterals]:
        """Determine the file's scope."""
        if "historic_apoe_genotype" in self.filename:
            return "historic_apoe"

        match = SCOPE_PATTERN.match(self.filename)
        if not match:
            return None

        groups = match.groupdict()
        names = {key for key in groups if groups.get(key) is not None}
        if len(names) != 1:
            raise ValueError(f"error matching file name {self.filename} to scope")

        return names.pop()  # type: ignore

    def __determine_file_date(self) -> date:
        """Determine the file/form date that best represents this file.

        First check known form dates, then known imaging dates, then
        default to the modified date.
        """
        form_data = self.file_info.get("forms", {}).get("json", {})
        for field in ["visitdate"]:
            form_date = self.__check_date(form_data.get(field))
            if form_date:
                return form_date

        raw_data = self.file_info.get("raw", {})
        for field in ["study_date", "scan_date", "scandate", "scandt"]:
            raw_date = self.__check_date(raw_data.get(field))
            if raw_date:
                return raw_date

        dicom_data = self.file_info.get("header", {}).get("dicom", {})
        for field in ["StudyDate"]:
            dicom_date = self.__check_date(dicom_data.get(field))
            if dicom_date:
                return dicom_date

        # default is just the file's actual upload/modified date
        return self.modified_date

    def __determine_visit_pass(self) -> Optional[VISIT_PASS_LITERALS]:
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

    def set_uds_visitdate(self, uds_visitdate: str) -> None:
        """Set the UDS visitdate."""
        self._uds_visitdate = uds_visitdate

    def __eq__(self, other) -> bool:
        if not isinstance(other, FileModel):
            return False

        return self.file_id == other.file_id

    def __lt__(self, other) -> bool:
        """Order the objects by order class and date.

        First, use inverse order on order-class: if the class is greater
        than, the object is less than. Second, group by the file's
        scope. Finally, group by date.
        """
        if not isinstance(other, FileModel):
            return False
        if not self.visit_pass or not other.visit_pass:
            raise ValueError(
                f"Cannot compare values {self.visit_pass} with {other.visit_pass}"
            )

        # First, group by visitpass
        # Note: this inverts the order on the order_class
        if self.visit_pass > other.visit_pass:
            return True
        if self.visit_pass < other.visit_pass:
            return False

        # Next, group by scope
        if self.scope != other.scope and self.scope and other.scope:
            return self.scope < other.scope

        # Finally, group by relative dates
        if self.uds_visitdate and other.uds_visitdate:
            return self.uds_visitdate < other.uds_visitdate

        return self.file_date < other.file_date


class ViewResponseModel(BaseModel):
    """Defines the data model for a dataview response, and handles sanitizing
    the data."""

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

    def associate_uds_session(self) -> None:
        """Link all files belonging to a single UDS session and setting the
        uds_visitdate parameter.

        Mainly done to associate the MEDS file, which may not have the
        same form date as the UDS visit. This is also a way to detect
        duplicate sessions that can result from new updates changing
        the session visit number.

        The reason we call this directly instead of having it automatically
        run after model creation is because we do still want to know what
        files were pulled; if we fail on validation we lose that information.
        """
        # get UDS sessions; there should be exactly one per vistdate,
        # so sanity check that as well
        uds_sessions: Dict[str, str] = {}
        found_visitdates = set()
        for file in self.data:
            if file.scope == FormScope.UDS:
                visitdate = str(file.file_date)
                if visitdate in found_visitdates:
                    raise ValueError(
                        f"Multiple UDS sessions defined for visitdate {visitdate}"
                    )

                uds_sessions[file.session_id] = visitdate
                found_visitdates.add(visitdate)

        # link the UDS visitdate to each associated file in the same session
        for file in self.data:
            uds_visitdate = uds_sessions.get(file.session_id)
            if uds_visitdate:
                file.set_uds_visitdate(uds_visitdate)
