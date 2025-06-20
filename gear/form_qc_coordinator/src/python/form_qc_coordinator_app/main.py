"""Defines Form QC Coordinator."""

import logging

from configs.ingest_configs import FormProjectConfigs, PipelineType
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import (
    ParticipantVisits,
    SubjectAdaptor,
)
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import GearInfo

from form_qc_coordinator_app.pipelines import PipelineProcessor

log = logging.getLogger(__name__)


def run(*,
        gear_context: GearToolkitContext,
        proxy: FlywheelProxy,
        subject: SubjectAdaptor,
        visits_info: ParticipantVisits,
        form_project_configs: FormProjectConfigs,
        configs_file: FileEntry,
        qc_gear_info: GearInfo,
        pipeline: PipelineType,
        check_all: bool = False):
    """Invoke QC process for the given subject and pipeline.

    Args:
        gear_context: Flywheel gear context
        proxy: Flywheel proxy object
        subject: Flywheel subject to run the QC checks
        visits_info: Info on visits to process for the subject
        form_project_configs: form ingest configurations
        configs_file_id: form ingest configurations file id
        qc_gear_info: QC gear name and configs
        pipeline: pipeline that triggered this gear instance
        check_all: re-evaluate all visits for the subject/module

    Raises:
        GearExecutionError if any problem occurs during the QC process
    """

    module = visits_info.module.upper()
    pipeline_processor = PipelineProcessor(
        proxy=proxy,
        gear_context=gear_context,
        module=module,
        subject=subject,
        visits_info=visits_info,
        form_project_configs=form_project_configs,
        qc_gear_info=qc_gear_info,
        configs_file=configs_file,
        check_all=check_all)

    function_name = f'trigger_{pipeline}_pipeline_qc_process'
    pipeline_function = getattr(pipeline_processor, function_name, None)
    if pipeline_function and callable(pipeline_function):
        pipeline_function()
    else:
        raise GearExecutionError(
            f"{function_name} not defined in the Form QC Coordinator")
