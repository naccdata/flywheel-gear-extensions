"""Module to represent a REDCap project and associated API calls."""

import json
import logging
from json import JSONDecodeError
from typing import Any, Dict, List, Optional

from keys.keys import DefaultValues

from redcap.redcap_connection import (
    REDCapConnection,
    REDCapConnectionError,
    error_message,
)

NACC_TECH_ROLE = 'NACC_TECH_ROLE'
NACC_STAFF_ROLE = 'NACC_STAFF_ROLE'
CENTER_USER_ROLE = 'CENTER_USER_ROLE'
NACC_GEARBOT_ROLE = 'NACC_GEARBOT_ROLE'

log = logging.getLogger()


def get_nacc_developer_permissions(
        *,
        username: str,
        expiration: Optional[str] = None,
        forms_list: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Permissions for a NACC user who has developer privileges for a project.

    Args:
        username: REDCap username
        expiration (optional): permission expiration date
        forms_list (optional): list of forms in the project

    Returns:
        Dict[str, Any]: user permissions directory
    """

    forms = {}  # Form rights
    forms_export = {}  # Data export rights

    # Need to set permissions for each form in the project
    if forms_list:
        for form in forms_list:
            form_name = form['instrument_name']
            forms[form_name] = 1  # View and Edit
            forms_export[form_name] = 1  # Full Data Set

    permissions = {
        "username": username,
        "expiration": expiration,
        "design": 1,
        "alerts": 1,
        "user_rights": 1,
        "data_access_groups": 1,
        "data_export": 1,
        "reports": 1,
        "stats_and_charts": 1,
        "manage_survey_participants": 1,
        "calendar": 1,
        "data_import_tool": 1,
        "data_comparison_tool": 1,
        "logging": 1,
        "file_repository": 1,
        "data_quality_create": 1,
        "data_quality_execute": 1,
        "api_export": 1,
        "api_import": 1,
        "record_create": 1,
        "record_rename": 1,
        "record_delete": 1,
        "forms": forms,
        "forms_export": forms_export
    }

    return permissions


class REDCapProject:
    """Class representing a REDCap project."""

    def __init__(self, *, redcap_con: REDCapConnection, pid: int, title: str,
                 pk_field: str, longitudinal: bool,
                 repeating_ins: bool) -> None:
        self.__redcap_con = redcap_con
        self.__pid = pid
        self.__title = title
        self.__pk_field = pk_field
        self.__longitudinal = longitudinal
        self.__repeating_ins = repeating_ins

    @classmethod
    def create(cls, redcap_con: REDCapConnection) -> 'REDCapProject':
        """Get the REDCap project for this connection."""

        project_info = redcap_con.export_project_info()
        field_names = redcap_con.export_field_names()

        return REDCapProject(
            redcap_con=redcap_con,
            pid=int(project_info['project_id']),
            title=project_info['project_title'],
            pk_field=field_names[0]['export_field_name'],
            longitudinal=(project_info['is_longitudinal'] == 1),
            repeating_ins=(
                project_info['has_repeating_instruments_or_events'] == 1))

    @property
    def pid(self) -> int:
        """Returns REDCap project ID."""
        return self.__pid

    @property
    def title(self) -> str:
        """Returns REDCap project title."""
        return self.__title

    @property
    def primary_key_field(self) -> str:
        """Returns primary key field for the project."""
        return self.__pk_field

    def is_longitudinal(self) -> bool:
        """Is this project set up to collect longitudinal data."""
        return self.__longitudinal

    def has_repeating_instruments_or_events(self) -> bool:
        """Does this project has repeating instruments or events."""
        return self.__repeating_ins

    def export_instruments(self) -> List[Dict[str, str]]:
        """Export the list of instruments in the project.

        Returns:
            List containing the name and label for each instrument

        Raises:
          REDCapConnectionError if the response has an error
        """

        message = "exporting list of forms"
        data = {'content': 'instrument'}

        return self.__redcap_con.request_json_value(data=data, message=message)

    def export_user_roles(self) -> List[Dict[str, Any]]:
        """Export user roles defined in the project.

        Returns:
            List of user role dicts specifying permissions for each role

        Raises:
          REDCapConnectionError if the response has an error
        """
        message = "exporting user roles"
        data = {'content': 'userRole'}

        return self.__redcap_con.request_json_value(data=data, message=message)

    def assign_user_role(self, username: str, role: str) -> int:
        """Assign given user to a user role in REDCap project.

        Args:
            username: REDCap username
            role: Unique REDCap generated role name (not role label)

        Returns:
            Number of User-Role assignments added or updated

        Raises:
          REDCapConnectionError if the response has an error
        """
        data = {
            'content': 'userRoleMapping',
            'action': 'import',
            'data': json.dumps([{
                "username": username,
                "unique_role_name": role
            }])
        }
        return self.__redcap_con.request_json_value(
            data=data, message=f"assigning user {username} to role {role}")

    def add_user(self, user_info: Dict[str, Any]) -> int:
        """Import a new user into a project and set user privileges, or update
        the privileges of an existing user in the project.

        Args:
            user_info: User permissions for the project

        Returns:
            int: Number of users added or updated

        Raises:
          REDCapConnectionError if the response has an error
        """

        message = f"adding user {user_info['username']}"
        info = json.dumps([user_info])
        data = {
            'content': 'user',
            'data': info,
        }

        return self.__redcap_con.request_json_value(data=data, message=message)

    def assign_update_user_role_by_label(self, username: str,
                                         role_label: str) -> bool:
        """Assign or update user permissions in the REDCap project.

        Args:
            username: REDCap user name
            role_label: REDCap user role to be assigned to the user
        """

        try:
            roles = self.export_user_roles()
            role_name = None
            for role in roles:
                if role['role_label'] == role_label:
                    role_name = role['unique_role_name']
                    break

            if not role_name:
                log.error('User role %s does not exist in REDCap project %s',
                          role_label, self.title)
                return False

            self.assign_user_role(username, role_name)
        except REDCapConnectionError as error:
            log.error(
                'Failed to assign/update permissions for user %s '
                'in REDCap project %s - %s', username, self.title, error)
            return False

        return True

    def add_gearbot_user_to_project(self):
        """Add nacc gearbot user to the specified project.

        Args:
            redcap_con: API connection for the REDCap project

        Raises:
            REDCapConnectionError if the response has an error.
        """

        if not self.assign_update_user_role_by_label(
                DefaultValues.GEARBOT_USER_ID, NACC_GEARBOT_ROLE):
            forms = self.export_instruments()
            gearbot_user = get_nacc_developer_permissions(
                username=DefaultValues.GEARBOT_USER_ID, forms_list=forms)
            self.add_user(gearbot_user)

    def import_records(self, records: str, data_format: str = 'json') -> int:
        """Import records to the REDCap project.

        Args:
            records: List of records to be imported as a csv/json string
            data_format (optional): Import format, defaults to 'json'.

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

        response = self.__redcap_con.post_request(
            data=data, result_format=data_format.lower())
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
        """Export records from the REDCap project.

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
          REDCapConnectionError if the response has an error.
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
            data['filterLogic'] = filters

        message = 'failed to export records'
        if exp_format.lower() == 'json':
            return self.__redcap_con.request_json_value(data=data,
                                                        message=message)

        return self.__redcap_con.request_text_value(data=data,
                                                    result_format=exp_format,
                                                    message=message)

    def export_events(self) -> List[Dict[str, Any]]:
        """Exports the events defined in the project.

        Returns:
            List[Dict[str, str]]: List of event info Dicts

        Raises:
          REDCapConnectionError if the response has an error.
        """
        message = "exporting events"
        data = {'content': 'event'}

        return self.__redcap_con.request_json_value(data=data, message=message)

    def get_event_name_for_label(self, label: str) -> Optional[str]:
        """Returns the unique REDCap event name for given label.

        Returns:
            Optional[str]: REDCap event name if found, else None
        """

        try:
            events = self.export_events()
        except REDCapConnectionError as error:
            log.error('Failed to retrieve events for project %s - %s',
                      self.title, error)
            return None

        for event in events:
            if label == event['event_name'].lower():
                return event['unique_event_name']

        return None
