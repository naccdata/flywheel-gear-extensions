import logging
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError
from inputs.environment import get_environment_variable
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from serialization.case import camel_case

log = logging.getLogger(__name__)


def create_ses_client():
    """Creates a boto3 SES client if the AWS credentials are set.

    Expects AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, and
    AWS_DEFAULT_REGION.
    """
    secret_key = get_environment_variable('AWS_SECRET_ACCESS_KEY')
    access_id = get_environment_variable('AWS_ACCESS_KEY_ID')
    region = get_environment_variable('AWS_DEFAULT_REGION')
    if not secret_key or not access_id or not region:
        return None

    return boto3.client(
        'ses',  # type: ignore
        aws_access_key_id=access_id,
        aws_secret_access_key=secret_key,
        region_name=region)


class DestinationModel(BaseModel):
    """Defines a destination object for the boto3 SES client."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=camel_case))

    to_addresses: List[str]
    cc_addresses: Optional[List[str]] = None
    bcc_addresses: Optional[List[str]] = None


class MessageComponent(BaseModel):
    """Defines a model for message components for the boto3 SES client."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=camel_case))

    data: str
    charset: str = Field('utf-8')


class BaseTemplateModel(BaseModel):
    """Base templte model for messages for the boto3 SES client."""
    email_address: Optional[str] = None\


class TemplateDataModel(BaseTemplateModel):
    """Defines a model for messages for the boto3 SES client."""
    firstname: str
    url: Optional[str] = None


class EmailClient:
    """Wrapper for boto3 SES client."""

    def __init__(self, client, source: str) -> None:
        self.__client = client
        self.__source = source

    def send(
        self,
        configuration_set_name: str,
        destination: DestinationModel,
        template: str,
        template_data: BaseTemplateModel,
    ) -> str:
        """Sends the message to the destination from the source address.

        Args:
          configuration_set_name: name of the configuration set
          destination: the DestinationModel with email addresses
          template: the name of the SES template
          template_data: the MessageContentModel with message content
        Returns:
          the message ID if successfully sent
        Raises:
        """
        try:
            response = self.__client.send_templated_email(
                Source=self.__source,
                ConfigurationSetName=configuration_set_name,
                Destination=destination.model_dump(by_alias=True,
                                                   exclude_none=True),
                Template=template,
                TemplateData=template_data.model_dump_json(exclude_none=True))
            log.info("Sent %s email to %s", template,
                     ', '.join(destination.to_addresses))

        except ClientError as error:
            log.error("Failed to send email")
            raise EmailSendError(error) from error

        message_id = response['MessageId']
        log.info("Sent mail %s", message_id)
        return message_id


class EmailSendError(Exception):
    """Error class for error during sending email."""
