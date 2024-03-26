"""Classes and methods for connecting to REDCap."""
import json
from json import JSONDecodeError
from typing import Any, Dict, List, Optional

import requests
from inputs.parameter_store import REDCapReportParameters
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
        try:
            response = requests.post(self.__url, data=data)
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as error:
            raise REDCapConnectionError(
                message=f"Error connecting to {self.__url} - {error}"
            ) from error

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
            raise REDCapConnectionError(message=message) from error

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

    def import_records(self, records: str, data_format: str = 'json') -> int:
        """Import records to the REDCap project.

        Args:
            records (str): List of records to be imported as a csv/json string
            data_format (str, optional): Import formart, defaults to 'json'.

        Raises:
          REDCapConnectionError if the response has an error.
        """

        message = "importing records"
        data = {
            'content': 'record',
            'action': 'import',
            'forceAutoNumber': 'false',
            'data': records,
            'returnContent': 'count',
        }

        response = self.post_request(data=data, result_format=data_format)
        if not response.ok:
            raise REDCapConnectionError(
                message=error_message(message=message, response=response))

        try:
            num_records = json.loads(response.text)['count']
        except (JSONDecodeError, ValueError) as error:
            raise REDCapConnectionError(message=message) from error

        return num_records

    def export_records(
            self,
            *,
            exp_format: str = 'json',
            record_ids: Optional[list[str]] = None,
            fields: Optional[list[str]] = None,
            forms: Optional[list[str]] = None,
            events: Optional[list[str]] = None,
            filters: Optional[str] = None) -> List[Dict[str, str]] | str:
        """ Export records from the REDCap project.

        Args:
            exp_format: Export format, defaults to 'json'
            record_ids (Optional): List of record IDs to be exported
            fields (Optional): List of fields to be included
            forms (Optional): List of forms to be included
            events (Optional): List of events to be included
            filters (Optional) : Filter logic as a string (e.g. [age]>30)

        Returns:
            The list of records (JSON objects) or 
            a CSV text string depending on exp_format.

        Raises:
          REDCapConnectionException if the response has an error.
        """

        data = {
            'content': 'record',
            'action': 'export',
            'returnFormat': 'json'
        }

        # If set of record ids specified, export only those records.
        if record_ids:
            data['records'] = ','.join(record_ids)

        # If set of fields specified, export records only those fields.
        if fields:
            data['fields'] = ','.join(fields)

        # If set of forms specified, export records only from those forms.
        if forms:
            data['forms'] = ','.join(forms)

        # If set of events specified, export records only for those events.
        if events:
            data['events'] = ','.join(events)

        # If any filters specified, export only matching records.
        if filters:
            data['filterLogic'] = ','.join(filters)

        message = 'failed to export records'
        if exp_format == 'json':
            return self.request_json_value(data=data, message=message)

        return self.request_text_value(data=data,
                                       result_format=exp_format,
                                       message=message)


class REDCapReportConnection(REDCapConnection):
    """Defines a REDCap connection meant for reading a particular report."""

    def __init__(self, *, token: str, url: str, report_id: str) -> None:
        super().__init__(token=token, url=url)
        self.report_id = report_id

    @classmethod
    def create_from(
            cls,
            parameters: REDCapReportParameters) -> 'REDCapReportConnection':
        """Creates a REDCap connection with report parameters.

        Args:
          parameters: the parameters
        Returns:
          the connection using the parameters
        """
        return REDCapReportConnection(token=parameters['token'],
                                      url=parameters['url'],
                                      report_id=parameters['reportid'])

    def get_report_records(self) -> List[Dict[str, str]]:
        """Gets the report from the REDCap connection.

        Returns:
          list of records from the report
        """
        message = f"pulling report id {self.report_id}"
        data = {
            'content': 'report',
            'report_id': str(self.report_id),
            'csvDelimiter': '',
            'rawOrLabel': 'raw',
            'rawOrLabelHeaders': 'raw',
            'exportCheckboxLabel': 'false'
        }
        return self.request_json_value(data=data, message=message)


def error_message(*, message: str, response: Response) -> str:
    """Build an error message from the given message and HTTP response.

    Returns:
      The error string
    """
    return (f"Error: {message}\nHTTP Error:{response.status_code} "
            f"{response.reason}: {response.text}")


class REDCapConnectionError(Exception):
    """Exception class representing error connecting to a REDCap project."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def __str__(self) -> str:
        return self.message

    @property
    def message(self):
        """The error message."""
        return self._message
