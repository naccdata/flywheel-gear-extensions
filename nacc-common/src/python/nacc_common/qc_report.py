"""Defines QCVisitor classes for creating reports from QC data."""

import logging
import re
from abc import ABC, abstractmethod
from csv import DictWriter
from typing import Any, Callable, List, Optional

from flywheel.models.file_entry import FileEntry
from pydantic import BaseModel, ValidationError

from nacc_common.error_models import (
    ClearedAlertModel,
    ClearedAlertProvenance,
    FileError,
    FileQCModel,
    GearQCModel,
    QCVisitor,
    ValidationModel,
    VisitKeys,
)

ModuleName = str
log = logging.getLogger(__name__)

# TODO: Consider consolidating QC filename pattern usage - currently duplicated
# between ProjectReportVisitor and FileQCReportVisitor
QC_FILENAME_PATTERN = r"^([!-~]{1,10})_(\d{4}-\d{2}-\d{2})_(\w+)_qc-status.log$"


def extract_visit_keys(file: FileEntry) -> VisitKeys:
    """Extract visit keys from QC log filename.

    Args:
        file: The QC log file

    Returns:
        VisitKeys object with extracted data if filename matches pattern.
        None, otherwise.
    """
    matcher = re.compile(QC_FILENAME_PATTERN)
    match = matcher.match(file.name)
    if not match:
        raise TypeError(f"file name does not match qc-status log: {file.name}")

    ptid = match.group(1)
    visitdate = match.group(2)
    module = match.group(3).upper()

    return VisitKeys(ptid=ptid, date=visitdate, module=module)


class QCReportBaseModel(BaseModel):
    """Base model for QC reports.

    Includes the gear name as the pipeline stage
    """

    stage: str


ValidationTransformer = Callable[[str, VisitKeys, ValidationModel], QCReportBaseModel]
ErrorTransformer = Callable[[str, VisitKeys, FileError], QCReportBaseModel]


class QCTransformerError(Exception):
    """Error for transformers."""


class FileQCReportVisitor(QCVisitor):
    """Base implementation of the QCVisitor abstract base class.

    The entrypoint for this visitor is the visit_file_model() method, applied
    to the FileQCModel derived from the file.info.qc of a qc-status log file.

    This visitor extracts visit details from the QC log filename and stores
    them for use during processing.
    """

    def __init__(self, visit: VisitKeys) -> None:
        self.__visit_details = visit
        self.__gear_name: Optional[str] = None
        self.__table: List[QCReportBaseModel] = []

    @property
    def gear_name(self) -> Optional[str]:
        """Returns the active gear name.

        The gear name is set before apply is called on the gear model.
        Otherwise, it should be None.

        Returns:
          the gear name if currently set. None, otherwise.
        """
        return self.__gear_name

    @property
    def table(self) -> List[QCReportBaseModel]:
        """Returns the table of report objects added to this visitor.

        Returns:
          the table of report objects
        """
        return self.__table

    @property
    def visit_details(self) -> Optional[VisitKeys]:
        """Returns the details for the visit associated with the file."""
        return self.__visit_details

    def add(self, item: QCReportBaseModel) -> None:
        """Appends a report object to the table.

        Args:
          item: the report object
        """
        self.__table.append(item)

    def visit_file_model(self, file_model: FileQCModel) -> None:
        """Defines visit for a file model.

        Applies this visitor to each gear model.
        Sets the gear name before each apply, and resets after.

        Args:
          file_model: the model to visit
        """
        for gear_name, gear_model in file_model.qc.items():
            self.__gear_name = gear_name
            gear_model.apply(self)
            self.__gear_name = None

    def visit_gear_model(self, gear_model: GearQCModel) -> None:
        """Defines visit for a gear model.

        Applies this visitor to the validation model.

        Args:
          gear_model: the model to visit
        """
        gear_model.validation.apply(self)

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        pass

    def visit_file_error(self, file_error: FileError) -> None:
        pass

    def visit_cleared_alert(self, cleared_alert: ClearedAlertModel) -> None:
        pass

    def visit_alert_provenance(self, alert_provenance: ClearedAlertProvenance) -> None:
        pass


class StatusReportVisitor(FileQCReportVisitor):
    """Defines a QC reporting visitor for gathering submission status report
    for a file.

    To use this class, define an extension of QCReportBaseModel, and a
    function (or other Callable) that matches the ValidationTransformer
    type and maps to  the report model.
    """

    def __init__(self, visit: VisitKeys, transformer: ValidationTransformer) -> None:
        """Initializes a status visitor.

        The transformer is used to create the report object to be added to the
        table of this visitor.

        Args:
          file: the QC log file
          adcid: the ADRC ID
          transformer: callable to transform gear name and validation object
          to a report object.
        """
        super().__init__(visit)
        self.__transformer = transformer

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        """Defines a visit for a validation model.

        If the state of the validation model is defined, applies the transformer
        to the model to create a report object to add to the table.

        Args:
          validation_model: the model to visit
        """
        if self.visit_details is None:
            return
        if validation_model.state is None:
            return
        if self.gear_name is None:
            return

        self.add(
            self.__transformer(self.gear_name, self.visit_details, validation_model)
        )


