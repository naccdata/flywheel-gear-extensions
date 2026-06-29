import logging
import sys
from typing import ClassVar, Optional

from flywheel.models.acquisition_list_output import AcquisitionListOutput
from flywheel.models.container_output import ContainerOutput

from flywheel_adaptor.flywheel_proxy import FlywheelProxy

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class FlywheelREDCapImageForm:
    """Class for collecting and storing Flywheel data for the REDCap image
    form."""

    def __init__(self, session: ContainerOutput, proxy: FlywheelProxy):
        self.__image_form: dict[str, str] = {}
        self.__construct_session_info_for_redcap(session, proxy)

    def __getitem__(self, key):
        return self.__image_form[key]

    def __setitem__(self, key, item):
        self.__image_form[key] = item

    def __len__(self):
        return len(self.__image_form)

    def __repr__(self):
        return repr(self.__image_form)

    def __delitem__(self, key):
        del self.__image_form[key]

    def clear(self):
        return self.__image_form.clear()

    def copy(self):
        return self.__image_form.copy()

    def get(self, item):
        return self.__image_form.get(item)

    def has_key(self, k):
        return k in self.__image_form

    def update(self, *args, **kwargs):
        return self.__image_form.update(*args, **kwargs)

    def keys(self):
        return self.__image_form.keys()

    def values(self):
        return self.__image_form.values()

    def items(self):
        return self.__image_form.items()

    def pop(self, *args):
        return self.__image_form.pop(*args)

    def __contains__(self, item):
        return item in self.__image_form

    def __iter__(self):
        return iter(self.__image_form)

    # keys are Flywheel's two-character modality
    # values are NACC's three-character imagetype
    __imagetype_from_modality: ClassVar[dict] = {
        "PT": 1,  # 'PET'
        "MR": 2,  # 'MRI',
    }

    # keys are REDCap image form variables
    # values are DICOM tag names
    pet_tag_for_variable: ClassVar[dict] = {
        "tracer_dose_assay": "RadionuclideTotalDose",
        "tracer_inj_time": "RadiopharmaceuticalStartDateTime",
        "emission_start_time": "AcquisitionTime",
    }

    # list of REDCap image form variables that could be assigned by this class
    all_types_variables_to_check = (
        "adcid",
        "uploader_fullname",
        "uploader_email",
        "fw_session_label",
        "fwid",
        "imagetype",
        "ptid",
        "naccid",
        "scandt",
        "scanstart",
    )

    def __find_flywheel_origin_user_id(
        self, flywheel_obj, proxy: FlywheelProxy
    ) -> Optional[str]:
        """Treats cases for finding the user_id associated with a Flywheel
        object.

        Args:
            flywheel_obj: target Flywheel object
            proxy: proxy: the proxy for the Flywheel instance

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

    def __set_or_agree(
        self,
        conflicts: dict[str, str],
        key_to_set: str,
        val_to_set: str,
        info_context: str,
    ) -> None:
        """Sets the given key to the given value, tracking if there is a
        conflicting value already present.

        Args:
            conflicts: dict with keys of variables and values of conflict context(s)
            key_to_set: variable name that is used as a key
            val_to_set: value to associate with the key
            info_context: informational string describing the context of the source
        """
        if key_to_set not in self:
            self[key_to_set] = val_to_set
        elif self[key_to_set] != val_to_set:
            conflict_str = (
                f'; Expected "{self[key_to_set]}" not "{val_to_set}" '
                + f"for {key_to_set} from {info_context}"
            )
            if key_to_set in conflicts:
                conflicts[key_to_set] = conflicts[key_to_set] + "; " + conflict_str
            else:
                conflicts[key_to_set] = conflict_str

    def __inspect_acquisition(
        self,
        fw_mri_series: list[str],
        conflicts: dict,
        acq: AcquisitionListOutput,
        proxy: FlywheelProxy,
    ) -> None:
        """Inspects the given acquisition to extract information for the form.

        Args:
            fw_mri_series: list of classifications for MRI series
            conflicts: dict with keys of variables and values of conflict context(s)
            acq: target Flywheel acquisition
            proxy: the proxy for the Flywheel instance
        """
        log.info(f"  Found acquisition: {acq.label}")
        for file in acq.files:
            file = file.reload()  # needed to populate file.info
            user_id = self.__find_flywheel_origin_user_id(file, proxy)
            if user_id is not None:
                self.__set_or_agree(
                    conflicts, "uploader_email", user_id, f"origin['id'] in {file.name}"
                )
            self.__set_or_agree(
                conflicts,
                "imagetype",
                self.__imagetype_from_modality[file.modality],
                f"file.modality in {file.name}",
            )
            if "StudyDate" in file.info["header"]["dicom"]:
                studydt = file.info["header"]["dicom"]["StudyDate"]
                studydt = studydt[:4] + "-" + studydt[4:6] + "-" + studydt[6:]
                self.__set_or_agree(
                    conflicts,
                    "scandt",
                    studydt,
                    f"file.info['header']['dicom']['StudyDate'] in {file.name}",
                )
            if file.modality == "PT":
                for pet_var, pet_tag in self.__pet_tag_for_variable.items():
                    if pet_tag in file.info["header"]["dicom"]:
                        self.__set_or_agree(
                            conflicts,
                            pet_var,
                            file.info["header"]["dicom"][pet_tag],
                            f"file.info['header']['dicom']['{pet_var}'] in {file.name}",
                        )
            elif file.modality == "MR":
                # file.classification options: Features, Intent, and Measurement
                fw_mri_series.append(
                    ",".join(
                        file.classification["Measurement"]
                        + sorted(file.classification["Features"], reverse=True)
                    )
                    + ":"
                    + file.info["header"]["dicom"]["SeriesDescription"]
                )

    def __inspect_acquisitions(
        self, session: ContainerOutput, proxy: FlywheelProxy
    ) -> None:
        """Inspects the acquisitions in the given session to extract
        information for the form.

        Args:
            session: the target Flywheel session
            proxy: the proxy for the Flywheel instance
        """
        fw_mri_series = []
        conflicts = {}  # keys are REDCap variables and values are conflict context(s)
        for acq in session.acquisitions():
            self.__inspect_acquisition(fw_mri_series, conflicts, acq, proxy)
        for key, reason in conflicts.items():
            log.warning(f"{key}: {reason}")
            self[key] = None
        if "scandt" not in self:
            log.warning("No scandt found from any acquisition")
        if fw_mri_series:
            self["fw_mri_series"] = ";".join(fw_mri_series)

    def __construct_session_info_for_redcap(
        self, session: ContainerOutput, proxy: FlywheelProxy
    ) -> None:
        """Collects all session information for the REDCap form; does not find
        or define record_id because record_id needs special treatment.

        Args:
            session: the target Flywheel session
            proxy: the proxy for the Flywheel instance
        """
        fw_proj = proxy.get_container_by_id(session.project)

        if "pipeline_adcid" in fw_proj.info:
            if isinstance(fw_proj.info["pipeline_adcid"], int):
                self["adcid"] = fw_proj.info["pipeline_adcid"]
            else:
                log.warning(
                    "Expected adcid to be int, "
                    f"not {type(fw_proj.info['pipeline_adcid'])} "
                    f"for {fw_proj.info['pipeline_adcid']}"
                )
        else:
            log.warning(
                "Expected pipeline_adcid key in custom information "
                f"from project {fw_proj.label} for session {session.label}"
            )

        subject = session.subject
        if "naccid" in subject.info:
            self["naccid"] = session.subject.info["naccid"]
        else:
            log.warning("Expected entry for naccid in subject.info")
        if session.timestamp:
            self["scanstart"] = session.timestamp.strftime("%H:%M:%S")
        self.update(
            {
                "fw_session_label": session.label,
                "fwid": session.id,
                "ptid": session.subject.label,
            }
        )

        self.__inspect_acquisitions(session, proxy)
        if "uploader_email" in self:
            user = proxy.find_user(self["uploader_email"])
            if user is None:
                log.warning(
                    "Unable to determine uploader_fullname from "
                    f"email {self['uploader_email']}"
                )
            else:
                self["uploader_fullname"] = (
                    (user.firstname or "") + " " + (user.lastname or "")
                )
        else:
            log.warning("Missing uploader_email after inspecting acquisitions")
