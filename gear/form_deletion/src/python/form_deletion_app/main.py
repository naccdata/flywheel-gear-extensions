"""Defines Form Deletion."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from configs.ingest_configs import FormProjectConfigs
from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from error_logging.error_logger import update_file_info
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from identifiers.identifiers_repository import IdentifierRepository
from identifiers.query import find_naccid
from nacc_common.error_models import FileErrorList, FileQCModel, QCStatus
from notifications.email import EmailClient, create_ses_client
from outputs.error_writer import ListErrorWriter
from submissions.models import DeleteRequest

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
        sender_email: The sender email
        target_email: The target email
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    status = "COMPLETE" if success else "FAILED"

    subject = (
        f"[NACC Data Platform] Delete Request for PTID {delete_request.ptid} - {status}"
    )
    visits_section = f"\n\nDeleted visits:\n{deleted_visits}" if deleted_visits else ""
    body = (
        f"\n\nForm data delete request details: \n\n"
        f"{delete_request}\n\n{visits_section}"
    )

    target_email = delete_request.requested_by
    client.send_raw(destinations=[target_email], subject=subject, body=body)


def update_file_metadata(
    *,
    input_file: FileEntry,
    success: bool,
    deleted_items: Dict[str, List[str]],
    errors: FileErrorList,
) -> None:
    """_summary_

    Args:
        input_file (FileEntry): _description_
        success (bool): _description_
        deleted_items (Dict[str, List[str]]): _description_
        errors (FileErrorList): _description_
    """
    status: QCStatus = "PASS" if success else "FAIL"
    qc_info: FileQCModel = FileQCModel(qc={})
    qc_info.set_errors(gear_name="form-deletion", status=status, errors=errors)

    custom_info = qc_info.model_dump(by_alias=True)
    if deleted_items:
        custom_info["deleted"] = deleted_items
    timestamp = (datetime.now(timezone.utc)).strftime(DEFAULT_DATE_TIME_FORMAT)
    custom_info["processed-timestamp"] = timestamp

    try:
        update_file_info(file=input_file, custom_info=custom_info)
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
        project (ProjectAdaptor): _description_
        adcid (int): _description_
        input_file: FileEntry object for input file
        delete_request (DeleteRequest): _description_
        module_configs (ModuleConfigs): _description_
        identifiers_repo (IdentifierRepository): _description_
        sender_email (str): _description_
    """

    ptid = delete_request.ptid
    naccid = find_naccid(
        repo=identifiers_repo, adcid=adcid, ptid=ptid, active_only=False
    )
    error_writer = ListErrorWriter(
        container_id=input_file.file_id,
        fw_path=project.proxy.get_lookup_path(input_file),
    )
    processor = FormDeletionProcessor(
        project=project,
        adcid=adcid,
        delete_request=delete_request,
        form_configs=form_configs,
        error_writer=error_writer,
        naccid=naccid,
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
