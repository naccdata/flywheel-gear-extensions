import logging
from datetime import datetime as dt
from typing import Any, Dict, List, Literal, Optional

from dates.form_dates import DEFAULT_DATE_FORMAT, DEFAULT_DATE_TIME_FORMAT, convert_date
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.data_identification import (
    AbstractIdentificationVisitor,
    DataIdentification,
    FormIdentification,
    ImageIdentification,
    ParticipantIdentification,
    VisitIdentification,
)
from nacc_common.error_models import FileErrorList, FileQCModel, QCStatus
from nacc_common.field_names import FieldNames
from pydantic import BaseModel, ValidationError
from utils.decorators import api_retry

log = logging.getLogger(__name__)

MetadataCleanupFlag = Literal["ALL", "GEAR", "NA"]


class VisitLabelTemplate(BaseModel):
    """Template for creating a visit label for a data record."""

    id_field: str = FieldNames.PTID
    date_field: str = FieldNames.DATE_COLUMN

    def instantiate(self, record: Dict[str, Any], module: str) -> Optional[str]:
        """Instantiates this using the values for the template fields and
        module to create a visit-label.

        Constructs the label as "<id-field>_<date-field>_<module>".

        Args:
          record: the data record
          module: the module name
        Returns:
          the visit-label if all fields exist. None, otherwise.
        """
        components = []
        ptid = record.get(self.id_field)
        if not ptid:
            return None

        cleaned_ptid = ptid.strip().lstrip("0")
        if not cleaned_ptid:
            return None

        visitdate = record.get(self.date_field)
        if not visitdate:
            return None

        normalized_date = convert_date(
            date_string=visitdate, date_format=DEFAULT_DATE_FORMAT
        )
        if not normalized_date:
            return None

        components.append(cleaned_ptid)
        components.append(normalized_date)
        components.append(module.lower())

        return "_".join(components)


class ErrorLogIdentificationVisitor(AbstractIdentificationVisitor):
    """Visitor that collects identification attributes for error log file
    naming."""

    def __init__(self) -> None:
        self.__participant_attribute = ""
        self.__visit_attribute = ""
        self.__date_attribute = ""
        self.__data_attribute = ""

    @property
    def log_name_prefix(self) -> Optional[str]:
        """Build log name prefix from collected attributes.

        Returns None if any required attributes (participant, date,
        data) are empty. Visit attribute is optional.
        """
        # Check required attributes
        if (
            not self.__participant_attribute
            or not self.__date_attribute
            or not self.__data_attribute
        ):
            return None

        prefix = f"{self.__participant_attribute}"
        if self.__visit_attribute:
            prefix = f"{prefix}_{self.__visit_attribute}"
        prefix = f"{prefix}_{self.__date_attribute}"
        prefix = f"{prefix}_{self.__data_attribute}"
        return prefix

    @property
    def legacy_log_name_prefix(self) -> Optional[str]:
        """Build legacy log name prefix (without visitnum).

        Legacy format: {ptid}_{date}_{module} Returns None if required
        attributes are missing.
        """
        # Check required attributes
        if (
            not self.__participant_attribute
            or not self.__date_attribute
            or not self.__data_attribute
        ):
            return None

        return (
            f"{self.__participant_attribute}_"
            f"{self.__date_attribute}_"
            f"{self.__data_attribute}"
        )

    def visit_participant(self, participant: ParticipantIdentification) -> None:
        """Collect participant identification (ptid)."""
        self.__participant_attribute = participant.ptid

    def visit_visit(self, visit: VisitIdentification) -> None:
        """Collect visit identification (visitnum)."""
        self.__visit_attribute = visit.visitnum

    def visit_form(self, form: FormIdentification) -> None:
        """Collect form identification (module and packet).

        Converts to lowercase for filename compatibility.
        """
        module = form.module.lower()
        if form.packet is not None:
            self.__data_attribute = f"{module}_{form.packet.lower()}"
        else:
            self.__data_attribute = module

    def visit_image(self, image: ImageIdentification) -> None:
        """Collect image identification (modality).

        Converts to lowercase for filename compatibility.
        """
        self.__data_attribute = image.modality.lower()

    def visit_data_identification(self, data_id: DataIdentification) -> None:
        """Collect date from data identification."""
        self.__date_attribute = data_id.date


