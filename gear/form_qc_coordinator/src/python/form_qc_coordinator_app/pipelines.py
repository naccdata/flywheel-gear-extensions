import logging

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import ParticipantVisits, SubjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import GearInfo

from form_qc_coordinator_app.coordinator import QCCoordinator
from form_qc_coordinator_app.visits import VisitsLookupHelper

log = logging.getLogger(__name__)


class PipelineProcessor():
    """Class to trigger the QC process for a pipeline."""

    def __init__(self,
                 *,
                 proxy: FlywheelProxy,
                 gear_context: GearToolkitContext,
                 subject: SubjectAdaptor,
                 module: str,
                 visits_info: ParticipantVisits,
                 form_project_configs: FormProjectConfigs,
                 qc_gear_info: GearInfo,
                 configs_file: FileEntry,
                 check_all: bool = False) -> None:
        """Initialize the Pipeline Processor.

        Args:
            proxy: Flywheel proxy object
            gear_context: Flywheel gear context
            subject: Flywheel subject to run the QC checks
            module: module label
            visits_info: Info on visits to process for the subject
            form_project_configs: form ingest configurations for the project
            qc_gear_info: QC gear name and configs
            configs_file: form ingest configurations file entry object
            check_all: re-evaluate all visits for the subject/module
        """
        self.__proxy = proxy
        self.__gear_context = gear_context
        self.__module = module
        self.__subject = subject
        self.__visits_info = visits_info
        self.__form_configs = form_project_configs
        self.__qc_gear_info = qc_gear_info
        self.__configs_file = configs_file
        self.__check_all = check_all

        if (module not in form_project_configs.accepted_modules
                or not form_project_configs.module_configs.get(module)):
            raise GearExecutionError(
                f'Failed to find the ingest configurations for module {module}'
            )

        self.__module_configs: ModuleConfigs = self.__form_configs.module_configs.get(
            self.__module)  # type: ignore

        self.__visits_lookup_helper = VisitsLookupHelper(
            proxy=proxy,
            subject=subject,
            form_project_configs=form_project_configs)

    def trigger_submission_pipeline_qc_process(self):
        """Trigger the QC process for the `submission` pipeline.

        Raises:
            GearExecutionError: If errors occur during QC process
        """

        if self.__check_all:
            cutoff = None
        else:
            curr_visit = sorted(self.__visits_info.visits,
                                key=lambda d: d.visitdate)[0]
            cutoff = curr_visit.visitdate

        visits_list = self.__visits_lookup_helper.find_visits_for_module(
            module=self.__module,
            module_configs=self.__module_configs,
            cutoff_date=cutoff)
        if not visits_list:
            # This cannot happen,
            # at least one file should exist with matching cutoff date
            raise GearExecutionError(
                "Cannot find matching visits for subject "
                f"{self.__subject.label}/{self.__module} with "
                f"{self.__module_configs.date_field}>={cutoff}")

        qc_coordinator = QCCoordinator(
            subject=self.__subject,
            module=self.__module,
            form_project_configs=self.__form_configs,
            configs_file=self.__configs_file,
            qc_gear_info=self.__qc_gear_info,
            proxy=self.__proxy,
            gear_context=self.__gear_context)

        qc_coordinator.run_error_checks(visits=visits_list)

    def trigger_finalization_pipeline_qc_process(self):
        """Trigger the QC process for the `finalization` pipeline.

        Raises:
            GearExecutionError: If errors occur during QC process
        """

        dependent_visits_info = self.__visits_lookup_helper.get_dependent_module_visits(
            current_module=self.__module,
            current_visits=self.__visits_info.visits)

        if not dependent_visits_info:
            log.info(
                f"No dependent module visits found for module {self.__module}")
            return

        for dep_module, dep_visits in dependent_visits_info.items():
            # Create a QC Coordinator for each dependent module
            log.info(
                'Triggering QC Coordinator for dependent module %s #visits: %s',
                dep_module, len(dep_visits))

            qc_coordinator = QCCoordinator(
                subject=self.__subject,
                module=dep_module,
                form_project_configs=self.__form_configs,
                configs_file=self.__configs_file,
                qc_gear_info=self.__qc_gear_info,
                proxy=self.__proxy,
                gear_context=self.__gear_context)

            qc_coordinator.run_error_checks(visits=dep_visits)
