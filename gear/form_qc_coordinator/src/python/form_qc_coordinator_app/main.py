"""Defines Form QC Coordinator."""

import logging
from typing import Dict, List

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs, PipelineType
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

from form_qc_coordinator_app.coordinator import QCCoordinator
from form_qc_coordinator_app.visits import find_visits_for_participant_for_module

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


def trigger_dependent_modules_qc_checks(
        *, proxy: FlywheelProxy, gear_context: GearToolkitContext,
        subject: SubjectAdaptor, form_project_configs: FormProjectConfigs,
        configs_file_id: str, qc_gear_info: GearInfo,
        dependent_visits_info: Dict[str, List[Dict[str, str]]]):
    """Trigger QC checks for each dependent module for the given subject.

    Args:
        proxy: Flywheel proxy object
        gear_context: Flywheel gear context
        subject: Flywheel subject to run the QC checks
        form_project_configs: form ingest configurations
        configs_file_id: form ingest configurations file id
        qc_gear_info: GearInfo containing info for the qc gear
        dependent_visits_info: list of dependent visits by module
    """

    for dep_module, dep_visits in dependent_visits_info.items():
        if not dep_visits:
            log.warning('No visits found for dependent module %s', dep_module)
            continue

        # Create a QC Coordinator for each dependent module
        log.info(
            'Triggering QC Coordinator for dependent module %s #visits: %s',
            dep_module, len(dep_visits))

        qc_coordinator = QCCoordinator(
            subject=subject,
            module=dep_module,
            form_project_configs=form_project_configs,
            configs_file_id=configs_file_id,
            qc_gear_info=qc_gear_info,
            proxy=proxy,
            gear_context=gear_context,
            dependent_modules=form_project_configs.get_module_dependencies(
                module=dep_module))

        qc_coordinator.run_error_checks(visits=dep_visits)


def run(*,
        gear_context: GearToolkitContext,
        client_wrapper: ClientWrapper,
        visits_file_wrapper: InputFileWrapper,
        form_project_configs: FormProjectConfigs,
        configs_file_id: str,
        subject: SubjectAdaptor,
        visits_info: ParticipantVisits,
        qc_gear_info: GearInfo,
        pipeline: PipelineType,
        check_all: bool = False):
    """Invoke QC process for the given participant/module.

    Args:
        gear_context: Flywheel gear context
        client_wrapper: Flywheel SDK client wrapper
        visits_file_wrapper: Input file wrapper
        subject: Flywheel subject to run the QC checks
        form_project_configs: form ingest configurations
        configs_file_id: form ingest configurations file id
        visits_info: Info on new/updated visits for the participant/module
        qc_gear_info: QC gear name and configs
        pipeline: Pipeline that triggered this gear instance
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

    if (module not in form_project_configs.accepted_modules
            or not form_project_configs.module_configs.get(module)):
        raise GearExecutionError(
            f'Failed to find the configurations for module {module}')

    module_configs: ModuleConfigs = form_project_configs.module_configs.get(
        module)  # type: ignore

    dependent_modules = form_project_configs.get_module_dependencies(
        module=module)
    log.info('List of other modules dependent on module %s: %s', module,
             dependent_modules)

    proxy = client_wrapper.get_proxy()

    visits_list = find_visits_for_participant_for_module(
        proxy=proxy,
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

    qc_coordinator = QCCoordinator(subject=subject,
                                   module=module,
                                   form_project_configs=form_project_configs,
                                   configs_file_id=configs_file_id,
                                   qc_gear_info=qc_gear_info,
                                   proxy=proxy,
                                   gear_context=gear_context,
                                   dependent_modules=dependent_modules)

    qc_coordinator.run_error_checks(visits=visits_list)

    dependent_visits_info = qc_coordinator.get_dependent_module_visits()
    if dependent_visits_info:
        trigger_dependent_modules_qc_checks(
            proxy=proxy,
            gear_context=gear_context,
            subject=subject,
            form_project_configs=form_project_configs,
            configs_file_id=configs_file_id,
            qc_gear_info=qc_gear_info,
            dependent_visits_info=dependent_visits_info)

    update_file_tags(gear_context, visits_file_wrapper)
