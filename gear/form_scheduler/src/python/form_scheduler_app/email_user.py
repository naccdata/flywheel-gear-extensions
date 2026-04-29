"""Handles emailing user on completion of their submission pipeline."""

import logging
import re
from abc import abstractmethod
from typing import ClassVar

from configs.ingest_configs import PipelineType
from deletions.models import DeleteInfoModel
from flywheel import Project, User
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from inputs.parameter_store import URLParameter
from notifications.email import (
    BaseTemplateModel,
    DestinationModel,
    EmailClient,
    EmailSendError,
)
from pydantic import ValidationError

log = logging.getLogger(__name__)


class PipelineNotificationTemplate(BaseTemplateModel):
    """Base class for pipeline email template models."""

    template_name: ClassVar[str]
    configuration_set_name: ClassVar[str]
    cc_sender: ClassVar[bool] = False  # whether to CC the sender

    first_name: str
    center_name: str
    portal_url: str

    @classmethod
    @abstractmethod
    def build_template(
        cls,
        user: User,
        file: FileEntry,
        group_label: str,
        portal_url: URLParameter,
    ) -> "PipelineNotificationTemplate":
        """Builds the template model for pipeline notifications."""


class SubmissionPipelineNotificationTemplate(PipelineNotificationTemplate):
    """Submission complete template model."""

    template_name = "submission-pipeline-complete"
    configuration_set_name = "submission-pipeline"

    file_name: str

    @classmethod
    def build_template(
        cls,
        user: User,
        file: FileEntry,
        group_label: str,
        portal_url: URLParameter,
    ) -> "SubmissionPipelineNotificationTemplate":
        """Builds the template model for submission pipeline notifications."""
        return cls(
            first_name=user.firstname,  # type: ignore
            file_name=file.name,
            center_name=group_label,
            portal_url=portal_url["url"],
        )


class DeletePipelineNotificationTemplate(PipelineNotificationTemplate):
    """Base class for deletion pipeline template models."""

    configuration_set_name = "deletion-pipeline"

    delete_request_label: str  # <ptid>_<date>_[<visitnum>_]<module>

    @classmethod
    def build_template(
        cls,
        user: User,
        file: FileEntry,
        group_label: str,
        portal_url: URLParameter,
    ) -> "PipelineNotificationTemplate":
        """Builds the template model for deletion pipeline notifications.

        Returns a success model if the deletion completed with PASS
        state, otherwise returns a failure model.
        """

        # filename format: delete_<ptid>_<date>_[<visitnum>_]<module>.json
        match = re.match(
            r"^delete_(.+)_(\d{4}-\d{2}-\d{2})_(?:(\S+)_)?(\S+)\.json$",
            file.name,
        )
        if match:
            ptid, date, visitnum, module = match.groups()
            label = f"PTID: {ptid}, Module: {module.upper()}, Date: {date}"
            if visitnum:
                label += f", Visit Number: {visitnum}"
        else:
            label = file.name.replace("delete_", "", 1).replace(".json", "")

        try:
            delete_response_info = (
                DeleteInfoModel.model_validate(file.info) if file.info else None
            )
            if (
                delete_response_info
                and delete_response_info.delete_response.state == "PASS"
            ):
                deleted_visits = delete_response_info.get_deleted_visits_list()
                if deleted_visits:
                    return DeleteSuccessTemplate(
                        first_name=user.firstname,  # type: ignore
                        center_name=group_label,
                        portal_url=portal_url["url"],
                        delete_request_label=label,
                        deleted_visits=deleted_visits,
                    )
        except ValidationError as error:
            log.error(
                "Failed to extract response details for the delete request %s: %s",
                file.name,
                error,
            )

        return DeleteFailureTemplate(
            first_name=user.firstname,  # type: ignore
            center_name=group_label,
            portal_url=portal_url["url"],
            delete_request_label=label,
        )


class DeleteSuccessTemplate(DeletePipelineNotificationTemplate):
    """Deletion request success notification template."""

    template_name = "deletion-success-notification"

    deleted_visits: str


class DeleteFailureTemplate(DeletePipelineNotificationTemplate):
    """Deletion request failure notification template."""

    template_name = "deletion-failure-notification"
    cc_sender = True


def send_email(
    proxy: FlywheelProxy,
    email_client: EmailClient,
    file: FileEntry,
    project: Project,
    portal_url: URLParameter,
    pipeline_name: PipelineType,
) -> None:
    """Sends an email notifying user that their pipeline has completed.

    Args:
        proxy: the proxy for the Flywheel instance
        email_client: EmailClient to send emails from
        file: The FileEntry object to will pull details
        project: Flywheel project container
        portal_url: The portal URL
        pipeline_name: The name of the pipeline that completed
    """
    file = file.reload()
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

    match pipeline_name:
        case "submission":
            template_data: PipelineNotificationTemplate = (
                SubmissionPipelineNotificationTemplate.build_template(
                    user, file, group_label, portal_url
                )
            )
        case "deletion":
            template_data = DeletePipelineNotificationTemplate.build_template(
                user, file, group_label, portal_url
            )
        case _:
            log.warning(
                "No email template configured for pipeline '%s', skipping notification",
                pipeline_name,
            )
            return

    receivers = [target_email]
    if template_data.cc_sender:
        receivers.append(email_client.source)

    destination = DestinationModel(to_addresses=receivers)

    try:
        email_client.send(
            configuration_set_name=template_data.configuration_set_name,
            destination=destination,
            template=template_data.template_name,
            template_data=template_data,
        )
    except EmailSendError as error:
        log.error(error)
