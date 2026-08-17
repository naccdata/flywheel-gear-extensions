import logging
from typing import Any, ClassVar, Optional

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
        "tracer_dose_assay": "RadionuclideTotalDose",
        "tracer_inj_time": "RadiopharmaceuticalStartDateTime",
    }

    # PET-specific fields stored as extra data
    emission_start_time: Optional[str] = None
    tracer_dose_assay: Optional[str] = None
    tracer_inj_time: Optional[str] = None

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

    def _set_or_agree(
        self,
        conflicts: dict[str, str],
        field_name: str,
        value: Any,
        info_context: str,
    ) -> None:
        """Sets the given field to the given value, tracking if there is a
        conflicting value already present.

        Args:
            conflicts: dict with field names as keys and conflict descriptions
            field_name: the field to set
            value: value to assign
            info_context: describes the source for conflict messages
        """
        current = getattr(self, field_name)
        if current is None:
            setattr(self, field_name, value)
        elif current != value:
            conflict_str = (
                f'; Expected "{current}" not "{value}" '
                f"for {field_name} from {info_context}"
            )
            if field_name in conflicts:
                conflicts[field_name] += "; " + conflict_str
            else:
                conflicts[field_name] = conflict_str

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
                    ",".join(classifications)
                    + ":"
                    + file.info["header"]["dicom"]["SeriesDescription"]
                )
            else:
                fw_mri_series.append(
                    "no_classification_elements:"
                    + file.info["header"]["dicom"]["SeriesDescription"]
                )
        else:
            fw_mri_series.append(
                "no_classification:" + file.info["header"]["dicom"]["SeriesDescription"]
            )

    def _inspect_acquisition(
        self,
        fw_mri_series: list[str],
        conflicts: dict[str, str],
        acq: Acquisition,
        proxy: FlywheelProxy,
    ) -> None:
        """Inspects an acquisition to extract information for the form.

        Args:
            fw_mri_series: list of classifications for MRI series
            conflicts: dict tracking field conflicts
            acq: target Flywheel acquisition
            proxy: the proxy for the Flywheel instance
        """
        log.info(f"  Found acquisition: {acq.label}")
        for file in acq.files:
            reloaded_file = file.reload()
            user_id = self._find_flywheel_origin_user_id(reloaded_file, proxy)
            if user_id is not None:
                self._set_or_agree(
                    conflicts,
                    "uploader_email",
                    user_id,
                    f"origin['id'] in {reloaded_file.name}",
                )
            self._set_or_agree(
                conflicts,
                "imagetype",
                self._imagetype_from_modality[reloaded_file.modality],
                f"file.modality in {reloaded_file.name}",
            )
            if "StudyDate" in reloaded_file.info["header"]["dicom"]:
                studydt = reloaded_file.info["header"]["dicom"]["StudyDate"]
                studydt = studydt[:4] + "-" + studydt[4:6] + "-" + studydt[6:]
                self._set_or_agree(
                    conflicts,
                    "scandt",
                    studydt,
                    "file.info['header']['dicom']['StudyDate']"
                    f" in {reloaded_file.name}",
                )
            if reloaded_file.modality == "PT":
                for pet_var, pet_tag in self._pet_tag_for_variable.items():
                    if pet_tag in reloaded_file.info["header"]["dicom"]:
                        variable_value = reloaded_file.info["header"]["dicom"][pet_tag]
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
                            conflicts,
                            pet_var,
                            variable_value,
                            "file.info['header']['dicom']"
                            f"['{pet_var}']"
                            f" in {reloaded_file.name}",
                        )
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
        conflicts: dict[str, str] = {}
        for acq in session.acquisitions():
            self._inspect_acquisition(fw_mri_series, conflicts, acq, proxy)
        for field_name, reason in conflicts.items():
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
