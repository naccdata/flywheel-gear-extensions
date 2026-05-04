"""Provides utilities for pulling input from the OS environment."""

import os


def get_environment_variable(name: str) -> str | None:
    """Gets the value of the environment variable.

    Note: converts the variable name to upper case.

    Returns:
      The value of the environment variable.
    """
    value = None
    variable = name.upper()
    if variable in os.environ:
        value = os.environ[variable]
    return value
