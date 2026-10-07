import logging
from typing import Any, ClassVar, Final, Optional

from flywheel.models.acquisition import Acquisition
from flywheel.models.container_output import ContainerOutput
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)


class ImageSubmissionForm(BaseModel):
    """Collects and stores Flywheel data for the REDCap Image Submission EDC
    form."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    adcid: Optional[int] = None
    fw_session_label: Optional[str] = None
    fwid: Optional[str] = None
    imagetype: Optional[int] = None
    naccid: Optional[str] = None
    ptid: Optional[str] = None
    redcap_data_access_group: Optional[str] = None
    scandt: Optional[str] = None
    scanstart: Optional[str] = None
    upload_date: Optional[str] = None
    uploader_email: Optional[str] = None
    uploader_fullname: Optional[str] = None
    fw_mri_series: Optional[str] = None
    fw_header: Optional[str] = None
    fw_dicom: Optional[str] = None

    __conflicts: dict[str, str]

    # keys are Flywheel's two-character modality
    # values are NACC's imagetype code
    _imagetype_from_modality: ClassVar[dict[str, int]] = {
        "PT": 1,  # PET
        "MR": 2,  # MRI
    }

    # keys are REDCap image form variables
    # values are DICOM tag names
    _pet_tag_for_variable: ClassVar[dict[str, str]] = {
        "emission_start_time": "AcquisitionTime",
        "tracer": "Radiopharmaceutical",
        "tracer_dose_assay": "RadionuclideTotalDose",
        "tracer_inj_time": "RadiopharmaceuticalStartDateTime",
    }

    # PET-specific fields stored as extra data
    emission_start_time: Optional[str] = None
    tracer: Optional[str] = None
    tracer_dose_assay: Optional[str] = None
    tracer_inj_time: Optional[str] = None

    # PET-specific mapping to search for each allowed tracer code
    # Keys have precedence and no key or list item should contain another
    _pet_matches_for_code: Final[dict[str, list[str]]] = {
        "FBB": ["Florbetaben"],
        "FBP": ["Florbetapir"],
        "FTP": ["Flortaucipir"],
        "FDG": ["Fludeoxyglucose"],
        "FLUTE": ["Flutemetamol"],
        "GTP1": [],
        "MK6240": [],
        "NAV": ["NAV4694"],
        "PI2620": [],
        "PIB": ["Pittsburgh Compound B"],
    }

    # Fields that must be present for a successful export
    required_fields: ClassVar[list[str]] = [
        "adcid",
        "fw_session_label",
        "fwid",
        "imagetype",
        "naccid",
        "ptid",
        "redcap_data_access_group",
        "scandt",
        "scanstart",
        "upload_date",
        "uploader_email",
        "uploader_fullname",
    ]

    @classmethod
    def from_session(
        cls, session: ContainerOutput, proxy: FlywheelProxy
    ) -> "ImageSubmissionForm":
        """Constructs an ImageSubmissionForm by collecting data from a Flywheel
        session and its acquisitions.

        Args:
            session: the target Flywheel session
            proxy: the proxy for the Flywheel instance

        Returns:
            A populated ImageSubmissionForm instance
        """
        form = cls()
        form._collect_session_info(session, proxy)
        return form

    def check_required_fields(self) -> list[str]:
        """Returns the list of required fields that are missing (None).

        Returns:
            list of field names that are None
        """
        missing = []
        for field_name in self.required_fields:
            if getattr(self, field_name) is None:
                missing.append(field_name)
        return missing

    def get_conflicts(self) -> dict[str, str]:
        """Returns the conflicts found during creation.

        Returns:
            a copy of the internal variable __conflicts
        """
        return self.__conflicts.copy()

    def _add_conflict(self, field_name: str, conflict_reason: str):
        """Incorporates the given conflict into any existing conflicts.

        Args:
            field_name: the field to set
            conflict_reason: an explanation for the conflict
        """
        if field_name in self.__conflicts:
            self.__conflicts[field_name] += "; " + conflict_reason
        else:
            self.__conflicts[field_name] = conflict_reason

    def _set_or_agree(
        self,
        field_name: str,
        value: Any,
        info_context: str,
    ) -> None:
        """Sets the given field to the given value, tracking if there is a
        conflicting value already present.

        Args:
            field_name: the field to set
            value: value to assign
            info_context: describes the source for conflict messages
        """
        current = getattr(self, field_name)
        if current is None:
            setattr(self, field_name, value)
        elif current != value:
            self._add_conflict(
                field_name,
                f'; Expected "{current}" not "{value}" for {field_name} '
                f"from {info_context}",
            )

    def _find_flywheel_origin_user_id(
        self, flywheel_obj, proxy: FlywheelProxy
    ) -> Optional[str]:
        """Finds the user_id associated with a Flywheel object's origin.

        Args:
            flywheel_obj: target Flywheel object
            proxy: the proxy for the Flywheel instance

        Returns:
            string for user_id, if found; otherwise None
        """
        match flywheel_obj.origin["type"]:
            case "user":
                return flywheel_obj.origin["id"]
            case "job":
                j = proxy.get_job_by_id(flywheel_obj.origin["id"])
                if j is None:
                    return None
                try:
                    return j["config"]["inputs"]["input-file"]["object"]["origin"]["id"]
                except (KeyError, TypeError, IndexError):
                    return None
            case _:
                return None

    def _collect_classification(
        self, file: FileEntry, fw_mri_series: list[str]
    ) -> None:
        """Collects the classification output from the File Classifier gear.

        Args:
            file: target file from Flywheel
            fw_mri_series: list to store classifications for MRI series
        """
        if "SeriesDescription" in file.info["header"]["dicom"]:
            series_description = file.info["header"]["dicom"]["SeriesDescription"]
        else:
            series_description = "no_SeriesDescription_available"
        if file.get("classification"):
            classifications = []
            for classification_key in ["Measurement", "Intent"]:
                if file.classification.get(classification_key):
                    classifications.extend(
                        sorted(
                            file.classification[classification_key],
                            reverse=True,
                        )
                    )
            if classifications:
                fw_mri_series.append(
                    ",".join(classifications) + ":" + series_description
                )
            else:
                fw_mri_series.append("no_classification_elements:" + series_description)
        else:
            fw_mri_series.append("no_classification:" + series_description)

    def _sanitize_tracer(self) -> None:
        """Maps the given tracer to an allowable value for REDCap."""
        if self.tracer is not None:
            # matching a key gets precedence
            for redcap_code in self._pet_matches_for_code:
                if redcap_code.lower() in self.tracer.lower():
                    self.tracer = redcap_code
                    return
            # if no key, inspect any associated list of terms
            for redcap_code, possible_match_list in self._pet_matches_for_code.items():
                for possible_match in possible_match_list:
                    if possible_match.lower() in self.tracer.lower():
                        self.tracer = redcap_code
                        return
        self.tracer = "Unknown"

    def _inspect_pet(self, pet_file: FileEntry) -> None:
        """Inspects file for PET-specific information.

        Args:
            pet_file: PET file to inspect
        """
        for pet_var, pet_tag in self._pet_tag_for_variable.items():
            if pet_tag in pet_file.info["header"]["dicom"]:
                variable_value = pet_file.info["header"]["dicom"][pet_tag]
                if pet_var.endswith("_time"):
                    variable_value = variable_value.split(".")[0]
                    variable_value = (
                        variable_value[:2]
                        + ":"
                        + variable_value[2:4]
                        + ":"
                        + variable_value[4:6]
                    )
                self._set_or_agree(
                    pet_var,
                    variable_value,
                    f"file.info['header']['dicom']['{pet_var}'] in {pet_file.name}",
                )
        if self.tracer is None:
            ris = "RadiopharmaceuticalInformationSequence"
            if ris in pet_file.info["header"]["dicom"]:
                for ri_dict in pet_file.info["header"]["dicom"][ris]:
                    if "Radiopharmaceutical" in ri_dict:
                        self._set_or_agree(
                            "tracer",
                            ri_dict["Radiopharmaceutical"],
                            "file.info['header']['dicom']"
                            f"['{ris}']...['Radiopharmaceutical']"
                            f" in {pet_file.name}",
                        )
        self._sanitize_tracer()

    def _inspect_acquisition(
        self,
        fw_mri_series: list[str],
        acq: Acquisition,
        proxy: FlywheelProxy,
    ) -> None:
        """Inspects an acquisition to extract information for the form.

        Args:
            fw_mri_series: list of classifications for MRI series
            acq: target Flywheel acquisition
            proxy: the proxy for the Flywheel instance
        """
        log.info(f"  Found acquisition: {acq.label}")
        for file in acq.files:
            reloaded_file = file.reload()
            user_id = self._find_flywheel_origin_user_id(reloaded_file, proxy)
            if user_id is not None:
                self._set_or_agree(
                    "uploader_email",
                    user_id,
                    f"origin['id'] in {reloaded_file.name}",
                )
            if reloaded_file.modality is None:
                self._add_conflict(
                    "imagetype",
                    f"interprettable modality missing from {reloaded_file.name}",
                )
            elif reloaded_file.modality not in self._imagetype_from_modality:
                self._add_conflict(
                    "imagetype",
                    f'unrecognized modality "{reloaded_file.modality}" '
                    f"from {reloaded_file.name}",
                )
            else:
                self._set_or_agree(
                    "imagetype",
                    self._imagetype_from_modality[reloaded_file.modality],
                    f"file.modality in {reloaded_file.name}",
                )
            if "header" not in reloaded_file.info:
                self._add_conflict(
                    "fw_header", f'"header" missing from {reloaded_file.name}'
                )
                return
            if "dicom" not in reloaded_file.info["header"]:
                self._add_conflict(
                    "fw_dicom", f'"dicom" missing from {reloaded_file.name}["header"]'
                )
                return
            if "StudyDate" in reloaded_file.info["header"]["dicom"]:
                studydt = reloaded_file.info["header"]["dicom"]["StudyDate"]
                studydt = studydt[:4] + "-" + studydt[4:6] + "-" + studydt[6:]
                self._set_or_agree(
                    "scandt",
                    studydt,
                    "file.info['header']['dicom']['StudyDate']"
                    f" in {reloaded_file.name}",
                )
            if reloaded_file.modality == "PT":
                self._inspect_pet(reloaded_file)
            elif reloaded_file.modality == "MR":
                self._collect_classification(reloaded_file, fw_mri_series)

    def _inspect_acquisitions(
        self, session: ContainerOutput, proxy: FlywheelProxy
    ) -> None:
        """Inspects the acquisitions in the session to extract form data.

        Args:
            session: the target Flywheel session
            proxy: the proxy for the Flywheel instance
        """
        fw_mri_series: list[str] = []
        self.__conflicts = {}
        for acq in session.acquisitions():
            self._inspect_acquisition(fw_mri_series, acq, proxy)
        for field_name, reason in self.__conflicts.items():
            log.warning(f"{field_name}: {reason}")
            # Setting to None causes check_required_fields() to flag
            # this field as missing, which fails the gear with a clear
            # "missing information" error.
            setattr(self, field_name, None)
        if self.scandt is None:
            log.warning("No scandt found from any acquisition")
        if fw_mri_series:
            self.fw_mri_series = ";".join(fw_mri_series)

    def _collect_session_info(
        self, session: ContainerOutput, proxy: FlywheelProxy
    ) -> None:
        """Collects all session information for the REDCap form.

        Does not find or define record_id because record_id needs
        special treatment.

        Args:
            session: the target Flywheel session
            proxy: the proxy for the Flywheel instance
        """
        fw_proj = proxy.get_container_by_id(session.project)

        if "pipeline_adcid" in fw_proj.info:
            if isinstance(fw_proj.info["pipeline_adcid"], int):
                self.adcid = fw_proj.info["pipeline_adcid"]
            else:
                log.warning(
                    "Expected adcid to be int, "
                    f"not {type(fw_proj.info['pipeline_adcid'])} "
                    f"for {fw_proj.info['pipeline_adcid']}"
                )
        else:
            log.warning(
                "Expected pipeline_adcid key in custom information "
                f"from project {fw_proj.label} for session "
                f"{session.label}"
            )

        if "redcap_data_access_group" in fw_proj.info:
            if isinstance(fw_proj.info["redcap_data_access_group"], str):
                self.redcap_data_access_group = fw_proj.info["redcap_data_access_group"]
            else:
                log.warning(
                    "Expected redcap_data_access_group to be str, "
                    "not "
                    f"{type(fw_proj.info['redcap_data_access_group'])}"
                    " for "
                    f"{fw_proj.info['redcap_data_access_group']}"
                )
        else:
            log.warning(
                "Expected redcap_data_access_group key in custom "
                f"information from project {fw_proj.label} for "
                f"session {session.label}"
            )

        subject = session.subject
        if "naccid" in subject.info:
            self.naccid = session.subject.info["naccid"]
        else:
            log.warning("Expected entry for naccid in subject.info")
        if session.timestamp:
            self.scanstart = session.timestamp.strftime("%H:%M:%S")
        if session.created:
            self.upload_date = session.created.strftime("%Y-%m-%d")

        self.fw_session_label = session.label
        self.fwid = session.id
        self.ptid = session.subject.label

        self._inspect_acquisitions(session, proxy)
        if self.uploader_email:
            user = proxy.find_user(self.uploader_email)
            if user is None:
                log.warning(
                    "Unable to determine uploader_fullname from "
                    f"email {self.uploader_email}"
                )
            else:
                self.uploader_fullname = (
                    (user.firstname or "") + " " + (user.lastname or "")
                )
        else:
            log.warning("Missing uploader_email after inspecting acquisitions")
