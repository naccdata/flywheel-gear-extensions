"""Utilities for invoking AWS Lambda functions."""

import logging
from typing import Dict, List, Literal, Optional

import boto3
from botocore.exceptions import ClientError
from inputs.environment import get_environment_variable
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)


def create_lambda_client():
    """Creates a boto3 lambda client if AWS credentials are set.

    Expects AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, and
    AWS_DEFAULT_REGION.
    """
    secret_key = get_environment_variable("AWS_SECRET_ACCESS_KEY")
    access_id = get_environment_variable("AWS_ACCESS_KEY_ID")
    region = get_environment_variable("AWS_DEFAULT_REGION")
    if not secret_key or not access_id or not region:
        return None

    return boto3.client(
        "lambda",  # type: ignore
        aws_access_key_id=access_id,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


class BaseRequest(BaseModel):
    """Base model for request objects with connection mode."""

    mode: Optional[Literal["dev", "prod"]] = "prod"


class ResponseObject(BaseModel):
    """Base model for response objects."""

    statusCode: int
    headers: Dict[str, str]
    body: str


class ErrorResponseObject(BaseModel):
    """Base model for error response objects."""

    errorMessage: str
    errorType: str
    stackTrace: List[str]


# pylint: disable=(too-few-public-methods)
class LambdaClient:
    """Wrapper for boto3 lambda client."""

    def __init__(self, client) -> None:
        self.__client = client

    def invoke(self, name: str, request: BaseRequest) -> ResponseObject:
        """Invokes the named lambda function on the request object.

        Note: using this function requires AWS credentials with invoke rights
        on the lambda.

        Args:
          name: the name of the AWS lambda function
          request: the request object
        Returns:
          the response object from invoking the lambda function
        Raises:
          LambdaInvocationError if the response format is unexpected
        """
        try:
            response = self.__client.invoke(
                FunctionName=name,
                Qualifier=request.mode,
                InvocationType="RequestResponse",
                Payload=request.model_dump_json().encode("utf-8"),
                LogType="None",
            )
        except ClientError as error:
            raise LambdaInvocationError(str(error)) from error

        payload = response["Payload"].read()
        try:
            return ResponseObject.model_validate_json(payload)
        except ValidationError:
            pass

        try:
            response = ErrorResponseObject.model_validate_json(payload)
        except ValidationError as error:
            log.error("error validating lambda response: %s", str(error))
            raise LambdaInvocationError(str(error)) from error

        raise LambdaInvocationError(response.errorMessage)


class LambdaInvocationError(Exception):
    """Error class for error related to invoking lambda."""
