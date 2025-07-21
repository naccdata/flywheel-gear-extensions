"""Handles REDCap email list."""

from typing import Dict

from redcap_api.redcap_connection import (
    REDCapConnectionError,
    REDCapReportConnection,
)
from redcap_api.redcap_parameter_store import REDCapReportParameters


class REDCapEmailListError(Exception):
    pass


class REDCapEmailList:
    def __init__(self, redcap_con: REDCapReportConnection, email_key: str) -> None:
        """Pull email list from REDCap report.

        Args:
            redcap_con: The REDCapReportConnection
            email_key: Name of header key which emails can be found under
                in the REDCap Report
        """
        self.__redcap_con = redcap_con
        self.__email_list = self.__pull_email_list_from_redcap(email_key)

    @property
    def email_list(self) -> Dict[str, Dict[str, str]]:
        return self.__email_list

    def __pull_email_list_from_redcap(
        self, email_key: str
    ) -> Dict[str, Dict[str, str]]:
        """Pull email list from REDCap.

        Maps each email to the corresponding
        record, and assumes each email is unique.
        Args:
            email_key: Name of header key which emails can be found under
                in the REDCap Report
        """
        records = self.__redcap_con.get_report_records()

        email_list = {}
        for record in records:
            email = record[email_key]
            if email in email_list:
                raise REDCapEmailListError(f"Duplicate email: {email}")
            email_list[email] = record

        return email_list

    @staticmethod
    def create(
        redcap_params: REDCapReportParameters, email_key: str
    ) -> "REDCapEmailList":
        """Creates the REDCapEmailList."""
        try:
            redcap_con = REDCapReportConnection.create_from(redcap_params)
            return REDCapEmailList(redcap_con=redcap_con, email_key=email_key)
        except REDCapConnectionError as error:
            raise REDCapEmailListError(error) from error
