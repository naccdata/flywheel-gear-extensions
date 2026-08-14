from typing import Optional

from flywheel.models.container_output import ContainerOutput as ContainerOutput
from pydantic import BaseModel

from flywheel_adaptor.flywheel_proxy import FlywheelProxy as FlywheelProxy

class FlywheelREDCapImageForm(BaseModel):
    adcid: Optional[int]
    fw_session_label: Optional[str]
    fwid: Optional[str]
    imagetype: Optional[int]
    naccid: Optional[str]
    ptid: Optional[str]
    redcap_data_access_group: Optional[str]
    scandt: Optional[str]
    scanstart: Optional[str]
    upload_date: Optional[str]
    uploader_email: Optional[str]
    uploader_fullname: Optional[str]
    fw_mri_series: Optional[str]
    emission_start_time: Optional[str]
    tracer_dose_assay: Optional[str]
    tracer_inj_time: Optional[str]
    required_fields: list[str]

    @classmethod
    def from_session(
        cls, session: ContainerOutput, proxy: FlywheelProxy
    ) -> "FlywheelREDCapImageForm": ...
    def check_required_fields(self) -> list[str]: ...
