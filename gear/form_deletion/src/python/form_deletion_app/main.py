"""Defines Form Deletion."""

import logging

from configs.ingest_configs import ModuleConfigs
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from identifiers.identifiers_repository import IdentifierRepository
from identifiers.query import find_naccid
from notifications.email import EmailClient, create_ses_client
from outputs.error_writer import ListErrorWriter
from submissions.models import DeleteRequest

from form_deletion_app.delete import FormDeletionProcessor

log = logging.getLogger(__name__)


# TODO - change this to use a template
def send_email(sender_email: str, delete_request: DeleteRequest, status: str) -> None:
    """Send an email notifying the user the result of the delete request.

    Args:
        sender_email: The sender email
        target_email: The target email
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    subject = (
        f"[NACC Data Platform] Delete Request for PTID {delete_request.ptid} - {status}"
    )
    body = f"\n\nForm data delete request details: \n\n{delete_request}\n\n"

    target_email = delete_request.requested_by
    client.send_raw(destinations=[target_email], subject=subject, body=body)


def run(
    *,
    project: ProjectAdaptor,
    adcid: int,
    delete_request: DeleteRequest,
    module_configs: ModuleConfigs,
    identifiers_repo: IdentifierRepository,
    error_writer: ListErrorWriter,
    sender_email: str,
):
    """Process the form data delete request.

    Args:
        project (ProjectAdaptor): _description_
        adcid (int): _description_
        delete_request (DeleteRequest): _description_
        module_configs (ModuleConfigs): _description_
        identifiers_repo (IdentifierRepository): _description_
        sender_email (str): _description_
    """

    ptid = delete_request.ptid
    naccid = find_naccid(
        repo=identifiers_repo, adcid=adcid, ptid=ptid, active_only=False
    )
    processor = FormDeletionProcessor(
        project=project,
        adcid=adcid,
        delete_request=delete_request,
        module_configs=module_configs,
        error_writer=error_writer,
        naccid=naccid,
    )

    status = "COMPLETE" if processor.process_request() else "FAILED"
    send_email(sender_email=sender_email, delete_request=delete_request, status=status)