class ErrorReportVisitor(FileQCReportVisitor):
    """Defines a QC reporting visitor for gathering error report for a file.

    To use this class, define an extension of QCReportBaseModel, and a
    function (or other Callable) that matches the ErrorTransformer type
    and maps to  the report model.
    """

    def __init__(self, visit: VisitKeys, transformer: ErrorTransformer) -> None:
        """Initializes an error visitor.

        The transformer is used to create the report object to be added to the
        table of this visitor.

        Args:
          file: the QC log file
          adcid: the ADRC ID
          transformer: callable to transform gear name and file error object
          to a report object.
        """
        super().__init__(visit)
        self.__transformer = transformer

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        """Defines a visit for a validation model.

        If the state of the validation model is "fail", applies the visitor to
        each of the file error objects in the model.

        Args:
          validation_model: the model to visit
        """
        state = validation_model.state
        if state is not None and state.lower() == "pass":
            return

        for error_model in validation_model.data:
            error_model.apply(self)

    def visit_file_error(self, file_error: FileError) -> None:
        """Defines a visit for a file error.

        Applies the transformer to the gear name and file error object to
        create the report object that is added to the table.

        Args:
          file_error: the model to visit
        """
        if self.gear_name is None:
            return
        if self.visit_details is None:
            return

        self.add(self.__transformer(self.gear_name, self.visit_details, file_error))


class ReportWriter(ABC):
    @abstractmethod
    def writerow(self, row: dict[str, Any]) -> None:
        pass


class ListReportWriter(ReportWriter):
    def __init__(self, result: list[dict[str, Any]]):
        self.__result = result

    def writerow(self, row: dict[str, Any]) -> None:
        self.__result.append(row)


class DictReportWriter(ReportWriter):
    def __init__(self, writer: DictWriter):
        self.__writer = writer

    def writerow(self, row: dict[str, Any]) -> None:
        self.__writer.writerow(row)


class ReportTableVisitor(ABC):
    def visit_table(self, table: List[QCReportBaseModel]) -> None:
        for row in table:
            self.visit_row(row)

    @abstractmethod
    def visit_row(self, row: QCReportBaseModel) -> None:
        pass


class WriterTableVisitor(ReportTableVisitor):
    def __init__(self, writer: ReportWriter) -> None:
        self.__writer = writer

    def visit_row(self, row: QCReportBaseModel) -> None:
        self.__writer.writerow(row.model_dump(by_alias=True))


FileQCReportVisitorBuilder = Callable[[FileEntry, int], FileQCReportVisitor]


class ProjectReportVisitor:
    """Defines a partial hierarchy visitor for gathering submission status data
    from a project.

    Creates a fresh file visitor for each QC log file using the provided
    factory.
    """

    def __init__(
        self,
        *,
        adcid: int,
        file_visitor_factory: FileQCReportVisitorBuilder,
        table_visitor: ReportTableVisitor,
        ptid_set: Optional[set[str]] = None,
        modules: Optional[set[str]] = None,
        file_filter: Callable[[FileEntry], bool] = lambda file: True,
    ) -> None:
        self.__adcid = adcid
        self.__table_visitor = table_visitor
        self.__modules = modules
        self.__ptid_set = ptid_set
        self.__file_visitor_factory = file_visitor_factory
        self.__file_filter = file_filter
        self.__matcher = re.compile(QC_FILENAME_PATTERN)

    def __should_process_file(self, filename: str) -> bool:
        """Check if file should be processed based on ptid and module filters.

        Args:
          filename: the filename to check
        Returns:
          True if file should be processed, False otherwise.
        """
        match = self.__matcher.match(filename)
        if not match:
            return False

        ptid = match.group(1)
        if self.__ptid_set is not None and ptid not in self.__ptid_set:
            return False

        module = match.group(3).upper()
        return self.__modules is None or module.upper() in self.__modules

    def visit_file(self, file: FileEntry) -> None:
        """Creates a file visitor for the QC log file and processes it.

        Args:
          file: the file entry
        """
        if not self.__should_process_file(file.name):
            return

        file = file.reload()

        try:
            qc_model = FileQCModel.create(file)
        except ValidationError as error:
            log.warning("Failed to load QC data for %s: %s", file.name, error)
            return

        # Create fresh visitor for this file using factory
        file_visitor = self.__file_visitor_factory(file, self.__adcid)

        # Check if visit details were successfully extracted
        if file_visitor.visit_details is None:
            log.warning("Could not extract visit details from %s", file.name)
            return

        try:
            qc_model.apply(file_visitor)
        except QCTransformerError as error:
            log.error(
                "Unexpected QC transformation error for file %s: %s", file.name, error
            )
            return

        self.__table_visitor.visit_table(file_visitor.table)

    def visit_project(self, project) -> None:
        """Applies the file_visitor to qc-status log files in the project.

        Note: the project is intentionally untyped to avoid dependencies issues
        in nacc-common, but the type is Union[Project, ProjectAdaptor]

        Args:
          project: the project (either flywheel.Project or ProjectAdaptor)
        """
        for file in project.files:
            if not self.__matcher.match(file.name):
                continue
            if not self.__file_filter(file):
                continue

            file = file.reload()
            if not file.info.get("qc"):
                log.warning("file does not have qc: %s", file.name)
                continue

            self.visit_file(file)
