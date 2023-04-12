"""Classes and methods for connecting to REDCap."""
from json import JSONDecodeError
from typing import Any, Dict, List, Optional

import requests
from requests import Response


class REDCapConnection:
    """Class managing the connection to a REDCap project.

    Provides a post method to adapting classes. See `ProjectReader`
    """

    def __init__(self, *, token: str, url: str) -> None:
        """Initializes a REDCap connection using the given project token and
        URL.

        Args:
          token: API token for the REDCap project.
          url: URL of REDCap instance
        """
        self.__token = token
        self.__url = url

    def post_request(self,
                     *,
                     data: Dict[str, str],
                     result_format: Optional[str] = None,
                     return_format: str = 'json') -> Any:
        """Posts a request to the REDCap project with the given data object.

        Returns:
          The response from posting the request.

        Raises:
          REDCapConnectionException if there is an error connecting to the
          specified project
        """
        data.update({'token': self.__token, 'returnFormat': return_format})
        if result_format:
            data['format'] = result_format
        response = requests.post(self.__url, data=data)

        return response

    def request_json_value(self, *, data: Dict[str, str], message: str) -> Any:
        """Posts a request to the REDCap project with the given data object
        expecting a JSON value.

        Returns:
          The object for the JSON value.

        Raises:
          REDCapConnectionException if the response has an error.
        """
        response = self.post_request(data=data, result_format='json')
        if not response.ok:
            raise REDCapConnectionError(
                message=error_message(message=message, response=response))
        try:
            return response.json()
        except JSONDecodeError as error:
            raise REDCapConnectionError(message=message,
                                        error=error) from error

    def request_text_value(self,
                           *,
                           data: Dict[str, str],
                           result_format: Optional[str] = None,
                           message: str) -> str:
        """Posts a request to the REDCap project with the given data object
        expecting a text value.

        Returns:
          The text string for the returned value.

        Raises:
          REDCapConnectionError if the response has an error.
        """
        response = self.post_request(data=data, result_format=result_format)
        if not response.ok:
            message = "cannot get project XML"
            raise REDCapConnectionError(
                message=error_message(message=message, response=response))

        return response.text


def error_message(*, message: str, response: Response) -> str:
    """Build an error message from the given message and HTTP response.

    Returns:
      The error string
    """
    return (f"Error: {message}\nHTTP Error:{response.status_code} "
            f"{response.reason}: {response.text}")


class REDCapConnectionError(Exception):
    """Exception class representing error connecting to a REDCap project."""

    def __init__(self,
                 *,
                 error: Optional[Exception] = None,
                 message: str) -> None:
        super().__init__()
        self._error = error
        self._message = message

    def __str__(self) -> str:
        if self.error:
            return f"{self.message}\n{self.error}"

        return self.message

    @property
    def error(self):
        """The exception causing this error."""
        return self._error

    @property
    def message(self):
        """The error message."""
        return self._message


def get_report(connection: REDCapConnection,
               report_id: str) -> List[Dict[str, str]]:
    """Pull the contents for the indicated report from the REDCap connection.

    Args:
      connection: the connection to the REDCap instance
      report_id: the ID for the report
    """
    data = {
        'content': 'report',
        'report_id': report_id,
        'rawOrLabel': 'raw',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false'
    }
    message = "Unable to get report contents"
    return connection.request_json_value(data=data, message=message)
