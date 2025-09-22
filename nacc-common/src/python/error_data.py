"""Utilities for pulling error data attached to files."""

from typing import Any, Callable, Dict, List, Literal, Optional

from flywheel import FileEntry, Project

ERROR_HEADER_NAMES: List[str] = [
    "type",
    "ptid",
    "visitnum",
    "code",
    "line",
    "column_name",
    "key_path",
    "id",
    "name",
    "gear",
    "container_id",
    "flywheel_path",
    "value",
    "expected",
    "message",
    "timestamp",
]

STATUS_HEADER_NAMES: List[str] = ["name", "id", "gear", "status"]


def qc_data(file_object: FileEntry) -> Dict[str, Any]:
    """Returns the QC object in the metadata for the file.

    Args:
      file_object: the file metadata
    Returns:
      the dictionary for info.qc if non-empty. Otherwise, the empty dictionary.
    """
    return file_object.get("info", {}).get("qc", {})


def validation_data(qc_object: Dict[str, Any], gear_name: str) -> Dict[str, Any]:
    """Returns the validation object in the QC metadata for the named gear.

    Args:
      qc_object: the QC metadata (file.info.qc)
      gear_name: the name of the gear
    """
    return qc_object.get(gear_name, {}).get("validation", {})


def error_data(qc_object: Dict[str, Any], gear_name: str) -> List[Dict[str, Any]]:
    """Returns the error object in the QC metadata if the status is not "pass".

    Args:
      qc_object: the QC metadata (file.info.qc)
      gear_name: the name of the gear
    Returns:
      the list for gear_name.validation.data if exists.
      Otherwise, the empty list.
    """
    validation_object = validation_data(qc_object=qc_object, gear_name=gear_name)
    status = validation_object.get("state")
    if status is not None and status.lower() == "pass":
        return []

    return validation_object.get("data", [])


def status_data(
    qc_object: Dict[str, Any], gear_name: str
) -> Optional[Literal["pass", "fail"]]:
    """Returns the QC status in the QC metadata.

    Args:
      qc_object: the QC metadata (file.info.qc)
      gear_name: the name of the gear
    Returns:
      the QC status for the gear if set. None, otherwise.
    """
    status = validation_data(qc_object=qc_object, gear_name=gear_name).get("state")
    if status is None:
        return None
    if status.lower() == "pass":
        return "pass"
    if status.lower() == "fail":
        return "fail"

    return None


def build_qc_info_list(
    file_object: FileEntry,
    insert_info: Callable[[Dict[str, Any], str, List[Dict[str, Any]]], None],
) -> List[Dict[str, Any]]:
    """Build dictionaries for output of QC data for the file using the insert
    function.

    Args:
      file_object: the FW file
      insert_info: the QC data insert function
    Returns:
      A list of dictionaries for each object in the QC data for the file
    """
    qc_object = qc_data(file_object)
    gear_names = set(qc_object.keys())
    table: List[Dict[str, Any]] = []
    for gear_name in gear_names:
        insert_info(qc_object, gear_name, table)
    return table


def get_qc_data(
    project: Project, info_builder: Callable[[FileEntry], List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """Helper function to create list of dictionaries created by the info
    builder function applied to files in the project.

    Args:
      project: the project
      info_builder: function to create list of QC information
    Returns:
      List of QC information dictionaries for files in the project
    """
    project_object: Project = project.reload()
    return [
        item
        for sl in [
            info_builder(file)
            for file in project_object.files
            if file.info.get("qc", None)
        ]
        for item in sl
    ]


def get_error_data(project: Project) -> List[Dict[str, Any]]:
    """Creates a list of dictionaries, each corresponding to an error in a file
    in the project.

    Args:
      project: the flywheel project object
    """

    def build_error_info_list(file_object: FileEntry) -> List[Dict[str, Any]]:
        """Builds a list of error table information from the file dictionary
        object.

        Flattens in gear name, and error locations.

        Args:
        file_object: the file dictionary
        """

        def insert_error_info(
            qc_object: Dict[str, Any], gear_name: str, table: List[Dict[str, Any]]
        ) -> None:
            for error in error_data(qc_object, gear_name):
                loc: Dict[str, Any] = error.pop("location", {})  # type: ignore
                if loc:
                    error.update(loc)  # type: ignore
                table.append(
                    {
                        "name": file_object.name,
                        "id": file_object.id,
                        "gear": gear_name,
                        **error,
                    }
                )

        return build_qc_info_list(file_object, insert_error_info)

    return get_qc_data(project, build_error_info_list)


def get_status_data(project: Project) -> List[Dict[str, Any]]:
    """Returns a list of dictionaries containing QC status data for files in
    the project.

    Args:
      project: the project
    Returns:
      a list of containing status info objects for files in the project
    """

    def build_status_info_list(file_object: FileEntry) -> List[Dict[str, Any]]:
        """Returns a list of dictionaries containing QC status data for the file.

        Args:
          file_object: the FW file
        Returns:
          the list of QC status objects
        """

        def insert_status_info(
            qc_object: Dict[str, Any], gear_name: str, table: List[Dict[str, Any]]
        ) -> None:
            """Inserts the QC status info in to the list.

            Args:
              qc_object: the QC object from FW
              gear_name: the name of the gear generating error
              table: the list to insert into
            """
            table.append(
                {
                    "name": file_object.name,
                    "id": file_object.id,
                    "gear": gear_name,
                    "status": status_data(qc_object, gear_name),
                }
            )

        return build_qc_info_list(file_object, insert_status_info)

    return get_qc_data(project, build_status_info_list)
