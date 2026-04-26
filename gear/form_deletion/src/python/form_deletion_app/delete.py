import logging
from datetime import datetime
from typing import Optional

from configs.ingest_configs import FormProjectConfigs
from deletions.models import DeletedItems, DeleteRequest
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import (
    FileVisitAnnotator,
    QCStatusLogManager,
)
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from identifiers.model import IdentifierObject
from nacc_common.data_identification import DataIdentification
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
        """
        self.__project = project
        self.__adcid = adcid
        self.__form_configs = form_configs
        self.__error_writer = error_writer
        self.__delete_request = delete_request
        self.__request_time = request_time
        self.__identifier = identifier
        self.__naccid = identifier.naccid if identifier else None
        self.__module = delete_request.module.upper()

        self.__dependent_modules = form_configs.get_module_dependencies(
            module=self.__module
        )

        self.__qc_log_manager = QCStatusLogManager(
            error_log_template=ErrorLogTemplate(),
            visit_annotator=FileVisitAnnotator(project),
        )

        self.__deleted_items: DeletedItems = DeletedItems()

    @property
    def deleted_items(self) -> DeletedItems:
        """Returns the items deleted while processing the delete request."""
        return self.__deleted_items

    def get_deleted_visits_list(self) -> Optional[str]:
        """Returns the list of deleted visits as a newline-joined string.

        Example log file names:     Form with visitnum:         →
        12345_2024-01-15_001_uds_qc-status.log     Form without visitnum
        (non-visit form):         → 12345_2024-01-15_np_qc-status.log
        Old format (no visitnum):         → 12345_2024-01-15_uds_qc-
        status.log
        """

        visits = []

        for logfile in self.deleted_items.logs:
            if not logfile.endswith(".log"):
                continue
            segments = logfile.split("_")
            num_segments = len(segments)
            if num_segments < 4 or num_segments > 5:
                continue
            ptid = segments[0]
            date = segments[1]
            visitnum = segments[2] if num_segments == 5 else None
            module = segments[-2].upper()
            visit_str = f"ptid={ptid}, module={module}, date={date}"
            if visitnum:
                visit_str += f", visitnum={visitnum}"
            visits.append(visit_str)

        return "\n".join(visits) if visits else None

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

    def process_request(self) -> bool:
        """Process delete request.

        Returns:
            bool: True if success, else False
        """

        if self.__identifier and not self.__identifier.active:
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

        # If subject exists in the project, remove the respective acquisitions
        if self.__naccid and self.__project.find_subject(self.__naccid):
            module_configs = self.__form_configs.module_configs.get(self.__module)
            if not module_configs:
                self.__add_delete_failed_error(
                    f"No module configs found for module {self.__module}"
                )
                return False

            acq_remover = AcquisitionRemover(
                proxy=self.__project.proxy,
                module=self.__module,
                naccid=self.__naccid,
                form_configs=self.__form_configs,
                module_configs=module_configs,
                delete_request=self.__delete_request,
                deleted_items=self.__deleted_items,
                dependent_modules=self.__dependent_modules,
            )

            if not acq_remover.cleanup_acquisitions():
                self.__add_delete_failed_error(
                    "Failed to remove the acquisition files for this delete request"
                )
                return False

        return self.__cleanup_log_files(error_log_name=error_log_name)
