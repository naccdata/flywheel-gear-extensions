"""Defines Form Deletion."""

import logging
from datetime import UTC, datetime

from configs.ingest_configs import FormProjectConfigs
from deletions.models import (
    DeletedItems,
    DeleteInfoModel,
    DeleteRequest,
    DeleteResponse,
)
from error_logging.error_logger import update_file_info
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from identifiers.identifiers_repository import IdentifierRepository
from identifiers.query import find_identifier
from nacc_common.error_models import FileErrorList
from outputs.error_writer import ListErrorWriter

from form_deletion_app.delete import FormDeletionProcessor

log = logging.getLogger(__name__)


def update_file_metadata(
    *,
    input_file: FileEntry,
    success: bool,
    deleted_items: DeletedItems,
    errors: FileErrorList,
) -> None:
    """Save the response details in the file.info metadata of the request file.

    Args:
        input_file: Delete request file
        success: Status of the request
        deleted_items: Information on the deleted items (if any)
        errors: Errors occurred while processing the delete request (if any)
    """

    status = "PASS" if success else "FAIL"
    delete_response = DeleteResponse(
        errors=errors.list(), deleted=deleted_items, state=status
    )
    delete_info = DeleteInfoModel(
        delete_response=delete_response, processed_timestamp=datetime.now(UTC)
    )

    try:
        update_file_info(
            file=input_file, custom_info=delete_info.model_dump(by_alias=True)
        )
        log.info(
            f"Saved response details in file info metadata {input_file.name}, "
            f"status: {status}"
        )
    except ApiException as error:
        log.error(
            f"Error in updating custom info metadata in file {input_file.name}: {error}"
        )


def run(
    *,
    project: ProjectAdaptor,
    adcid: int,
    input_file: FileEntry,
    delete_request: DeleteRequest,
    form_configs: FormProjectConfigs,
    identifiers_repo: IdentifierRepository,
    check_sbsq_visits: bool,
):
    """Process the form data delete request.

    Args:
        project: Flywheel project adaptor
        adcid: ADCID
        input_file: FileEntry object for input file
        delete_request: Delete request details
        form_configs: Form ingest configs
        identifiers_repo: Identifier repository
        check_sbsq_visits: Check whether there are any subsequent QC passed visits
    """

    error_writer = ListErrorWriter(
        container_id=input_file.file_id,
        fw_path=project.proxy.get_lookup_path(input_file),
    )

    identifier = find_identifier(
        repo=identifiers_repo, adcid=adcid, ptid=delete_request.ptid
    )

    processor = FormDeletionProcessor(
        project=project,
        adcid=adcid,
        delete_request=delete_request,
        request_time=input_file.modified,
        form_configs=form_configs,
        error_writer=error_writer,
        identifier=identifier,
        check_sbsq_visits=check_sbsq_visits,
    )

    success = processor.process_request()

    update_file_metadata(
        input_file=input_file,
        success=success,
        deleted_items=processor.deleted_items,
        errors=error_writer.errors(),
    )
