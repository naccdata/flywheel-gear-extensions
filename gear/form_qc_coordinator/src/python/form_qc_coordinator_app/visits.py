import logging
from typing import Dict, List, Optional

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import SubjectAdaptor, VisitInfo
from gear_execution.gear_execution import GearExecutionError
from keys.keys import FieldNames, MetadataKeys

log = logging.getLogger(__name__)


class VisitsLookupHelper():
    """Helper class to lookup visits files for a participant matching with any
    specified constraints."""

    def __init__(self, *, proxy: FlywheelProxy, subject: SubjectAdaptor,
                 form_project_configs: FormProjectConfigs) -> None:
        """Initialize the Visits Lookup Helper.

        Args:
            proxy: Flywheel proxy object
            subject: Flywheel subject to run the QC checks
            form_project_configs: form ingest configurations
        """
        self.__proxy = proxy
        self.__subject = subject
        self.__form_project_configs = form_project_configs

    @property
    def proxy(self) -> FlywheelProxy:
        return self.__proxy

    @property
    def subject(self) -> SubjectAdaptor:
        return self.__subject

    @property
    def form_configs(self) -> FormProjectConfigs:
        return self.__form_project_configs

    def find_visits_for_module(
            self,
            *,
            module: str,
            module_configs: ModuleConfigs,
            cutoff_date: Optional[str] = None
    ) -> Optional[List[Dict[str, str]]]:
        """Get the list of visits for this participant for the specified
        module. If cutoff_date specified, get the visits having a visit date on
        or later than the cutoff_date.

        Note: This method assumes visit date in file metadata is normalized to
        YYYY-MM-DD format at a previous stage of the submission pipeline.

        Args:
            module: module label, matched with Flywheel acquisition label
            module_configs: form ingest configs for the module
            cutoff_date (optional): If specified, filter visits on date_col>=cutoff_date

        Returns:
            List[Dict]: List of visits matching with the specified cutoff date
        """

        title = f'{module} visits for participant {self.__subject.label}'

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

        return self.__proxy.get_matching_acquisition_files_info(
            container_id=self.__subject.id,
            dv_title=title,
            columns=columns,
            filters=filters)

    def find_module_visits_with_matching_visitdate(
            self, *, module: str, module_configs: ModuleConfigs,
            visitdate: str,
            visitnum: Optional[str]) -> Optional[List[Dict[str, str]]]:
        """Get the list of visits for the specified participant for the
        specified module matching with the given visitdate and visitnum (if
        specified).

        Note: This method assumes visit date in file metadata is normalized to
        YYYY-MM-DD format at a previous stage of the submission pipeline.

        Args:
            module: module label, matched with Flywheel acquisition label
            module_configs: form ingest configs for the module
            visitdate: visitdate to match
            visitnum(optional): visit number to match

        Returns:
            List[Dict]: List of visits matching with the specified date and visitnum
        """

        title = f'{module} visits for participant {self.__subject.label}'

        ptid_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PTID}'
        date_col_key = f'{MetadataKeys.FORM_METADATA_PATH}.{module_configs.date_field}'
        columns = [
            ptid_key, date_col_key, 'file.name', 'file.file_id',
            'file.parents.acquisition'
        ]

        filters = f'acquisition.label={module},{date_col_key}={visitdate}'

        if visitnum and FieldNames.VISITNUM in module_configs.required_fields:
            visitnum_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
            columns.append(visitnum_key)
            filters += f',{visitnum_key}={visitnum}'

        return self.__proxy.get_matching_acquisition_files_info(
            container_id=self.__subject.id,
            dv_title=title,
            columns=columns,
            filters=filters)

    def get_dependent_module_visits(
        self, *, current_module: str, current_visits: List[VisitInfo]
    ) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """Check whether there are any module visits dependent on the specified
        visits that needs to be re-validated.

        Args:
            current_module: current module
            current_visits: list of visits for current module
        Raises:
            GearExecutionError: if errors occur while looking up dependent visits
        """

        dependent_modules = self.__form_project_configs.get_module_dependencies(
            module=current_module)

        if not dependent_modules:
            return None

        log.info('List of other modules dependent on module %s: %s',
                 current_module, dependent_modules)

        dependent_visits: Dict[str, List[Dict[str, str]]] = {}
        for dep_module in dependent_modules:
            dep_module_configs = self.__form_project_configs.module_configs.get(
                dep_module)

            if not dep_module_configs:
                raise GearExecutionError(
                    f"Failed to find module configs for dependent module {dep_module}"
                )

            for visit in current_visits:
                matched_visits = self.find_module_visits_with_matching_visitdate(
                    module=dep_module,
                    module_configs=dep_module_configs,
                    visitdate=visit.visitdate,
                    visitnum=visit.visitnum)

                if not matched_visits:
                    log.info(f"No module visits dependent on {current_module} "
                             f"visit with visitdate: {visit.visitdate} "
                             f"visitnum: {visit.visitnum}")
                    continue

                if len(matched_visits) > 1:  # this cannot happen
                    raise GearExecutionError(
                        f"Multiple {dep_module} visits found with "
                        f"visitdate: {visit.visitdate} visitnum: {visit.visitnum}"
                    )

                if dep_module not in dependent_visits:
                    dependent_visits[dep_module] = []
                dependent_visits[dep_module].append(matched_visits[0])

        return dependent_visits