class ErrorLogTemplate(VisitLabelTemplate):
    """Template for creating the name of an error log file.

    The file name is form using the visit label as the prefix, and
    suffix and extension fields from this template.
    """

    suffix: Optional[str] = "qc-status"
    extension: Optional[str] = "log"

    def instantiate(self, record: Dict[str, Any], module: str) -> Optional[str]:
        """Instantiates the template using the visit-label built for the record
        and module as a prefix, and the suffix and extension fields from this
        template.

        Args:
          record: the data record
          module: the module name
        Returns:
          the file name if the visit label can be built. None, otherwise.
        """
        prefix = super().instantiate(record=record, module=module)
        if not prefix:
            return None

        return self.create_filename(prefix)

    def instantiate_from_data_identification(
        self, data_id: "DataIdentification"
    ) -> Optional[str]:
        """Generate QC log filename from DataIdentification.

        Creates filename that reflects the DataIdentification structure:
        - Includes visitnum if present
        - Includes packet if present (forms only)
        - Format: {ptid}[_{visitnum}]_{date}_{module}[_{packet}]_qc-status.log

        Args:
            data_id: DataIdentification with visit metadata

        Returns:
            QC log filename, or None if required fields are missing

        Examples:
            Form with visitnum and packet:
                → 12345_001_2024-01-15_a1_i_qc-status.log
            Form without visitnum (non-visit form):
                → 12345_2024-01-15_np_i_qc-status.log
            Old format (no visitnum, no packet):
                → 12345_2024-01-15_a1_qc-status.log
        """
        visitor = ErrorLogIdentificationVisitor()
        data_id.apply(visitor)

        prefix = visitor.log_name_prefix
        if prefix is None:
            return None

        return self.create_filename(prefix)

    def get_possible_filenames(self, data_id: "DataIdentification") -> list[str]:
        """Get list of possible filenames for lookup (new and legacy formats).

        Returns filenames in priority order:
        1. New format with visitnum (if present)
        2. Legacy format without visitnum

        This supports backward compatibility when looking up existing files.

        Args:
            data_id: DataIdentification with visit metadata

        Returns:
            List of possible filenames to try, in priority order
        """
        visitor = ErrorLogIdentificationVisitor()
        data_id.apply(visitor)

        filenames = set()

        # Add new format (with visitnum if present)
        if visitor.log_name_prefix:
            filenames.add(self.create_filename(visitor.log_name_prefix))

        # Add legacy format (without visitnum)
        if visitor.legacy_log_name_prefix:
            filenames.add(self.create_filename(visitor.legacy_log_name_prefix))

        return list(filenames)

    def create_filename(self, visit_label: str) -> str:
        """Creates a log file name from this template by extending the visit-
        label.

        The format of the file name is "<visit-label>_<suffix>.<extension>".

        Args:
          visit_label: the visit label
        Returns:
          the file name build by extending the visit label
        """
        return f"{visit_label}_{self.suffix}.{self.extension}"


@api_retry
def update_file_info(file: FileEntry, custom_info: Dict[str, Any]):
    """Set custom info for the given file.

    Args:
        file: FileEntry object to set info
        custom_info: custom info dict,
                     any existing info under specified top-level key will be replaced

    Raise:
        ApiException: If failed to update custom info
    """

    # Note: have to use update_info() here for reset to take effect
    # Using update() will not delete any existing data
    file.update_info(custom_info)


def get_log_contents(log_file: FileEntry) -> str:
    """Returns contents of the log file.

    Decodes content as UTF-8

    Args:
      log_file: the file entry
    Return:
       the contents of the log_file
    """
    try:
        return log_file.read().decode("utf-8")
    except ApiException as error:
        log.error(
            f"Error in reading log file {log_file.name}: {error}",
        )
        ts = (dt.now()).strftime(DEFAULT_DATE_TIME_FORMAT)
        reset_str = f"{ts} RESET due to read errors\n"
        return reset_str


def create_log_entry(*, gear_name: str, state: str, errors: FileErrorList) -> str:
    """Creates a log entry as a string.

    A log entry consists of a time-stamped row that indicates the gear and the
    QC status.
    If the status is FAIL, the list of errors is serialized on subsequent rows.

    Args:
      gear_name: the gear name
      state: the QC status for the gear job
      errors: the list of QC errors
    Returns:
      the string representation for the QC log entry
    """
    timestamp = (dt.now()).strftime(DEFAULT_DATE_TIME_FORMAT)
    entry = f"{timestamp} QC Status: {gear_name.upper()} - {state.upper()}\n"
    for qc_error in errors:
        entry += qc_error.model_dump_json(by_alias=True) + "\n"
    return entry


