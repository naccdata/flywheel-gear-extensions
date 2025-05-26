"""Defines Form QC Coordinator."""

import logging
from typing import Dict, List, Optional

from configs.ingest_configs import ModuleConfigs
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import (
    ParticipantVisits,
    SubjectAdaptor,
)
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearExecutionError,
    InputFileWrapper,
)
from gear_execution.gear_trigger import GearInfo
from keys.keys import FieldNames, MetadataKeys
from pydantic import ValidationError
from utils.utils import load_form_ingest_configurations

from form_qc_coordinator_app.coordinator import QCCoordinator

log = logging.getLogger(__name__)


def update_file_tags(gear_context: GearToolkitContext,
                     input_wrapper: InputFileWrapper):
    """Add gear tag to file.

    Args:
        gear_context: Flywheel gear context
        input_wrapper: gear input file wrapper
    """

    gear_name = gear_context.manifest.get('name', 'form-qc-coordinator')
    gear_context.metadata.add_file_tags(input_wrapper.file_input,
                                        tags=gear_name)


def get_matching_visits(
        *,
        proxy: FlywheelProxy,
        container_id: str,
        subject: str,
        module: str,
        module_configs: ModuleConfigs,
        cutoff_date: Optional[str] = None) -> Optional[List[Dict[str, str]]]:
    """Get the list of visits for the specified participant for the specified
    module.

    Note: This method assumes visit date in file metadata is normalized to
    YYYY-MM-DD format at a previous stage of the submission pipeline.

    Args:
        proxy: Flywheel proxy
        container_id: Flywheel subject container ID
        subject: Flywheel subject label for participant
        module: module label, matched with Flywheel acquisition label
        module_configs: form ingest configs for the module
        cutoff_date (optional): If specified, filter visits on date_col >= cutoff_date

    Returns:
        List[Dict]: List of visits matching with the specified cutoff date
    """

    title = f'{module} visits for participant {subject}'

    ptid_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PTID}'
    date_col_key = f'{MetadataKeys.FORM_METADATA_PATH}.{module_configs.date_field}'
    columns = [
        ptid_key, date_col_key, 'file.name', 'file.file_id',
        'file.parents.acquisition'
    ]

    if FieldNames.VISITNUM in module_configs.required_fields:
        visitnum_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
        columns.append(visitnum_key)

    filters = f'acquisition.label={module}'

    if cutoff_date:
        filters += f',{date_col_key}>={cutoff_date}'

    return proxy.get_matching_acquisition_files_info(container_id=container_id,
                                                     dv_title=title,
                                                     columns=columns,
                                                     filters=filters)


def run(*,
        gear_context: GearToolkitContext,
        client_wrapper: ClientWrapper,
        visits_file_wrapper: InputFileWrapper,
        configs_file_wrapper: InputFileWrapper,
        subject: SubjectAdaptor,
        visits_info: ParticipantVisits,
        qc_gear_info: GearInfo,
        check_all: bool = False):
    """Invoke QC process for the given participant/module.

    Args:
        gear_context: Flywheel gear context
        client_wrapper: Flywheel SDK client wrapper
        visits_file_wrapper: Input file wrapper
        subject: Flywheel subject to run the QC checks
        configs_file_wrapper: module configurations file
        visits_info: Info on new/updated visits for the participant/module
        qc_gear_info: QC gear name and configs
        check_all: re-evaluate all visits for the participant/module

    Raises:
        GearExecutionError if any problem occurs during the QC process
    """

    if check_all:
        cutoff = None
    else:
        curr_visit = sorted(visits_info.visits, key=lambda d: d.visitdate)[0]
        cutoff = curr_visit.visitdate

    module = visits_info.module.upper()

    try:
        form_project_configs = load_form_ingest_configurations(
            configs_file_wrapper.filepath)
    except ValidationError as error:
        raise GearExecutionError(
            'Error reading form configurations file '
            f'{configs_file_wrapper.filename}: {error}') from error

    if (module not in form_project_configs.accepted_modules
            or not form_project_configs.module_configs.get(module)):
        raise GearExecutionError(
            f'Failed to find the configurations for module {module}')

    module_configs: ModuleConfigs = form_project_configs.module_configs.get(
        module)  # type: ignore

    proxy = client_wrapper.get_proxy()

    visits_list = get_matching_visits(proxy=proxy,
                                      container_id=subject.id,
                                      subject=subject.label,
                                      module=module,
                                      module_configs=module_configs,
                                      cutoff_date=cutoff)
    if not visits_list:
        # This cannot happen, at least one file should exist with matching cutoff date
        raise GearExecutionError(
            'Cannot find matching visits for subject '
            f'{subject.label}/{module} with {module_configs.date_field}>={cutoff}'
        )

    qc_coordinator = QCCoordinator(
        subject=subject,
        module=module,
        module_configs=module_configs,
        configs_file_id=configs_file_wrapper.file_id,
        qc_gear_info=qc_gear_info,
        proxy=proxy,
        gear_context=gear_context)

    qc_coordinator.run_error_checks(visits=visits_list)

    update_file_tags(gear_context, visits_file_wrapper)
