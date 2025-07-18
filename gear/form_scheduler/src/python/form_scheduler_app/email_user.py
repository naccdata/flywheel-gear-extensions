"""Handles emailing user on completion of their submission pipeline."""

import logging

from flywheel import Project
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from inputs.parameter_store import URLParameter
from notifications.email import (
    BaseTemplateModel,
    DestinationModel,
    EmailClient,
)

log = logging.getLogger(__name__)


class SubmissionCompleteTemplateModel(BaseTemplateModel):
    """Submission complete template model."""

    first_name: str
    file_name: str
    center_name: str
    portal_url: str


def send_email(
    proxy: FlywheelProxy,
    email_client: EmailClient,
    file: FileEntry,
    project: Project,
    portal_url: URLParameter,
) -> None:
    """Sends an email notifying user that their submission pipeline has
    completed.

    Args:
        proxy: the proxy for the Flywheel instance
        email_client: EmailClient to send emails from
        file: The FileEntry object to will pull details
        project: Flywheel project container
        portal_url: The portal URL
    """

    user_id = file.info.get("uploader")
    if not user_id:
        log.warning("Uploader ID not available in file custom info for %s", file.name)
        if file.origin.type != "user":
            log.warning(
                "File %s is generated by non-user origin %s, "
                "will not send completion email",
                file.name,
                file.origin.id,
            )
            return

        user_id = file.origin.id

    # If the user does not exist, we cannot send an email
    user = proxy.find_user(user_id)
    if not user:
        log.warning(
            "Owner of the file does not match a user on Flywheel, "
            "will not send completion email"
        )
        return

    # lookup the user's email; if not set fall back to the file origin id
    target_email = user.email if user.email else file.origin.id

    # don't send emails to the gearbot
    if target_email in [
        "nacc-flywheel-gear@uw.edu",
        "nacc-flywheel-gear@washington.edu",
    ]:
        log.info("Owner is the gearbot, not sending email")
        return

    # look up the center name
    group = proxy.find_group(project.group)
    group_label = "your center" if not group else group.label

    template_data = SubmissionCompleteTemplateModel(
        first_name=user.firstname,  # type: ignore
        file_name=file.name,
        center_name=group_label,
        portal_url=portal_url["url"],
    )

    destination = DestinationModel(to_addresses=[target_email])

    email_client.send(
        configuration_set_name="submission-pipeline",
        destination=destination,
        template="submission-pipeline-complete",
        template_data=template_data,
    )
