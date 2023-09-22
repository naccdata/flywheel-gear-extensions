"""Module for connections to LONI."""

from typing import Optional

import requests


class LONIConnectionError(Exception):
    """Exception for errors that occur when connecting to LONI."""


class LONIConnection:
    """Manages a connection to the LONI IDA."""

    def __init__(self, key) -> None:
        self.__key = key

    def list_tables(self, database_name: str):
        """Returns the list of tables for the database.

        Args:
          database_name: the database

        Returns:
          List of tables in the database.
        """
        response = requests.get(
            url=LONIConnection.url(f"{database_name}/tables"),
            params={
                'key': self.__key,
                'format': 'json'
            })
        if response.status_code == 401:
            # handle invalid key
            raise LONIConnectionError(
                f"Unable to access tables in {database_name}: {response.reason}"
            )

        if response.status_code == 500:
            # handle system error
            raise LONIConnectionError(
                f"Unable to connect to {database_name}: {response.reason}")

        return response.json()

    def list_columns(self, *, database_name: str, table_name: str):
        """Returns the list of columns for the table of the database.

        Args:
          database_name: the name of the database.
          table_name: the name of the table.

        Returns:
          The columns of the table.
        """
        response = requests.get(
            url=LONIConnection.url(f"{database_name}/{table_name}/columns"),
            params={
                'key': self.__key,
                'format': 'json'
            })
        if response.status_code == 401:
            raise LONIConnectionError(
                f"unable to access columns: {response.reason}")

        if response.status_code == 500:
            raise LONIConnectionError(
                f"error connecting to {database_name}: {response.reason}")

        return response.json()

    def get_table(self, *, database_name: str, table_name: str) -> str:
        """Returns the requested table from the database.

        Args:
          database_name: the name of the database
          table_name: the name of the table
        Returns:
          CSV of table contents
        Raises:
          LONIConnectionError when access is denied or there is a system error
        """
        response = requests.get(
            url=LONIConnection.url(f"{database_name}/download"),
            params={
                'table': table_name,
                'key': self.__key
            })
        if response.status_code == 401:
            raise LONIConnectionError(
                f"Failed to get table {table_name}: {response.reason}")

        if response.status_code == 500:
            raise LONIConnectionError(
                f"Error connecting to {database_name}: {response.reason}")

        return response.text

    @classmethod
    def url(cls, path: str) -> str:
        """Builds a URL for accessing a LONI IDA endpoint.

        Returns:
          URL constructed by extending the LONI API path with the given string.
        """
        return f"https://ida.loni.usc.edu/sync/v1/{path}"

    @classmethod
    def create_connection(cls, *, email: str,
                          password: str) -> Optional['LONIConnection']:
        """Creates a connection object using the credentials (email and
        password).

        A connection is only valid for 2 hours after which the connection key expires.

        Args:
          email: email address for a LONI IDA account.
          password: password for the LONI IDA account.

        Returns:
          A LONI IDA connection for the account.
        """
        user_params = {'email': email, 'format': 'json'}
        response = requests.post(url=cls.url('sync/v1/auth'),
                                 headers={'Content-Type': 'text/plain'},
                                 params=user_params,
                                 data=password)

        if not response.ok:
            raise LONIConnectionError(
                f"Could not create LONI connection: {response.reason}")

        key = response.json()['key']
        return LONIConnection(key)
