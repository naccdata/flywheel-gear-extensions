"""QC checks coordination module."""

import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from configs.ingest_configs import (
    ErrorLogTemplate,
    FormProjectConfigs,
    SupplementModuleConfigs,
)
from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from error_logging.error_logger import (
    reset_error_log_metadata_for_gears,
    update_error_log_and_qc_metadata,
)
from flywheel.models.acquisition import Acquisition
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_adaptor.subject_adaptor import (
    SubjectAdaptor,
    VisitInfo,
)
from fw_gear import GearContext
from fw_gear.utils.metadata import Metadata, create_qc_result_dict
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import CredentialGearConfigs, GearInfo, trigger_gear
from jobs.job_poll import JobPoll
from keys.keys import DefaultValues, MetadataKeys, SysErrorCodes
from nacc_common.error_models import (
    FileError,
    FileErrorList,
    FileQCModel,
    GearQCModel,
    GearTags,
    QCStatus,
    VisitKeys,
)
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    preprocessing_error,
    system_error,
)
from pydantic import ValidationError

from form_qc_coordinator_app.visits import VisitsLookupHelper

log = logging.getLogger(__name__)


class QCGearConfigs(CredentialGearConfigs):
    """Class to represent qc gear configs."""

    rules_s3_bucket: str
    qc_checks_db_path: str
    strict_mode: Optional[bool] = True
    admin_group: Optional[str] = DefaultValues.NACC_GROUP_ID


