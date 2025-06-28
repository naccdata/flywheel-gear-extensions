"""Class for handle email lists."""

import json
import logging
from typing import Dict, Optional

from gear_execution.gear_execution import InputFileWrapper
from inputs.parameter_store import ParameterError, ParameterStore
from pydantic import BaseModel, ConfigDict, Field
from redcap_api.redcap_connection import (
    REDCapConnectionError,
    REDCapReportConnection,
)
from redcap_api.redcap_email_list import REDCapEmailList

from .email import (
    BaseTemplateModel,
    DestinationModel,
    EmailClient,
    TemplateDataModel,
    create_ses_client,
)

log = logging.getLogger(__name__)


class EmailListError(Exception):
    """Error class for error during creating email list."""


class EmailListConfigs(BaseModel):
    """Defines model for basic email list configs."""

    model_config = ConfigDict(populate_by_name=True)

    source_email: str
    configuration_set_name: str
    template_name: str

    # if using TemplateDataModel
    firstname_key: Optional[str] = None
    url_key: Optional[str] = None


class REDCapEmailListConfigs(EmailListConfigs):
    """Defines model for REDCap-specific email list configs.

    Need to define fields for where in REDCap to grab emails.
    """

    redcap_parameter_path: str
    email_key: str = Field(default="email")


class EmailListClient(EmailClient):
    """Handles sending emails to lists."""

    def __init__(
        self,
        client,
        email_list: Dict[str, Dict[str, str]],
        configs: EmailListConfigs,
        dry_run: bool = False,
    ) -> None:
        """Handles emails to an email list.

        Args:
            client: SES client for sending emails
            email_list: Mapping of recipient email to recipient-specific data.
            configs: EmailListConfigs - describes the email configuration
                set and template to use, as well as the keys in email_list
                that correspond to the firstname/url/etc.
            dry_run: Whether or not to do a dry run
        """
        super().__init__(client=client, source=configs.source_email)
        self.__email_list = email_list
        self.__configs = configs
        self.__dry_run = dry_run

    def send_mass_email(self) -> Optional[str]:
        """Sends a single email to all recipients.

        Assumes the template does not need to be configured per user.

        Returns:
            the message ID if successfully sent
        """
        log.info(f"Sending single mass email to {len(self.__email_list)} recipients")
        destination = DestinationModel(to_addresses=list(self.__email_list.keys()))
        template_data = BaseTemplateModel()

        if self.__dry_run:
            log.info(f"DRY RUN: Would have sent email to {destination}")
            return None

        return self.send(
            configuration_set_name=self.__configs.configuration_set_name,
            destination=destination,
            template=self.__configs.template_name,
            template_data=template_data,
        )

    def send_emails(self) -> Optional[Dict[str, str]]:
        """Sends individual emails to each recipient.

        Assumes the template needs to be configured per user.

        Returns:
            Dict mapping each email to the message ID if successfully sent
        """
        log.info(f"Sending emails to {len(self.__email_list)} recipients")
        message_ids = {}

        for email, data in self.__email_list.items():
            destination = DestinationModel(to_addresses=[email])

            firstname = (
                data.get(self.__configs.firstname_key)
                if self.__configs.firstname_key
                else None
            )
            url = data.get(self.__configs.url_key) if self.__configs.url_key else None

            if not firstname:
                raise EmailListError(f"Cannot determine first name for {email}")

            template_data = TemplateDataModel(firstname=firstname, url=url)

            if self.__dry_run:
                log.info(f"DRY RUN: would have sent email to {destination}")
                continue

            response = self.send(
                configuration_set_name=self.__configs.configuration_set_name,
                destination=destination,
                template=self.__configs.template_name,
                template_data=template_data,
            )
            message_ids[email] = response

        return message_ids if not self.__dry_run else None


def get_redcap_email_list_client(
    redcap_email_configs_file: InputFileWrapper | None,
    parameter_store: ParameterStore | None,
    dry_run: bool = False,
) -> Optional[EmailListClient]:
    """Get the REDCap email list client."""
    if not redcap_email_configs_file:
        return None
    if not parameter_store:
        raise EmailListError("Need parameter_store to create REDCapEmailListClient")

    with open(redcap_email_configs_file.filepath, "r", encoding="utf-8-sig") as fh:
        configs = REDCapEmailListConfigs(**json.load(fh))
        try:
            redcap_parameter_path = configs.redcap_parameter_path
            redcap_params = parameter_store.get_redcap_report_parameters(
                param_path=redcap_parameter_path
            )
            redcap_con = REDCapReportConnection.create_from(redcap_params)
            email_list = REDCapEmailList(
                redcap_con=redcap_con, email_key=configs.email_key
            )
        except (ParameterError, REDCapConnectionError) as error:
            raise EmailListError(error) from error

        return EmailListClient(
            client=create_ses_client(),
            email_list=email_list,
            configs=configs,
            dry_run=dry_run,
        )
