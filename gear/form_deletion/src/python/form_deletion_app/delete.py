import logging
from typing import Optional

from configs.ingest_configs import FormProjectConfigs
from datastore.forms_store import FormsStore
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import (
    FileVisitAnnotator,
    QCStatusLogManager,
)
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from nacc_common.data_identification import DataIdentification
from outputs.error_writer import ListErrorWriter
from outputs.errors import delete_request_failed_error
from submissions.models import DeleteRequest

log = logging.getLogger(__name__)


class FormDeletionProcessor:
    """Class to handle the form data delete request."""

    def __init__(
        self,
        *,
        project: ProjectAdaptor,
        adcid: int,
        delete_request: DeleteRequest,
        form_configs: FormProjectConfigs,
        error_writer: ListErrorWriter,
        naccid: Optional[str] = None,
    ):
        """
        Args:
            project (ProjectAdaptor): _description_
            adcid (int): _description_
            delete_request (DeleteRequest): _description_
            module_configs (ModuleConfigs): _description_
            naccid:
        """
        self.__project = project
        self.__adcid = adcid
        self.__form_configs = form_configs
        self.__error_writer = error_writer
        self.__delete_request = delete_request
        self.__naccid = naccid
        self.__module = delete_request.module.upper()

        self.__dependent_modules = form_configs.get_module_dependencies(
            module=self.__module
        )

        self.__forms_store = FormsStore(ingest_project=project)

        self.__qc_log_manager = QCStatusLogManager(
            error_log_template=ErrorLogTemplate(),
            visit_annotator=FileVisitAnnotator(project),
        )

    def __get_subject(self) -> Optional[SubjectAdaptor]:
        """Returns the subject whose label matches naccid, or None."""
        if not self.__naccid:
            return None
        return self.__project.find_subject(self.__naccid)

    def __get_error_log_name(self, module: str) -> Optional[str]:
        """Returns the QC errorlog filename for this delete request.

        Args:
            module (str): module name

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

        error_log_name = self.__qc_log_manager.get_qc_log_filename(
            visit_keys=visit_keys, project=self.__project
        )

        if not error_log_name:
            self.__add_delete_failed_error(
                "Failed to find the respective log file name for"
                " the visit to be deleted"
            )

        return error_log_name

    def __is_log_modified_after_request(self, log_file: FileEntry) -> bool:
        """Returns True if the log file was last modified after the delete
        request timestamp.

        Args:
            log_file: the error log file entry
        Returns:
            True if the log was modified before the request timestamp
        """
        if log_file.modified > self.__delete_request.timestamp:
            log.warning(
                f"Delete request timestamp: {self.__delete_request.timestamp}, "
                f"Log file {log_file.name} modified timestamp: {log_file.modified}"
            )
            return True

        return False

    def __add_delete_failed_error(self, message: str) -> None:
        """Writes a delete request failed error to the error writer.

        Args:
            message: the error message
        """
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
        success = self.__delete_error_log(filename=error_log_name)
        if not success:
            self.__add_delete_failed_error(
                "Failed to delete the log file for the requested visit"
            )

        if not self.__dependent_modules:
            return success

        log.info("Checking for associated module log files")
        for dep_module in self.__dependent_modules:
            dep_module_log_name = self.__get_error_log_name(module=dep_module)
            if not dep_module_log_name:
                continue

            errorlog_file = self.__project.get_file(name=dep_module_log_name)
            if not errorlog_file:
                log.info("No %s visit found for this delete request", dep_module)
                continue

            # No need to check the return value or add an error
            # Dependent modules will be deleted anyway
            self.__is_log_modified_after_request(errorlog_file)

            if not self.__delete_error_log(filename=dep_module_log_name):
                self.__add_delete_failed_error(
                    "Failed to delete the log file for the"
                    f" associated module {dep_module}"
                )
                success = False

        return success

    def process_request(self) -> bool:
        error_log_name = self.__get_error_log_name(module=self.__module)
        if not error_log_name:
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

        return self.__cleanup_log_files(error_log_name=error_log_name)