def update_error_log_and_qc_metadata(
    *,
    error_log_name: str,
    destination_prj: ProjectAdaptor,
    gear_name: str,
    state: str,
    errors: FileErrorList,
    reset_qc_metadata: MetadataCleanupFlag = "NA",
) -> bool:
    """Update project level error log file and store error metadata in
    file.info.qc.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_name: gear that generated errors
        state: gear execution status [PASS|FAIL|IN REVIEW|NA]
        errors: list of error objects, expected to be JSON dicts
        reset_qc_metadata: flag to reset metadata from previous runs:
            ALL - clean all, set this for the first gear in submission pipeline.
            GEAR - reset only current gear metadata from previous runs.
            NA - do not reset (Default).

    Returns:
        bool: True if metadata update is successful, else False
    """
    qc_info: Optional[FileQCModel] = FileQCModel(qc={})
    contents = ""

    current_log = destination_prj.get_file(error_log_name)
    # append to existing error details if any
    if current_log:
        if reset_qc_metadata != "ALL":
            try:
                qc_info = FileQCModel.create(current_log)
            except ValidationError as error:
                log.error(
                    "Error loading QC metadata for file %s: %s", current_log.name, error
                )
                return False

        contents = get_log_contents(current_log)

    if qc_info is None:
        return False

    contents += create_log_entry(
        gear_name=gear_name, state=state.upper(), errors=errors
    )

    new_file = destination_prj.upload_file_contents(
        filename=error_log_name, contents=contents, content_type="text"
    )
    if new_file is None:
        return False

    error_list = errors.list()
    if reset_qc_metadata == "NA":
        # extend existing errors with new errors. maintaining order
        file_errors = qc_info.get_errors(gear_name)
        file_errors.extend(error_list)
        error_list = file_errors

    qc_info.set_errors(
        gear_name=gear_name,
        status=state.upper(),  # type: ignore
        errors=error_list,
    )
    try:
        update_file_info(file=new_file, custom_info=qc_info.model_dump(by_alias=True))
    except ApiException as error:
        log.error(
            "Error in setting QC metadata in file %s - %s",
            error_log_name,
            error,
        )
        return False

    return True


def update_gear_qc_status(
    *,
    error_log_name: str,
    destination_prj: ProjectAdaptor,
    gear_name: str,
    status: QCStatus,
) -> None:
    """Updates the QC status in error log file (file.info.qc.<gear_name>) for
    the specified gear.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_name: gear to update the QC status
        status: new status
    """
    current_log = destination_prj.get_file(error_log_name)
    if not current_log:
        log.warning(
            f"Cannot find error log file {error_log_name} in "
            f"project {destination_prj.group}/{destination_prj.label}"
        )
        return

    try:
        qc_info = FileQCModel.create(current_log)
    except ValidationError as error:
        log.warning(f"QC info not found in error log file {error_log_name}: {error}")
        return

    gear_info = qc_info.get(gear_name=gear_name)
    if not gear_info:
        log.warning(
            f"QC info not found for gear {gear_name} in error log file {error_log_name}"
        )
        return

    # Preserve existing errors while updating status
    existing_errors = gear_info.get_errors()
    qc_info.set_errors(gear_name=gear_name, status=status, errors=existing_errors)
    try:
        update_file_info(
            file=current_log, custom_info=qc_info.model_dump(by_alias=True)
        )
    except ApiException as error:
        log.error(f"Error in setting QC status in file {current_log.name}: {error}")


def reset_error_log_metadata_for_gears(
    *, error_log_name: str, destination_prj: ProjectAdaptor, gear_names: List[str]
) -> None:
    """Reset error log file QC metadata in file.info.qc.<gear_name> for the
    specified gears.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_names: list of gears to clear qc metadata
    """
    current_log = destination_prj.get_file(error_log_name)
    if not current_log:
        return

    try:
        qc_info = FileQCModel.create(current_log)
    except ValidationError:
        # If we can't parse the QC info, there's nothing to reset
        return

    # Remove specified gears from the QC model
    for gear_name in gear_names:
        if gear_name in qc_info.qc:
            del qc_info.qc[gear_name]

    try:
        update_file_info(
            file=current_log, custom_info=qc_info.model_dump(by_alias=True)
        )
    except ApiException as error:
        log.error(f"Error in resetting QC metadata in file {current_log.name}: {error}")
