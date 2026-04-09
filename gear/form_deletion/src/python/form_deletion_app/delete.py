import logging
from typing import Optional

from configs.ingest_configs import ModuleConfigs
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import (
    FileVisitAnnotator,
    QCStatusLogManager,
)
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
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
        module_configs: ModuleConfigs,
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
        self.__module_configs = module_configs
        self.__error_writer = error_writer
        self.__delete_request = delete_request
        self.__naccid = naccid

        self.__qc_log_manager = QCStatusLogManager(
            error_log_template=ErrorLogTemplate(),
            visit_annotator=FileVisitAnnotator(project),
        )

    def process_request(self) -> bool:
        visit_keys = DataIdentification.from_visit_metadata(
            adcid=self.__adcid,
            ptid=self.__delete_request.ptid,
            date=self.__delete_request.visitdate,
            naccid=self.__naccid,
            visitnum=self.__delete_request.visitnum,
            module=self.__delete_request.module,
        )

        error_log_name = self.__qc_log_manager.get_qc_log_filename(
            visit_keys=visit_keys, project=self.__project
        )

        if not error_log_name:
            self.__error_writer.write(
                delete_request_failed_error(
                    ptid=self.__delete_request.ptid,
                    visitdate=self.__delete_request.visitdate,
                    visitnum=self.__delete_request.visitnum,
                    naccid=self.__naccid,
                    message="Failed to create error log file name for this request",
                )
            )
            return False

        return True
