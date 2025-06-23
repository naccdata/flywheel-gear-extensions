"""Handles email list from REDCap report."""

import logging
from typing import Dict, Optional

from gear_execution.gear_execution import GearExecutionError
from inputs.parameter_store import ParameterError, ParameterStore
from pydantic import BaseModel, ConfigDict, Field
from redcap_api.redcap_connection import (
    REDCapConnectionError,
    REDCapReportConnection,
)

from .email import (
    BaseTemplateModel,
    DestinationModel,
    EmailClient,
    TemplateDataModel,
    create_ses_client,
)

log = logging.getLogger(__name__)


class REDCapEmailListConfigs(BaseModel):
    """Defines model for REDCap email list configs."""

    model_config = ConfigDict(populate_by_name=True)

    redcap_parameter_path: str
    source_email: str
    configuration_set_name: str
    template_name: str
    email_key: str = Field(default="email")

    # if using TemplateDataModel
    firstname_key: Optional[str] = None
    url_key: Optional[str] = None


class REDCapEmailList:
    def __init__(
        self,
        redcap_con: REDCapReportConnection,
        configs: REDCapEmailListConfigs,
        dry_run: bool = False,
        ses=None,
    ) -> None:
        """Pull email list from REDCap report."""
        self.__redcap_con = redcap_con
        self.__configs = configs
        self.__dry_run = dry_run

        ses = ses if ses is not None else create_ses_client()

        self.__email_list = self.__pull_email_list_from_redcap()
        self.__email_client = EmailClient(
            client=ses, source=self.__configs.source_email
        )

    @property
    def email_list(self) -> Dict[str, Dict[str, str]]:
        return self.__email_list

    @staticmethod
    def create(
        parameter_store: ParameterStore,
        configs: REDCapEmailListConfigs,
        dry_run: bool = False,
    ) -> "REDCapEmailList":
        """Creates the REDCapEmailList."""
        try:
            redcap_parameter_path = configs.redcap_parameter_path
            redcap_params = parameter_store.get_redcap_report_parameters(
                param_path=redcap_parameter_path
            )
            redcap_con = REDCapReportConnection.create_from(redcap_params)
            return REDCapEmailList(
                redcap_con=redcap_con, configs=configs, dry_run=dry_run
            )
        except (ParameterError, REDCapConnectionError) as error:
            raise GearExecutionError(error) from error

    def __pull_email_list_from_redcap(self) -> Dict[str, Dict[str, str]]:
        """Pull email list from REDCap. Maps each email to the corresponding
        record, and assumes each email is unique.

        Args:
            email: key the email is expected to live under
        """
        records = self.__redcap_con.get_report_records()

        email_list = {}
        for record in records:
            email = record[self.__configs.email_key]
            if email in email_list:
                raise GearExecutionError(f"Duplicate email: {email}")
            email_list[email] = record

        return email_list

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

        return self.__email_client.send(
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
                raise GearExecutionError(f"Cannot determine first name for {email}")

            template_data = TemplateDataModel(firstname=firstname, url=url)

            if self.__dry_run:
                log.info(f"DRY RUN: would have sent email to {destination}")
                continue

            response = self.__email_client.send(
                configuration_set_name=self.__configs.configuration_set_name,
                destination=destination,
                template=self.__configs.template_name,
                template_data=template_data,
            )
            message_ids[email] = response

        return message_ids if not self.__dry_run else None
