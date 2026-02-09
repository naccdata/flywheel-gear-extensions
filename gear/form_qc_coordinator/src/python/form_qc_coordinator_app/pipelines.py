import logging
from abc import ABC, abstractmethod
from typing import Optional

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs, PipelineType
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import ParticipantVisits, SubjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import GearInfo
from keys.keys import DefaultValues, MetadataKeys

from form_qc_coordinator_app.coordinator import QCCoordinator
from form_qc_coordinator_app.visits import VisitsLookupHelper

log = logging.getLogger(__name__)


class PipelineProcessor(ABC):
    """Abstract class to trigger the QC process for a pipeline."""

    def __init__(
        self,
        *,
        proxy: FlywheelProxy,
        gear_context: GearToolkitContext,
        subject: SubjectAdaptor,
        module: str,
        visits_info: ParticipantVisits,
        form_project_configs: FormProjectConfigs,
        qc_gear_info: GearInfo,
        configs_file: FileEntry,
        check_all: bool = False,
    ) -> None:
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
        self._proxy = proxy
        self._gear_context = gear_context
        self._module = module
        self._subject = subject
        self._visits_info = visits_info
        self._form_configs = form_project_configs
        self._qc_gear_info = qc_gear_info
        self._configs_file = configs_file
        self._check_all = check_all

        if (
            module not in form_project_configs.accepted_modules
            or not form_project_configs.module_configs.get(module)
        ):
            raise GearExecutionError(
                f"Failed to find the ingest configurations for module {module}"
            )

        self._module_configs: ModuleConfigs = self._form_configs.module_configs.get(
            self._module
        )  # type: ignore

        self._visits_lookup_helper = VisitsLookupHelper(
            proxy=proxy, subject=subject, form_project_configs=form_project_configs
        )

    @abstractmethod
    def trigger_qc_process(self) -> None:
        """Trigger the QC process for the pipeline."""
        pass


class SubmissionPipelineProcessor(PipelineProcessor):
    """Subclass to handle submission pipeline QC process."""

    def trigger_qc_process(self):
        """Trigger the QC process for the `submission` pipeline.

        Raises:
            GearExecutionError: If errors occur during QC process
        """

        cutoff = None
        search_operator = ">="

        if not self._check_all:
            sorted_visits = sorted(self._visits_info.visits, key=lambda d: d.visitdate)
            cutoff = sorted_visits[0].visitdate

            # If module is not longitudinal no need to evaluate all subsequent visits
            # set search operator to only look for specified visits
            if not self._module_configs.longitudinal:
                search_operator = "="

                if len(sorted_visits) > 1:
                    cutoff = ",".join([f"'{d.visitdate}'" for d in sorted_visits])
                    search_operator = DefaultValues.FW_SEARCH_OR

        visits_list = self._visits_lookup_helper.find_visits_for_module(
            module=self._module,
            module_configs=self._module_configs,
            cutoff_date=cutoff,
            search_op=search_operator,
        )
        if not visits_list:
            # This cannot happen,
            # at least one file should exist with matching cutoff date
            raise GearExecutionError(
                "Cannot find matching visits for subject "
                f"{self._subject.label}/{self._module} with "
                f"{self._module_configs.date_field}{search_operator}{cutoff}"
            )

        qc_coordinator = QCCoordinator(
            subject=self._subject,
            module=self._module,
            form_project_configs=self._form_configs,
            configs_file=self._configs_file,
            qc_gear_info=self._qc_gear_info,
            proxy=self._proxy,
            gear_context=self._gear_context,
            visits_lookup_helper=self._visits_lookup_helper,
        )

        qc_coordinator.run_error_checks(visits=visits_list)


class FinalizationPipelineProcessor(PipelineProcessor):
    """Subclass to handle finalization pipeline QC process."""

    def __process_dependent_modules(self):
        """Re-process any dependent module visits matching with current
        visit."""

        dependent_visits_info = self._visits_lookup_helper.get_dependent_module_visits(
            current_module=self._module, current_visits=self._visits_info.visits
        )

        if not dependent_visits_info:
            log.info(f"No dependent module visits found for module {self._module}")
            return

        for dep_module, dep_visits in dependent_visits_info.items():
            # Create a QC Coordinator for each dependent module
            log.info(
                "Triggering QC Coordinator for dependent module %s #visits: %s",
                dep_module,
                len(dep_visits),
            )

            qc_coordinator = QCCoordinator(
                subject=self._subject,
                module=dep_module,
                form_project_configs=self._form_configs,
                configs_file=self._configs_file,
                qc_gear_info=self._qc_gear_info,
                proxy=self._proxy,
                gear_context=self._gear_context,
                visits_lookup_helper=self._visits_lookup_helper,
            )

            qc_coordinator.run_error_checks(visits=dep_visits)

    def __process_subsequent_visits(self):
        """Re-process any subsequent visits for the current module."""

        current_visit = self._visits_info.visits[0]
        visits_list = self._visits_lookup_helper.find_visits_for_module(
            module=self._module,
            module_configs=self._module_configs,
            cutoff_date=current_visit.visitdate,
            search_op=">",
            missing_data_strategy="none",
            add_timestamp=True,
        )

        if not visits_list:
            log.info(
                f"No follow-up {self._module} visits found after "
                f"the visit {current_visit.filename}"
            )
            return

        for visit in visits_list:
            visit[MetadataKeys.TRIGGERED_TIMESTAMP] = (
                current_visit.validated_timestamp
                if current_visit.validated_timestamp
                else ""
            )

        qc_coordinator = QCCoordinator(
            subject=self._subject,
            module=self._module,
            form_project_configs=self._form_configs,
            configs_file=self._configs_file,
            qc_gear_info=self._qc_gear_info,
            proxy=self._proxy,
            gear_context=self._gear_context,
            visits_lookup_helper=self._visits_lookup_helper,
        )
        qc_coordinator.run_error_checks(visits=visits_list)

    def trigger_qc_process(self):
        """Trigger the QC process for the `finalization` pipeline.

        Raises:
            GearExecutionError: If errors occur during QC process
        """

        if len(self._visits_info.visits) > 1:
            raise GearExecutionError(
                "finalization pipeline cannot be triggered on multiple visits: "
                f"{self._visits_info.visits}"
            )

        self.__process_dependent_modules()

        if self._module_configs.longitudinal:
            self.__process_subsequent_visits()


def create_pipeline_processor(
    pipeline: PipelineType, **kwargs
) -> Optional[PipelineProcessor]:
    """Creates the pipeline processor for the specified pipeline.

    Args:
        pipeline: pipeline name that triggered this gear instance
        kwargs: keyword arguments to create PipelineProcessor, which include:
            proxy: Flywheel proxy object
            gear_context: Flywheel gear context
            subject: Flywheel subject to run the QC checks
            module: module label
            visits_info: Info on visits to process for the subject
            form_project_configs: form ingest configurations for the project
            qc_gear_info: QC gear name and configs
            configs_file: form ingest configurations file entry object
            check_all: re-evaluate all visits for the subject/module

    Returns:
        PipelineProcessor: if successful else None
    """

    if pipeline == DefaultValues.SUBMISSION_PIPELINE:
        return SubmissionPipelineProcessor(**kwargs)
    elif pipeline == DefaultValues.FINALIZATION_PIPELINE:
        return FinalizationPipelineProcessor(**kwargs)
    else:
        return None
