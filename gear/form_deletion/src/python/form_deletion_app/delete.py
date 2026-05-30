import logging
from datetime import datetime
from typing import Optional

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from deletions.models import DeletedItems, DeleteRequest
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import (
    FileVisitAnnotator,
    QCStatusLogManager,
)
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, SubjectAdaptor
from identifiers.model import IdentifierObject
from keys.keys import CLINICAL_MODULES, DefaultValues, MetadataKeys
from nacc_common.data_identification import DataIdentification
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import delete_request_failed_error

from form_deletion_app.helpers import AcquisitionRemover

log = logging.getLogger(__name__)


class FormDeletionProcessor:
    """Class to handle the form data delete request."""

    def __init__(
        self,
        *,
        project: ProjectAdaptor,
        adcid: int,
        delete_request: DeleteRequest,
        request_time: datetime,
        form_configs: FormProjectConfigs,
        error_writer: ListErrorWriter,
        identifier: Optional[IdentifierObject] = None,
        check_sbsq_visits: bool,
    ):
        """
        Args:
            project: FLywheel project adaptor
            adcid: Center's ADCID
            delete_request: delete request object
            request_time: delete request file timestamp
            form_configs: form ingest configs
            error_writer: Error writer to record any errors
            identifier: IdentifierObject if exists
            check_sbsq_visits: Check whether there are any subsequent QC passed visits
        """
        self.__project = project
        self.__adcid = adcid
        self.__form_configs = form_configs
        self.__error_writer = error_writer
        self.__delete_request = delete_request
        self.__request_time = request_time
        self.__identifier = identifier
        self.__naccid = identifier.naccid if identifier else None
        self.__check_sbsq_visits = check_sbsq_visits
        self.__module = delete_request.module.upper()

        self.__dependent_modules = form_configs.get_module_dependencies(
            module=self.__module, exact_match=False
        )

        self.__qc_log_manager = QCStatusLogManager(
            error_log_template=ErrorLogTemplate(),
            visit_annotator=FileVisitAnnotator(project),
        )

        self.__deleted_items: DeletedItems = DeletedItems()

        self.__acq_remover: Optional[AcquisitionRemover] = None

    @property
    def deleted_items(self) -> DeletedItems:
        """Returns the items deleted while processing the delete request."""
        return self.__deleted_items

    def __get_error_log_name(self, module: str) -> Optional[str]:
        """Returns the QC errorlog filename for this delete request.

        Args:
            module: module name

        Returns:
            Optional[str]: errorlog filename for the module or None.
        """
        visit_keys = DataIdentification.from_visit_metadata(
            adcid=self.__adcid,
            ptid=self.__delete_request.ptid,
            date=self.__delete_request.visitdate,
            naccid=self.__naccid,
            visitnum=self.__delete_request.visitnum,
            module=module,
        )

        return self.__qc_log_manager.get_qc_log_filename(
            visit_keys=visit_keys, project=self.__project
        )

    def __is_log_modified_after_request(self, log_file: FileEntry) -> bool:
        """Returns True if the log file was last modified after the delete
        request timestamp.

        Args:
            log_file: the error log file entry
        Returns:
            True if the log was modified before the request timestamp
        """
        if log_file.modified > self.__request_time:
            log.warning(
                f"Delete request timestamp: {self.__request_time}, "
                f"Log file {log_file.name} modified timestamp: {log_file.modified}"
            )
            return True

        return False

    def __add_delete_failed_error(self, message: str) -> None:
        """Writes a delete request failed error to the error writer.

        Args:
            message: the error message
        """
        log.error(message)
        self.__error_writer.write(
            delete_request_failed_error(
                ptid=self.__delete_request.ptid,
                visitdate=self.__delete_request.visitdate,
                visitnum=self.__delete_request.visitnum,
                naccid=self.__naccid,
                message=message,
            )
        )

    def __delete_error_log(self, filename: str) -> bool:
        """Deletes the error log file from the project.

        Args:
            filename: the error log filename to delete
        Returns:
            True if successfully deleted, False otherwise
        """
        return self.__project.delete_file(filename)

    def __cleanup_log_files(self, error_log_name: str) -> bool:
        """Deletes the error log for the current module and any dependent
        module logs that exist.

        Args:
            error_log_name: the primary module's error log filename

        Returns:
            True if all deletions succeeded, False if any failed
        """
        log.info(
            f"Removing log files for PTID {self.__delete_request.ptid}, "
            f"visitdate {self.__delete_request.visitdate}"
        )

        success = True
        # Remove any associated module log files first
        if self.__dependent_modules:
            log.info(f"Checking for associated module log files for {error_log_name}")
            for dep_module in self.__dependent_modules:
                dep_module_log_name = self.__get_error_log_name(module=dep_module)
                if not dep_module_log_name:
                    self.__add_delete_failed_error(
                        f"Failed to derive the error log name for module {dep_module}"
                    )
                    success = False
                    continue

                errorlog_file = self.__project.get_file(name=dep_module_log_name)
                if not errorlog_file:  # this is possible
                    log.info(f"No {dep_module} log file found for this delete request")
                    continue

                # No need to check the return value or add an error
                # Dependent modules will be deleted anyway
                # Calling the method to add a log entry
                self.__is_log_modified_after_request(errorlog_file)

                if not self.__delete_error_log(filename=dep_module_log_name):
                    self.__add_delete_failed_error(
                        "Failed to delete the log file for the"
                        f" associated module {dep_module}"
                    )
                    success = False
                    continue

                self.__deleted_items.logs.append(dep_module_log_name)

        if not self.__delete_error_log(filename=error_log_name):
            self.__add_delete_failed_error(
                "Failed to delete the log file for the requested visit"
            )
            return False

        self.__deleted_items.logs.append(error_log_name)

        return success

    def __has_matching_acquisition_files(
        self, subject: SubjectAdaptor, module_configs: ModuleConfigs
    ) -> int:
        """Check whether there's a matching acquisition file for the delete
        request.

        Args:
            subject: Flywheel subject adaptor
            module_configs: Module configs for the primary module

        Returns:
            int: Number of matching acquisition files
        """
        date_col_key = MetadataKeys.get_column_key(module_configs.date_field)
        visitnum_key = MetadataKeys.get_column_key(FieldNames.VISITNUM)
        columns = [
            "file.name",
            "file.file_id",
            "file.parents.acquisition",
            date_col_key,
        ]
        filters = f"acquisition.label={self.__module}"
        filters += f",{date_col_key}={self.__delete_request.visitdate}"

        if FieldNames.VISITNUM in module_configs.required_fields:
            columns.append(visitnum_key)
            filters += f",{visitnum_key}={self.__delete_request.visitnum}"

        log.info(f"Searching for an acquisition file matching with {filters}")

        results = self.__project.proxy.get_matching_acquisition_files_info(
            container_id=subject.id,
            dv_title=f"{self.__module} visits for {self.__delete_request.visitdate}",
            columns=columns,
            filters=filters,
        )

        if not results:
            return 0

        return len(results)

    def __has_qc_passed_subsequent_visits(
        self, subject: SubjectAdaptor, module_configs: ModuleConfigs
    ) -> bool:
        """Check whether the participant has any QC passed subsequent visits
        after the visit requested to be deleted.

        Args:
            subject: Flywheel subject adaptor
            module_configs: Module configs for the primary module

        Returns:
            bool: True if any subsequent visits found for the module
        """
        date_col_key = MetadataKeys.get_column_key(module_configs.date_field)
        columns = [
            "file.name",
            "file.file_id",
            "file.parents.acquisition",
            date_col_key,
        ]
        filters = f"acquisition.label={self.__module}"
        filters += f",{date_col_key}>{self.__delete_request.visitdate}"
        filters += f",file.info.qc.{DefaultValues.QC_GEAR}.validation.state=PASS"

        results = self.__project.proxy.get_matching_acquisition_files_info(
            container_id=subject.id,
            dv_title=f"{self.__module} visits after {self.__delete_request.visitdate}",
            columns=columns,
            filters=filters,
        )

        if results:
            log.warning(
                f"Found {len(results)} {self.__module} visits after "
                f"{self.__delete_request.visitdate} in {subject.label}"
            )
            return True

        return False

    def __has_remaining_clinical_forms(self, subject: SubjectAdaptor) -> bool:
        """Check if any UDS, MDS, or BDS acquisitions remain for the subject in
        the ingest project or the retrospective project.

        Args:
            subject: Subject adaptor object in ingest project

        Returns:
            True if at least one clinical form exists, False otherwise
        """

        filters = (
            f"acquisition.label{DefaultValues.FW_SEARCH_OR}"
            f"[{','.join(CLINICAL_MODULES)}]"
        )
        columns = ["file.name", "file.file_id"]

        results = self.__project.proxy.get_matching_acquisition_files_info(
            container_id=subject.id,
            dv_title=f"Clinical forms for {self.__naccid}",
            columns=columns,
            filters=filters,
        )
        if results:
            return True

        retro_project_label = self.__project.label.replace(
            DefaultValues.FORM_PRJ_LABEL, DefaultValues.LEGACY_PRJ_LABEL
        )
        retro_projects = self.__project.proxy.find_projects(
            group_id=self.__project.group, project_label=retro_project_label
        )
        if not retro_projects:
            return False

        retro_subject = retro_projects[0].subjects.find_first(f"label={self.__naccid}")
        if not retro_subject:
            return False

        results = self.__project.proxy.get_matching_acquisition_files_info(
            container_id=retro_subject.id,
            dv_title=f"Clinical forms for {self.__naccid}",
            columns=columns,
            filters=filters,
        )

        return bool(results)

    def __cleanup_orphan_module_errorlogs(self) -> bool:
        """Deletes the error logs file for the orphaned module from the ingest
        project.

        Note: This method uses the list of orphaned visit info populated
        while removing any orphaned acquisitions.

        Returns:
            True if all deletions succeeded, False otherwise
        """

        if not self.__acq_remover:
            return True

        success = True
        for visit_keys in self.__acq_remover.get_orphaned_visit_details():
            orphaned_module = visit_keys.module
            log_name = self.__qc_log_manager.get_qc_log_filename(
                visit_keys=visit_keys, project=self.__project
            )
            if not log_name:
                log.error(
                    "Failed to derive the error log name for orphaned visit "
                    f"{orphaned_module}/{visit_keys.date}"
                )
                success = False
                continue

            errorlog_file = self.__project.get_file(name=log_name)
            if not errorlog_file:
                log.warning(
                    f"No error log found for orphaned visit "
                    f"{orphaned_module}/{visit_keys.date}"
                )
                continue

            # No need to check the return value or add an error
            # Orphaned visits are deleted anyway
            # Calling the method to add a log entry
            self.__is_log_modified_after_request(errorlog_file)

            if not self.__delete_error_log(filename=log_name):
                log.error(f"Failed to delete orphaned error log {log_name}")
                success = False
                continue

            self.__deleted_items.logs.append(log_name)

        return success

    def __cleanup_acquisitions(self) -> bool:
        """Finds the subject in the project and removes its acquisitions,
        including any NP/MLST acquisitions that become orphaned as a result.

        Returns:
            True if all operations succeeded (or subject not found), False on
            any error
        """
        if not self.__naccid:
            log.info("NACCID does not exist, skip looking up acquisitions")
            return True

        subject = self.__project.find_subject(self.__naccid)
        if not subject:
            log.info(
                "Subject does not exist in ingest project, skip looking up acquisitions"
            )
            return True

        module_configs = self.__form_configs.module_configs.get(self.__module)
        if not module_configs:
            self.__add_delete_failed_error(
                f"No module configs found for module {self.__module}"
            )
            return False

        if (
            FieldNames.VISITNUM in module_configs.required_fields
            and not self.__delete_request.visitnum
        ):
            self.__add_delete_failed_error(
                "Require visitnum to process delete requests "
                f"for module {self.__module}"
            )
            return False

        # check for matching acquisition files, do this before subsequent visit check
        num_matches = self.__has_matching_acquisition_files(
            subject=subject, module_configs=module_configs
        )

        if num_matches == 0:  # no acquisition to clean
            log.info(
                "No matching acquisitions found in ingest project, "
                "skipping acquisition cleanup"
            )
            return True

        if num_matches > 1:
            self.__add_delete_failed_error(
                f"Multiple matching acquisition files ({num_matches}) "
                "found for the delete request"
            )
            return False

        # For longitudinal modules, check whether there are any QC passed
        # subsequent visits. To bypass this check, set
        # longitudinal_check=False in gear configs.
        if (
            self.__check_sbsq_visits
            and module_configs.longitudinal
            and self.__has_qc_passed_subsequent_visits(
                subject=subject, module_configs=module_configs
            )
        ):
            self.__add_delete_failed_error("Subject has QC passed subsequent visits")
            return False

        self.__acq_remover = AcquisitionRemover(
            proxy=self.__project.proxy,
            primary_project_id=self.__project.id,
            module=self.__module,
            naccid=self.__naccid,
            form_configs=self.__form_configs,
            module_configs=module_configs,
            delete_request=self.__delete_request,
            deleted_items=self.__deleted_items,
            dependent_modules=self.__dependent_modules,
        )

        if not self.__acq_remover.cleanup_acquisitions():
            self.__add_delete_failed_error(
                "Failed to remove the acquisition files for this delete request"
            )
            return False

        return True

    def __remove_orphaned_modules(self) -> bool:
        """If the deleted module was a clinical form (UDS/MDS/BDS) and no
        clinical forms remain for the subject, removes all NP and MLST
        acquisitions and their error logs.

        the AcquisitionRemover used for the primary deletion
        is reused to remove orphaned acquisitions

        Returns:
            True if nothing to do or all removals succeeded, False otherwise
        """
        if not self.__naccid or not self.__acq_remover:
            return True

        subject = self.__project.find_subject(label=self.__naccid)
        if not subject:  # subject removed during delete process
            return True

        if self.__module not in CLINICAL_MODULES:
            return True

        # More clinical forms present in the subject
        if self.__has_remaining_clinical_forms(subject=subject):
            return True

        orphan_modules = self.__form_configs.get_modules_dependent_on_clinical_forms()
        if not orphan_modules:
            return True

        log.info(
            f"No clinical forms remain for {self.__naccid}, "
            f"removing orphaned {orphan_modules} acquisitions"
        )

        success = True
        acquisitions_removed = self.__acq_remover.cleanup_orphaned_acquisitions(
            orphan_modules
        )
        if not acquisitions_removed:
            self.__add_delete_failed_error(
                f"Failed to remove orphaned {orphan_modules} acquisitions"
            )
            success = False

        if not self.__cleanup_orphan_module_errorlogs():
            self.__add_delete_failed_error(
                f"Failed to remove orphaned {orphan_modules} log files"
            )
            success = False

        return success

    def process_request(self) -> bool:
        """Process delete request.

        Returns:
            bool: True if success, else False
        """

        if self.__identifier and not self.__identifier.active:
            # Reject the request if participant is inactive (i.e. transferred),
            #   need to handle this manually
            self.__add_delete_failed_error(
                f"Participant {self.__naccid} is inactive in center {self.__adcid}"
            )
            return False

        error_log_name = self.__get_error_log_name(module=self.__module)
        if not error_log_name:
            self.__add_delete_failed_error(
                f"Failed to derive the error log name for module {self.__module}"
            )
            return False

        errorlog_file = self.__project.get_file(name=error_log_name)
        if not errorlog_file:
            self.__add_delete_failed_error(
                "Failed to find a matching log file for the visit to be deleted"
            )
            return False

        if self.__is_log_modified_after_request(errorlog_file):
            self.__add_delete_failed_error(
                "The visit to be deleted was modified after"
                " the delete request was submitted"
            )
            return False

        if not self.__cleanup_acquisitions():
            log.error("Failed to clean up acquisition files")
            return False

        if not self.__cleanup_log_files(error_log_name=error_log_name):
            log.error("Failed to clean up error log files")
            return False

        # When a clinical form is deleted, remove any modules/forms
        # that have become orphaned.
        # e.g. MLST or NP need an existing UDS/MDS/BDS form
        return self.__remove_orphaned_modules()
