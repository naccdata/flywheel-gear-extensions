"""Defines QCVisitor classes for creating reports from QC data."""

import logging
import re
from abc import ABC, abstractmethod
from csv import DictWriter
from typing import Any, Callable, List, Optional, Union

from flywheel.models.file_entry import FileEntry
from flywheel.models.project import Project
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.module_types import ModuleName
from pydantic import BaseModel, ValidationError

from outputs.error_models import (
    ClearedAlertModel,
    ClearedAlertProvenance,
    FileError,
    FileQCModel,
    GearQCModel,
    QCVisitor,
    ValidationModel,
    VisitKeys,
)

log = logging.getLogger(__name__)


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
    But is meant to be used for several files by calling `set_visit()` with the
    visit keys derived from the log file name before applying the visitor to the
    file qc model.
    This pattern is shown here

    ```
    file_visitor.set_visit(visit_keys)
    qc_model.apply(file_visitor)
    ```

    and is implemented in `ProjectReportVisitor.visit_file()`.

    This visitor stores a VisitKeys object for the visit associated with the
    file, and the gear name for the gear model being visited.
    """

    def __init__(self) -> None:
        self.__visit_details: Optional[VisitKeys] = None
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

    def clear(self) -> None:
        """Clears the table in this visitor."""
        self.__table = []

    def set_visit(self, visit: VisitKeys) -> None:
        self.clear()
        self.__visit_details = visit

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

    def __init__(self, transformer: ValidationTransformer) -> None:
        """Initializes a status visitor.

        The transformer is used to create the report object to be added to the
        table of this visitor.

        Args:
          transformer: callable to transform gear name and validation object
          to a report object.
        """
        super().__init__()
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

    def __init__(self, transformer: ErrorTransformer) -> None:
        """Initializes an error visitor.

        The transformer is used to create the report object to be added to the
        table of this visitor.

        Args:
          transformer: callable to transform gear name and file error object
          to a report object.
        """
        super().__init__()
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


class ProjectReportVisitor:
    """Defines a partial hierarchy visitor for gathering submission status data
    from a project.

    Applies the file_visitor to qc-status log files in a project to
    gather report objects. Report objects are written to the DictWriter.
    """

    def __init__(
        self,
        *,
        adcid: int,
        file_visitor: FileQCReportVisitor,
        writer: ReportWriter,
        ptid_set: Optional[set[str]] = None,
        modules: Optional[set[ModuleName]] = None,
    ) -> None:
        self.__adcid = adcid
        self.__writer = writer
        self.__modules = modules
        self.__ptid_set = ptid_set
        self.__file_visitor = file_visitor
        pattern = r"^([!-~]{1,10})_(\d{4}-\d{2}-\d{2})_(\w+)_qc-status.log$"
        self.__matcher = re.compile(pattern)

    def __get_visit_key(self, filename: str) -> Optional[VisitKeys]:
        """Returns a VisitKeys object with ptid, module and visit date set
        extracted from a qc-status log filename.

        Additionally, checks that ptid and module correspond to those in this
        visitor.

        Args:
          filename: the filename
        Returns:
          the visit keys object with values set if filename matches the log
          filename pattern.
          None, otherwise.
        """
        match = self.__matcher.match(filename)
        if not match:
            return None

        ptid = match.group(1)
        if self.__ptid_set is not None and ptid not in self.__ptid_set:
            return None

        module = match.group(3).upper()
        if self.__modules is not None and module.upper() not in self.__modules:
            return None

        visitdate = match.group(2)

        return VisitKeys(ptid=ptid, date=visitdate, module=module)

    def visit_file(self, file: FileEntry) -> None:
        """Applies the file visitor to a qc-status log file with matching ptid
        and module, and writes the gathered report objects using the writer.

        Args:
          file: the file entry
        """
        visit = self.__get_visit_key(file.name)
        if visit is None:
            return

        if visit.ptid is None:
            log.warning("No visit PTID for %s", file.name)
            return
        if visit.module is None:
            log.warning("No visit module for %s", file.name)
            return
        if visit.date is None:
            log.warning("No visit date for file %s", file.name)
            return

        file = file.reload()

        try:
            qc_model = FileQCModel.model_validate(file.info)
        except ValidationError as error:
            log.warning("Failed to load QC data for %s: %s", file.name, error)
            return

        visit.adcid = self.__adcid
        self.__file_visitor.set_visit(visit)
        try:
            qc_model.apply(self.__file_visitor)
        except QCTransformerError as error:
            log.error(
                "Unexpected QC transformation error for file %s: %s", file.name, error
            )
            return

        for item in self.__file_visitor.table:
            self.__writer.writerow(item.model_dump())

    def visit_project(self, project: Union[Project, ProjectAdaptor]) -> None:
        """Applies the file_visitor to qc-status log files in the project.

        Note: this takes a flywheel.Project object so that can be used in
        nacc-common without exposing proxy object

        Args:
          project: the project
        """
        for file in project.files:
            if not self.__matcher.match(file.name):
                continue

            file = file.reload()
            if not file.info.get("qc"):
                log.warning("file does not have qc: %s", file.name)
                continue

            self.visit_file(file)