class QCCoordinator:
    """This class coordinates the data quality checks for a given participant.

    - For each module visits are evaluated in the order of visit date.
    - If visit N for module M has not passed error checks any of the
    subsequent visits will not be evaluated for that module.
    - If an existing visit is modified, all of the subsequent visits are re-evaluated.
    - When a visit pass QC checks, any dependent module visits are also re-evaluated.
    """

    def __init__(
        self,
        *,
        subject: SubjectAdaptor,
        module: str,
        form_project_configs: FormProjectConfigs,
        configs_file: FileEntry,
        qc_gear_info: GearInfo,
        proxy: FlywheelProxy,
        gear_context: GearContext,
        visits_lookup_helper: VisitsLookupHelper,
    ) -> None:
        """Initialize the QC Coordinator.

        Args:
            subject: Flywheel subject to run the QC checks
            module: module label, matched with Flywheel acquisition label
            form_project_configs: form ingest configurations
            configs_file_id: form ingest configurations file id
            qc_gear_info: GearInfo containing info for the qc gear
            proxy: Flywheel proxy object
            gear_context: Flywheel gear context
            visits_lookup_helper: Helper class to lookup matching visits
        """
        self.__subject = subject
        self.__module = module
        self.__form_project_configs = form_project_configs
        self.__module_configs = self.__form_project_configs.module_configs.get(module)
        self.__qc_gear_info = qc_gear_info
        self.__proxy = proxy
        self.__configs_file = configs_file
        self.__metadata = Metadata(context=gear_context)
        self.__dependent_modules = form_project_configs.get_module_dependencies(
            self.__module
        )
        self.__project = self.__proxy.get_project_by_id(self.__subject.parents.project)
        self.__visits_lookup_helper = visits_lookup_helper
        self.__failed_visit: Optional[FileEntry] = None

    def __passed_qc_checks(self, visit_file: FileEntry, gear_name: str) -> bool:
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

        qc_info = visit_file.info.get("qc", {})
        gear_info = qc_info.get(gear_name, {})
        validation = gear_info.get("validation", {})
        return not ("state" not in validation or validation["state"] != "PASS")

    def __update_qc_error_metadata(
        self,
        *,
        visit_file: FileEntry,
        ptid: str,
        visitdate: str,
        status: str,
        error_obj: Optional[FileError] = None,
    ):
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
            container_id=visit_file.id, fw_path=self.__proxy.get_lookup_path(visit_file)
        )

        if error_obj:
            error_writer.write(error_obj)

        qc_result = create_qc_result_dict(
            name="validation",
            state=status,
            data=error_writer.errors().model_dump(by_alias=True),
        )
        visit_file = visit_file.reload()
        try:
            qc_info = FileQCModel.create(visit_file)
        except ValidationError as error:
            log.warning(
                "Error loading QC metadata for file %s: %s", visit_file.name, error
            )
            qc_info = FileQCModel(qc={})

        # add qc-coordinator gear info to visit file metadata
        updated_qc_info = self.__metadata.add_gear_info("qc", visit_file, **qc_result)
        gear_name = self.__metadata.name  # type: ignore
        gear_model = GearQCModel.model_validate(
            updated_qc_info["qc"][gear_name], by_alias=True
        )
        qc_info.set(gear_name=gear_name, gear_model=gear_model)

        try:
            visit_file.update_info(qc_info.model_dump(by_alias=True))
        except ApiException as error:
            log.error(
                "Error in setting QC metadata in file %s - %s", visit_file.name, error
            )

        self.__update_log_file(
            module=self.__module,
            ptid=ptid,
            visitdate=visitdate,
            status=status,
            gear_name=gear_name,
            errors=error_writer.errors(),
        )

    def __reset_qc_error_metadata(
        self,
        *,
        module: str,
        visit_file: FileEntry,
        ptid: str,
        visitdate: str,
        status: QCStatus,
        qc_gear_name: str,
        error_obj: Optional[FileError] = None,
    ):
        """Reset QC gear error metadata in the visit file qc info section.
        and update the QC gear status tag.
        Also, resets qc info metadata in visit error log.
        Note: This method modifies metadata in a file which is not tracked as gear input

        Args:
            module: module
            visit_file: FileEntry object for the visits file
            ptid: PTID
            visitdate: visit date
            status: QC status
            qc_gear_name: QC gear name to reset metadata
            error_obj (optional): FileError object with failure info
        """

        error_writer = ListErrorWriter(
            container_id=visit_file.id, fw_path=self.__proxy.get_lookup_path(visit_file)
        )

        if error_obj:
            error_writer.write(error_obj)

        visit_file = visit_file.reload()
        try:
            qc_info = FileQCModel.create(visit_file)
        except ValidationError as error:
            log.warning(
                "Error loading QC metadata for file %s: %s", visit_file.name, error
            )
            qc_info = FileQCModel(qc={})

        # rest form-qc-checker errors if any
        qc_info.reset(gear_name=qc_gear_name)
        qc_info.set_errors(
            gear_name=self.__metadata.name,  # type: ignore
            status=status,
            errors=error_writer.errors().model_dump(by_alias=True),
        )

        try:
            visit_file.update_info(qc_info.model_dump(by_alias=True))

            # update gear status tag
            gear_tags = GearTags(gear_name=qc_gear_name)
            fail_tag = gear_tags.fail_tag
            pass_tag = gear_tags.pass_tag

            # visit file is not tracked through gear context
            # need to directly add/remove tags from FileEntry object
            if visit_file.tags:
                if fail_tag in visit_file.tags:
                    visit_file.delete_tag(fail_tag)
                if pass_tag in visit_file.tags:
                    visit_file.delete_tag(pass_tag)

        except ApiException as error:
            log.error(
                f"Error in resetting QC metadata in file {visit_file.name}: {error}"
            )

        self.__update_log_file(
            module=module,
            ptid=ptid,
            visitdate=visitdate,
            status=status,
            gear_name=self.__metadata.name,  # type: ignore
            errors=error_writer.errors(),
            reset_gears=[qc_gear_name],
        )

    def __update_log_file(
        self,
        *,
        module: str,
        ptid: str,
        visitdate: str,
        status: str,
        gear_name: str,
        errors: FileErrorList,
        reset_gears: Optional[List[str]] = None,
    ):
        """Updates the visit error log and add qc info metadata.

        Args:
            module: module
            ptid: PTID
            visitdate: visit date
            status: QC status
            gear_name: QC coordinator gear name
            errors: error object with failure info
            reset_gears (optional): list of gear names to reset QC metadata

        Raises:
            GearExecutionError: If failed to update log file
        """
        error_log_name = ErrorLogTemplate().instantiate(
            record={
                f"{FieldNames.PTID}": ptid,
                f"{FieldNames.DATE_COLUMN}": visitdate,
            },
            module=module,
        )

        if (
            not error_log_name
            or not self.__project
            or not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=ProjectAdaptor(
                    project=self.__project, proxy=self.__proxy
                ),
                gear_name=gear_name,
                state=status,
                errors=errors,
                reset_qc_metadata="GEAR",
            )
        ):
            raise GearExecutionError(
                f"Failed to update error log for visit {ptid}, {visitdate}"
            )

        if reset_gears:
            reset_error_log_metadata_for_gears(
                error_log_name=error_log_name,
                destination_prj=ProjectAdaptor(
                    project=self.__project, proxy=self.__proxy
                ),
                gear_names=reset_gears,
            )

    def __update_last_failed_visit(
        self,
        module: str,
        file_id: str,
        filename: str,
        visitdate: str,
        visitnum: Optional[str] = None,
    ):
        """Update last failed visit details in subject metadata.

        Args:
            module: module label of the failed visit
            file_id: Flywheel file id of the failed visit file
            filename: name of the failed visit file
            visitdate: visit date of the failed visit
            visitnum (optional): visit number of the failed visit
        """
        lfv = self.__subject.get_last_failed_visit(module=module)
        if not lfv or lfv.visitdate >= visitdate:
            visit_info = VisitInfo(
                file_id=file_id,
                filename=filename,
                visitdate=visitdate,
                visitnum=visitnum,
            )
            self.__subject.set_last_failed_visit(module, visit_info)

    def __get_matching_supplement_visit_file(
        self,
        *,
        supplement_module_info: SupplementModuleConfigs,
        visitdate: str,
        visitnum: Optional[str],
    ) -> Optional[FileEntry]:
        """Find the matching supplement visit for the current visit (i.e.
        respective UDS visit for LBD or FTLD submission)

        Note: This method assumes visit date in file metadata is normalized to
        YYYY-MM-DD format at a previous stage of the submission pipeline.

        Args:
            supplement_module_info: supplement module information
            visitdate: visit date for current input
            visitnum (optional): visit number for current input

        Returns:
            FileEntry(optional): matching supplement visit file if found
        """

        supplement_module = supplement_module_info.label
        supplement_date_field = supplement_module_info.date_field

        title = f"{supplement_module} visits for participant {self.__subject.label}"

        ptid_key = MetadataKeys.get_column_key(FieldNames.PTID)
        date_col_key = MetadataKeys.get_column_key(supplement_date_field)
        columns = [
            ptid_key,
            date_col_key,
            "file.name",
            "file.file_id",
            "file.parents.acquisition",
        ]
        filters = f"acquisition.label={supplement_module},{date_col_key}={visitdate}"

        if visitnum:
            visitnum_key = MetadataKeys.get_column_key(FieldNames.VISITNUM)
            columns.append(visitnum_key)
            filters += f",{visitnum_key}={visitnum}"

        # filters += (
        #     f",file.info.qc.{self.__qc_gear_info.gear_name}.validation.state=PASS"
        # )

        tags = [
            f"{self.__qc_gear_info.gear_name}-PASS",
            f"{self.__form_project_configs.legacy_qc_gear}-PASS",
        ]
        filters += f",file.tags=|[{','.join(tags)}]"

        log.info("Searching for supplement visits matching with %s", filters)
        matching_visits = self.__proxy.get_matching_acquisition_files_info(
            container_id=self.__subject.id,
            dv_title=title,
            columns=columns,
            filters=filters,
        )

        if not matching_visits:
            return None

        if len(matching_visits) > 1:
            raise GearExecutionError(
                "More than one matching visits found for search "
                f"{filters} on {self.__subject}/{self.__module}"
            )

        return self.__proxy.get_file(matching_visits[0]["file.file_id"])

    def __update_visit_metadata_on_failure(
        self,
        *,
        ptid: str,
        visit_file: FileEntry,
        visitdate: str,
        error_obj: FileError,
        visitnum: Optional[str] = None,
    ) -> None:
        """Set last failed visit and update QC error metadata. Reset QC status
        of dependent module visits if there's any.

        Args:
            ptid: PTID for this visit
            visit_file: Flywheel file object for the visit
            visitdate: visit date
            error_obj: error metadata to report
            visitnum: visit number
        """

        # set the first failed visit for this run
        # and update the last failed visit for the subject
        if not self.__failed_visit:
            self.__failed_visit = visit_file
            self.__update_last_failed_visit(
                module=self.__module,
                file_id=visit_file.file_id,
                filename=visit_file.name,
                visitdate=visitdate,
                visitnum=visitnum,
            )

        self.__update_qc_error_metadata(
            visit_file=visit_file,
            error_obj=error_obj,
            ptid=ptid,
            visitdate=visitdate,
            status="FAIL",
        )

        self.__reset_dependent_modules_qc_status(visitdate=visitdate, visitnum=visitnum)

    def __is_outdated_trigger(self, visit: Dict[str, str]) -> bool:
        """If triggered from finalization workflow, check whether the module
        file was validated after the trigger.

        Args:
            visit: current visit info

        Returns:
            bool: True if current visit was finalized after the trigger
        """

        log.info(f"Validating finalization trigger: {visit}")

        module_timestamp = visit.get(
            f"{self.__module}-{MetadataKeys.VALIDATED_TIMESTAMP}"
        )
        trigger_timestamp = visit.get(MetadataKeys.TRIGGERED_TIMESTAMP)

        if not module_timestamp or not trigger_timestamp:
            return False

        outdated = datetime.strptime(
            module_timestamp, DEFAULT_DATE_TIME_FORMAT
        ) >= datetime.strptime(trigger_timestamp, DEFAULT_DATE_TIME_FORMAT)
        if outdated:
            log.info(
                f"Ignoring outdated finalization trigger "
                f"for file {visit['file.name']}: "
                f"trigger timestamp {trigger_timestamp} - "
                f"visit last validated at timestamp {module_timestamp}"
            )

        return outdated

    def __get_visit_file_and_destination(
        self,
        *,
        visit: Dict[str, str],
        ptid_key: str,
        date_col_key: str,
        visitnum_key: str,
    ) -> Tuple[Optional[FileEntry], Optional[Acquisition]]:
        """Retrieve visit file and acquisition container from visit info.

        Args:
            visit: visit info

        Returns:
            Tuple[FileEntry, Acquisition]: file entry and acquisition container if found
        """

        file_id = visit["file.file_id"]
        filename = visit["file.name"]
        visitdate = visit[date_col_key]
        ptid = visit[ptid_key]
        visitnum = visit.get(visitnum_key)

        try:
            return (
                self.__proxy.get_file(visit["file.file_id"]),
                self.__proxy.get_acquisition(visit["file.parents.acquisition"]),
            )
        except ApiException as error:
            # can only update the log file since visit file cannot be found
            error_obj = system_error(
                message=f"Error retrieving file {visit['file.name']}: {error}",
                visit_keys=VisitKeys(ptid=ptid, visitnum=visitnum, date=visitdate),
            )
            error_obj.timestamp = (datetime.now()).strftime(DEFAULT_DATE_TIME_FORMAT)
            self.__update_log_file(
                module=self.__module,
                ptid=ptid,
                visitdate=visitdate,
                status="FAIL",
                gear_name=self.__metadata.name,  # type: ignore
                errors=FileErrorList([error_obj]),
            )
            self.__update_last_failed_visit(
                module=self.__module,
                file_id=file_id,
                filename=filename,
                visitdate=visitdate,
                visitnum=visitnum,
            )

            return None, None

    def __build_qc_gear_inputs(
        self,
        *,
        visit_file: FileEntry,
        ptid: str,
        visitdate: str,
        visitnum: Optional[str] = None,
        naccid: Optional[str] = None,
    ) -> Optional[Dict[str, FileEntry]]:
        """Populate the inputs required for QC gear, report errors if required
        input files cannot be found.

        Args:
            visit_file: current visit file
            ptid: participant identifier
            visitdate: visit date
            visitnum (optional): visit number
            naccid (optional): NACCID

        Returns:
            Dict[str, FileEntry (optional): gear input dictionary or None
        """

        inputs = {
            "form_data_file": visit_file,
            "form_configs_file": self.__configs_file,
        }

        supplement_module = self.__module_configs.supplement_module  # type: ignore

        # if supplement visit required check for approved supplement visit
        # i.e. UDS visit must be approved before processing any FTLD/LBD visits
        if supplement_module and supplement_module.exact_match:
            supplement_file = self.__get_matching_supplement_visit_file(
                supplement_module_info=supplement_module,
                visitdate=visitdate,
                visitnum=visitnum,
            )

            if not supplement_file:
                error_obj = preprocessing_error(
                    field=FieldNames.MODULE,
                    value=self.__module,
                    error_code=SysErrorCodes.UDS_NOT_APPROVED,
                    visit_keys=VisitKeys(
                        ptid=ptid, visitnum=visitnum, date=visitdate, naccid=naccid
                    ),
                )
                self.__update_visit_metadata_on_failure(
                    ptid=ptid,
                    visit_file=visit_file,
                    visitdate=visitdate,
                    visitnum=visitnum,
                    error_obj=error_obj,
                )
                return None

            inputs["supplement_data_file"] = supplement_file

        return inputs

    def __reset_module_visit_qc_status(
        self, *, module: str, visitdate: str, visit_info: Dict[str, str]
    ):
        """Reset the QC metadata of the dependent module visit file and
        respective error log file.

        Args:
            module: the dependent module to be reset
            visitdate: visit date
            visit_info: dependent module visit info
        """
        ptid_key = MetadataKeys.get_column_key(FieldNames.PTID)
        visitnum_key = MetadataKeys.get_column_key(FieldNames.VISITNUM)
        naccid_key = MetadataKeys.get_column_key(FieldNames.NACCID)

        file_id = visit_info["file.file_id"]
        file_name = visit_info["file.name"]
        visitnum = visit_info.get(visitnum_key)
        try:
            visit_file = self.__proxy.get_file(file_id)
        except ApiException as error:
            log.warning(
                "Failed to retrieve file, error metadata not reset for "
                f"dependent module visit {file_name}: {error}"
            )
            return

        ptid = visit_info[ptid_key]
        error_obj = preprocessing_error(
            field=FieldNames.MODULE,
            value=module,
            error_code=SysErrorCodes.UDS_NOT_APPROVED,
            visit_keys=VisitKeys(
                ptid=ptid,
                visitnum=visitnum,
                date=visitdate,
                naccid=visit_info.get(naccid_key),
            ),
        )

        self.__reset_qc_error_metadata(
            module=module,
            visit_file=visit_file,
            error_obj=error_obj,
            ptid=ptid,
            visitdate=visitdate,
            qc_gear_name=self.__qc_gear_info.gear_name,
            status="FAIL",
        )

        self.__update_last_failed_visit(
            module=module,
            file_id=file_id,
            filename=file_name,
            visitdate=visitdate,
            visitnum=visitnum,
        )

    def __reset_dependent_modules_qc_status(
        self, *, visitdate: str, visitnum: Optional[str] = None
    ):
        """Reset the QC metadata of any module visits dependent on the failed
        visit.

        Args:
            visitdate: visit date to match
            visitnum (optional): visit number to match

        Raises:
            GearExecutionError: if errors occur while resetting metadata
        """
        if not self.__dependent_modules:
            log.info(f"No dependent modules for current module {self.__module}")
            return

        for dep_module in self.__dependent_modules:
            dep_module_configs = self.__form_project_configs.module_configs.get(
                dep_module
            )

            if not dep_module_configs:
                raise GearExecutionError(
                    f"Failed to find module configs for dependent module {dep_module}"
                )

            matched_visits = (
                self.__visits_lookup_helper.find_module_visits_with_matching_visitdate(
                    module=dep_module,
                    module_configs=dep_module_configs,
                    visitdate=visitdate,
                    visitnum=visitnum,
                )
            )

            if not matched_visits:
                log.info(
                    f"No {dep_module} visits dependent on {self.__module} "
                    f"visit with visitdate: {visitdate} "
                    f"visitnum: {visitnum}"
                )
                continue

            if len(matched_visits) > 1:  # this cannot happen
                raise GearExecutionError(
                    f"Multiple {dep_module} visits found with "
                    f"visitdate: {visitdate} visitnum: {visitnum}"
                )

            self.__reset_module_visit_qc_status(
                module=dep_module, visitdate=visitdate, visit_info=matched_visits[0]
            )

    def run_error_checks(self, *, visits: List[Dict[str, str]]) -> None:
        """Sequentially trigger the QC checks gear on the provided visits. If a
        visit failed QC validation or error occurred while running the QC gear,
        none of the subsequent visits will be evaluated.

        Args:
            visits: set of visits to be evaluated

        Raises:
            GearExecutionError: if errors occur while triggering the QC gear
        """

        assert self.__module_configs, "module configurations cannot be null"

        ptid_key = MetadataKeys.get_column_key(FieldNames.PTID)
        date_col_key = MetadataKeys.get_column_key(self.__module_configs.date_field)
        visitnum_key = MetadataKeys.get_column_key(FieldNames.VISITNUM)
        naccid_key = MetadataKeys.get_column_key(FieldNames.NACCID)

        # sort the visits in the ascending order of visit date
        sorted_visits = sorted(visits, key=lambda d: d[date_col_key])
        visits_queue = deque(sorted_visits)

        while visits_queue:
            visit = visits_queue.popleft()
            filename = visit["file.name"]
            visitdate = visit[date_col_key]
            ptid = visit[ptid_key]
            visitnum = visit.get(visitnum_key)
            naccid = visit.get(naccid_key)

            # skip if module file was validated after the finalization trigger
            if self.__is_outdated_trigger(visit):
                continue

            visit_file, destination = self.__get_visit_file_and_destination(
                visit=visit,
                ptid_key=ptid_key,
                date_col_key=date_col_key,
                visitnum_key=visitnum_key,
            )
            if not visit_file or not destination:
                continue

            qc_gear_inputs = self.__build_qc_gear_inputs(
                visit_file=visit_file,
                ptid=ptid,
                visitdate=visitdate,
                visitnum=visitnum,
                naccid=naccid,
            )
            if not qc_gear_inputs:
                continue

            qc_gear_name = self.__qc_gear_info.gear_name
            job_id = trigger_gear(
                proxy=self.__proxy,
                gear_name=qc_gear_name,
                log_args=False,
                config=self.__qc_gear_info.configs.model_dump(),
                inputs=qc_gear_inputs,
                destination=destination,
            )

            # If failed to trigger QC gear, report system error
            if not job_id:
                error_obj = system_error(
                    message=f"Failed to trigger gear {qc_gear_name}",
                    visit_keys=VisitKeys(ptid=ptid, visitnum=visitnum, date=visitdate),
                )
                self.__update_visit_metadata_on_failure(
                    ptid=ptid,
                    visit_file=visit_file,
                    visitdate=visitdate,
                    visitnum=visitnum,
                    error_obj=error_obj,
                )
                continue

            log.info(
                "Gear %s queued for file %s - Job ID %s", qc_gear_name, filename, job_id
            )

            # If QC gear did not complete, report system error
            if not JobPoll.is_job_complete(self.__proxy, job_id):
                error_obj = system_error(
                    message=f"Errors occurred while running gear {qc_gear_name}",
                    visit_keys=VisitKeys(ptid=ptid, visitnum=visitnum, date=visitdate),
                )
                self.__update_visit_metadata_on_failure(
                    ptid=ptid,
                    visit_file=visit_file,
                    visitdate=visitdate,
                    visitnum=visitnum,
                    error_obj=error_obj,
                )
                continue

            self.__update_qc_error_metadata(
                visit_file=visit_file, ptid=ptid, visitdate=visitdate, status="PASS"
            )

            qc_passed = self.__passed_qc_checks(visit_file, qc_gear_name)
            if qc_passed:
                # Add the submission complete tag
                # (1) to trigger QC process on any dependent modules
                # (2) for reporting
                visit_file.add_tag(DefaultValues.FINALIZED_TAG)
            else:
                # If failed do we need to reset the dependent module QC status?
                self.__reset_dependent_modules_qc_status(
                    visitdate=visitdate, visitnum=visitnum
                )

            # continue to trigger the form-qc-checker for next visit
            # form-qc-checker will validate whether the previous visit has passed
