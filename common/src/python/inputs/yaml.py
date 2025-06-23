"""Defines utilities for parsing YAML input."""

import logging
from typing import Any, List

import yaml

log = logging.getLogger(__name__)


def load_all_from_stream(stream) -> List[Any]:
    """Gets list of objects from the IO stream.

    Assumes the file can have more than one document.

    Args:
      stream: IO stream
      yaml_file: the name of the file
    Returns:
      List of lists of objects created from file or None if an error occurs
    """
    try:
        doc_iter = yaml.safe_load_all(stream)
        return [doc for doc in doc_iter]
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        if mark:
            raise YAMLReadError(
                f"Error in YAML: line {mark.line + 1}, " "column {mark.column + 1}"
            ) from error
        raise YAMLReadError(f"Error in YAML file: {error}") from error
    except yaml.YAMLError as error:
        raise YAMLReadError(f"Error in YAML file: {error}") from error


def load_from_stream(stream) -> Any:
    """Loads object from the YAML IO stream.

    Args:
      stream: IO stream
    Returns:
      Object created from file or None if an error occurs
    """
    try:
        return yaml.safe_load(stream)
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        if mark:
            raise YAMLReadError(
                f"Error in YAML: line {mark.line + 1}, " "column {mark.column + 1}"
            ) from error
        raise YAMLReadError(f"Error in YAML file: {error}") from error
    except yaml.YAMLError as error:
        raise YAMLReadError(f"Error in YAML file: {error}") from error


class YAMLReadError(Exception):
    """Exception class for errors that occur when reading objects from a YAML
    file."""
