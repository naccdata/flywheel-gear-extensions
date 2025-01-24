"""QC checks coordination module."""

import logging
from collections import deque
from typing import Dict, List, Optional

from configs.ingest_configs import ModuleConfigs
from flywheel import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor, VisitInfo
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.utils.metadata import Metadata, create_qc_result_dict
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import GearConfigs, GearInfo, trigger_gear
from jobs.job_poll import JobPoll
from keys.keys import DefaultValues, FieldNames, SysErrorCodes
from outputs.errors import (
    FileError,
    ListErrorWriter,
    get_error_log_name,
    preprocessing_error,
    previous_visit_failed_error,
    system_error,
    update_error_log_and_qc_metadata,
)

log = logging.getLogger(__name__)


class QCGearConfigs(GearConfigs):
    """Class to represent qc gear configs."""
    rules_s3_bucket: str
    qc_checks_db_path: str
    strict_mode: Optional[bool] = True
    admin_group: Optional[str] = DefaultValues.NACC_GROUP_ID


class QCCoordinator():
    """This class coordinates the data quality checks for a given participant.

    - For each module visits are evaluated in the order of visit date.
    - If visit N for module M has not passed error checks any of the
    subsequent visits will not be evaluated for that module.
    - If an existing visit is modified, all of the subsequent visits are re-evaluated.
    """

    def __init__(self, *, subject: SubjectAdaptor, module: str,
                 module_configs: ModuleConfigs, configs_file_id: str,
                 qc_gear_info: GearInfo, proxy: FlywheelProxy,
                 gear_context: GearToolkitContext) -> None:
        """Initialize the QC Coordinator.

        Args:
            subject: Flywheel subject to run the QC checks
            module: module label, matched with Flywheel acquisition label
            module_configs: module ingest configurations
            configs_file_id: form ingest configurations file id
            qc_gear_info: GearInfo containing info for the qc gear
            proxy: Flywheel proxy object
            gear_context: Flywheel gear context
        """
        self.__subject = subject
        self.__module = module
        self.__module_configs = module_configs
        self.__qc_gear_info = qc_gear_info
        self.__proxy = proxy
        self.__configs_file = proxy.get_file(configs_file_id)
        self.__metadata = Metadata(context=gear_context)

    def passed_qc_checks(self, visit_file: FileEntry, gear_name: str) -> bool:
        """Check the validation status for the specified visit for the
        specified gear.

        Args:
            visit_file: visit file object
            gear_name: gear name

        Returns:
            bool: True if the visit passed validation
        """
        visit_file = visit_file.reload()
        if not visit_file.info:
            return False

        qc_info = visit_file.info.get('qc', {})
        gear_info = qc_info.get(gear_name, {})
        validation = gear_info.get('validation', {})
        return not ('state' not in validation or validation['state'] != 'PASS')

    def __update_qc_error_metadata(self,
                                   *,
                                   visit_file: FileEntry,
                                   ptid: str,
                                   visitdate: str,
                                   status: str,
                                   error_obj: Optional[FileError] = None):
        """Add error metadata to the visits file qc info section.
        Also, updates the visit error log and add qc info metadata
        Note: This method modifies metadata in a file which is not tracked as gear input

        Args:
            visit_file: FileEntry object for the visits file
            ptid: PTID
            visitdate: visit date
            status: QC status
            error_obj (optional): FileError object with failure info
        """

        error_writer = ListErrorWriter(
            container_id=visit_file.id,
            fw_path=self.__proxy.get_lookup_path(visit_file))

        if error_obj:
            error_writer.write(error_obj)

        qc_result = create_qc_result_dict(name='validation',
                                          state=status,
                                          data=error_writer.errors())
        visit_file = visit_file.reload()
        info = visit_file.info if (visit_file.info
                                   and 'qc' in visit_file.info) else {
                                       'qc': {}
                                   }

        # add qc-coordinator gear info to visit file metadata
        updated_qc_info = self.__metadata.add_gear_info(
            'qc', visit_file, **qc_result)
        gear_name = self.__metadata.name  # type: ignore
        info['qc'][gear_name] = updated_qc_info['qc'][gear_name]

        try:
            visit_file.update_info(info)
        except ApiException as error:
            log.error('Error in setting QC metadata in file %s - %s',
                      visit_file, error)

        error_log_name = get_error_log_name(module=self.__module,
                                            input_data={
                                                'ptid': ptid,
                                                'visitdate': visitdate
                                            })

        project = self.__proxy.get_project_by_id(
            self.__subject.parents.project)  # type: ignore

        if not error_log_name or not project or not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=ProjectAdaptor(project=project,
                                               proxy=self.__proxy),
                gear_name=gear_name,
                state=status,
                errors=error_writer.errors()):
            raise GearExecutionError(
                f'Failed to update error log for visit {ptid}, {visitdate}')

    def update_last_failed_visit(self, file_id: str, filename: str,
                                 visitdate: str):
        """Update last failed visit details in subject metadata.

        Args:
            file_id: Flywheel file id of the failed visit file
            filename: name of the failed visit file
            visitdate: visit date of the failed visit
        """
        visit_info = VisitInfo(file_id=file_id,
                               filename=filename,
                               visitdate=visitdate)
        self.__subject.set_last_failed_visit(self.__module, visit_info)

    def __get_matching_supplement_visit_file(
            self, *, supplement_module_info: Dict[str, str], visitdate: str,
            visitnum: str) -> Optional[FileEntry]:
        """Find the matching supplement visit for the current visit (i.e.
        respective UDS visit for LBD or FTLD submission)

        Note: This method assumes visit date in file metadata is normalized to
        YYYY-MM-DD format at a previous stage of the submission pipeline.

        Args:
            supplement_module_info: supplement module information
            visitdate: visit date for current input
            visitnum: visit number for current input

        Returns:
            FileEntry(optional): matching supplement visit file if found
        """

        supplement_module = supplement_module_info.get('label')
        supplement_date_field = supplement_module_info.get('date_field')

        title = f'{supplement_module} visits for participant {self.__subject.label}'

        ptid_key = f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.PTID}'
        date_col_key = f'{DefaultValues.FORM_METADATA_PATH}.{supplement_date_field}'
        visitnum_key = f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
        columns = [
            ptid_key, date_col_key, visitnum_key, 'file.name', 'file.file_id',
            'file.parents.acquisition'
        ]
        filters = (
            f'acquisition.label={supplement_module},{date_col_key}={visitdate},{visitnum_key}={visitnum}'
        )

        filters += (
            f',file.info.qc.{self.__qc_gear_info.gear_name}.validation.state=PASS'
        )

        log.info('Searching for supplement visits matching with %s', filters)
        matching_visits = self.__proxy.get_matching_acquisition_files_info(
            container_id=self.__subject.id,
            dv_title=title,
            columns=columns,
            filters=filters)

        if not matching_visits:
            return None

        if len(matching_visits) > 1:
            raise GearExecutionError(
                'More than one matching visits found for search '
                f'{filters} on {self.__subject}/{self.__module}')

        return self.__proxy.get_file(matching_visits[0]['file.file_id'])

    def run_error_checks(  # noqa: C901
            self, *, visits: List[Dict[str, str]]) -> None:
        """Sequentially trigger the QC checks gear on the provided visits. If a
        visit failed QC validation or error occurred while running the QC gear,
        none of the subsequent visits will be evaluated.

        Args:
            visits: set of visits to be evaluated

        Raises:
            GearExecutionError if errors occur while triggering the QC gear
        """
        gear_name = self.__qc_gear_info.gear_name

        ptid_key = f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.PTID}'
        date_col_key = (
            f'{DefaultValues.FORM_METADATA_PATH}.{self.__module_configs.date_field}'
        )
        visitnum_key = (
            f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.VISITNUM}')

        # sort the visits in the ascending order of visit date
        sorted_visits = sorted(visits, key=lambda d: d[date_col_key])
        visits_queue = deque(sorted_visits)

        supplement_module = (self.__module_configs.supplement_module if
                             self.__module_configs.supplement_module else None)

        failed_visit = ''
        while len(visits_queue) > 0:
            visit = visits_queue.popleft()
            filename = visit['file.name']
            file_id = visit['file.file_id']
            acq_id = visit['file.parents.acquisition']
            visitdate = visit[date_col_key]
            ptid = visit[ptid_key]
            visitnum = visit[visitnum_key]

            try:
                visit_file = self.__proxy.get_file(file_id)
                destination = self.__proxy.get_acquisition(acq_id)
            except ApiException as error:
                raise GearExecutionError(
                    f'Failed to retrieve {filename} - {error}') from error

            supplement_file = None
            # if supplement visit required check for approved supplement visit
            # i.e. UDS visit must be approved before processing any FTLD/LBD visits
            if (supplement_module and supplement_module.get('label')
                    and supplement_module.get('date_field')):
                supplement_file = self.__get_matching_supplement_visit_file(
                    supplement_module_info=supplement_module,
                    visitdate=visitdate,
                    visitnum=visitnum)
                if not supplement_file:
                    self.update_last_failed_visit(file_id=file_id,
                                                  filename=filename,
                                                  visitdate=visitdate)
                    error_obj = preprocessing_error(
                        field=FieldNames.MODULE,
                        value=self.__module,
                        error_code=SysErrorCodes.UDS_NOT_APPROVED,
                        ptid=ptid,
                        visitnum=visitnum)
                    self.__update_qc_error_metadata(visit_file=visit_file,
                                                    error_obj=error_obj,
                                                    ptid=ptid,
                                                    visitdate=visitdate,
                                                    status='FAIL')
                    failed_visit = visit_file.name
                    break

            job_id = trigger_gear(
                proxy=self.__proxy,
                gear_name=gear_name,
                config=self.__qc_gear_info.configs.model_dump(),
                inputs={
                    "form_data_file": visit_file,
                    "form_configs_file": self.__configs_file,
                    "supplement_data_file": supplement_file
                },
                destination=destination)
            if job_id:
                log.info('Gear %s queued for file %s - Job ID %s', gear_name,
                         filename, job_id)
            else:
                raise GearExecutionError(
                    f'Failed to trigger gear {gear_name} on file {filename}')

            # If QC gear did not complete, stop evaluating any subsequent visits
            if not JobPoll.is_job_complete(self.__proxy, job_id):
                self.update_last_failed_visit(file_id=file_id,
                                              filename=filename,
                                              visitdate=visitdate)
                error_obj = system_error(
                    f'Errors occurred while running gear {gear_name} on this file'
                )
                self.__update_qc_error_metadata(visit_file=visit_file,
                                                error_obj=error_obj,
                                                ptid=ptid,
                                                visitdate=visitdate,
                                                status='FAIL')
                failed_visit = visit_file.name
                break

            self.__update_qc_error_metadata(visit_file=visit_file,
                                            ptid=ptid,
                                            visitdate=visitdate,
                                            status='PASS')

            # If QC checks failed, stop evaluating any subsequent visits
            if not self.passed_qc_checks(visit_file, gear_name):
                failed_visit = visit_file.name
                break

        # If there are any visits left, update error metadata in the respective file
        if len(visits_queue) > 0:
            log.info(
                'Visit %s failed, '
                'there are %s subsequent visits for this participant.',
                failed_visit, len(visits_queue))
            log.info('Adding error metadata to respective visit files')
            while len(visits_queue) > 0:
                visit = visits_queue.popleft()
                file_id = visit['file.file_id']
                visitdate = visit[date_col_key]
                ptid = visit[ptid_key]
                try:
                    visit_file = self.__proxy.get_file(file_id)
                except ApiException as error:
                    log.warning('Failed to retrieve file %s - %s',
                                visit['file.name'], error)
                    log.warning('Error metadata not updated for visit %s',
                                visit['file.name'])
                    continue
                error_obj = previous_visit_failed_error(failed_visit)
                self.__update_qc_error_metadata(visit_file=visit_file,
                                                error_obj=error_obj,
                                                ptid=ptid,
                                                visitdate=visitdate,
                                                status='FAIL')
