"""Defines Form QC Coordinator."""

import logging

from configs.ingest_configs import FormProjectConfigs, PipelineType
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import (
    ParticipantVisits,
    SubjectAdaptor,
)
from fw_gear import GearContext
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import GearInfo

from form_qc_coordinator_app.pipelines import create_pipeline_processor

log = logging.getLogger(__name__)


def run(
    *,
    gear_context: GearContext,
    proxy: FlywheelProxy,
    subject: SubjectAdaptor,
    visits_info: ParticipantVisits,
    form_project_configs: FormProjectConfigs,
    configs_file: FileEntry,
    qc_gear_info: GearInfo,
    pipeline: PipelineType,
    check_all: bool = False,
):
    """Invoke QC process for the given subject and pipeline.

    Args:
        gear_context: Flywheel gear context
        proxy: Flywheel proxy object
        subject: Flywheel subject to run the QC checks
        visits_info: Info on visits to process for the subject
        form_project_configs: form ingest configurations
        configs_file: form ingest configurations file
        qc_gear_info: QC gear name and configs
        pipeline: pipeline that triggered this gear instance
        check_all: re-evaluate all visits for the subject/module

    Raises:
        GearExecutionError if any problem occurs during the QC process
    """

    module = visits_info.module.upper()
    pipeline_processor = create_pipeline_processor(
        pipeline=pipeline,
        proxy=proxy,
        gear_context=gear_context,
        module=module,
        subject=subject,
        visits_info=visits_info,
        form_project_configs=form_project_configs,
        qc_gear_info=qc_gear_info,
        configs_file=configs_file,
        check_all=check_all,
    )

    if pipeline_processor:
        pipeline_processor.trigger_qc_process()
    else:
        raise GearExecutionError(
            f"Pipeline `{pipeline}` not defined in the Form QC Coordinator"
        )
