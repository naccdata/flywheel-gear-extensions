"""Defines Form Deletion."""

import logging
from datetime import datetime, timezone
from typing import Optional

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
from notifications.email import EmailClient, create_ses_client
from outputs.error_writer import ListErrorWriter

from form_deletion_app.delete import FormDeletionProcessor

log = logging.getLogger(__name__)


# TODO - change this to use a template
def send_email(
    sender_email: str,
    delete_request: DeleteRequest,
    success: bool,
    deleted_visits: Optional[str] = None,
) -> None:
    """Send an email notifying the user the result of the delete request.

    Args:
        sender_email: Source email to send the notification
        delete_request: Delete request information
        success: Status of the delete request
        deleted_visits: Info on visits deleted while processing the request
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    status = "COMPLETE" if success else "FAILED"

    subject = (
        f"[NACC Data Platform] Delete Request for PTID {delete_request.ptid} - {status}"
    )

    body = (
        f"\n\nDelete request details:\n\n"
        f"PTID: {delete_request.ptid}\n"
        f"MODULE: {delete_request.module.upper()}\n"
        f"VISIT DATE / FORM DATE: {delete_request.visitdate}\n"
    )

    if delete_request.visitnum:
        body += f"VISITNUM: {delete_request.visitnum}\n"

    if success and deleted_visits:
        body += (
            "\nForm data delete request listed above was successfully processed.\n"
            "List of deleted forms/modules:\n"
            f"{deleted_visits}\n\n"
            "If you need to resubmit this data, "
            "please make sure to reupload any associated modules listed above.\n\n"
            "Please contact nacchelp@uw.edu if you have any questions\n\n"
        )
    else:
        body += (
            "\nErrors occurred while processing the "
            "form data delete request listed above.\n"
            "Please contact nacchelp@uw.edu for assistance\n\n"
        )

    target_email = delete_request.requested_by
    client.send_raw(destinations=[target_email], subject=subject, body=body)


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

    delete_response = DeleteResponse(
        errors=errors.list(), deleted=deleted_items, state="PASS" if success else "FAIL"
    )
    delete_info = DeleteInfoModel(
        delete_response=delete_response, processed_timestamp=datetime.now(timezone.utc)
    )

    try:
        update_file_info(file=input_file, custom_info=delete_info.model_dump())
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
    sender_email: str,
):
    """Process the form data delete request.

    Args:
        project: Flywheel project adaptor
        adcid: ADCID
        input_file: FileEntry object for input file
        delete_request: Delete request details
        form_configs: Form ingest configs
        identifiers_repo: Identifier repository
        sender_email: Source email to send the notification
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
    )

    success = processor.process_request()

    update_file_metadata(
        input_file=input_file,
        success=success,
        deleted_items=processor.deleted_items,
        errors=error_writer.errors().model_dump(by_alias=True),
    )

    deleted_visits_str = processor.get_deleted_visits_list() if success else None
    send_email(
        sender_email=sender_email,
        delete_request=delete_request,
        success=success,
        deleted_visits=deleted_visits_str,
    )
