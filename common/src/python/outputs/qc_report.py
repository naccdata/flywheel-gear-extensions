"""Defines QCVisitor classes for creating reports from QC data."""

from typing import Callable, List, Optional

from pydantic import BaseModel

from outputs.error_models import (
    ClearedAlertModel,
    ClearedAlertProvenance,
    FileError,
    FileQCModel,
    GearQCModel,
    QCVisitor,
    ValidationModel,
)


class QCReportBaseModel(BaseModel):
    """Base model for QC reports.

    Includes the gear name.
    """

    gear: str


class FileQCVisitor(QCVisitor):
    """Base implementation of the QCVisitor abstract base class."""

    def __init__(self) -> None:
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


ValidationTransformer = Callable[[str, ValidationModel], QCReportBaseModel]


class StatusVisitor(FileQCVisitor):
    """Defines a QC reporting visitor for gathering submission status report
    for a file."""

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
        if validation_model.state is None:
            return
        if self.gear_name is None:
            return

        self.add(self.__transformer(self.gear_name, validation_model))


ErrorTransformer = Callable[[str, FileError], QCReportBaseModel]


class ErrorVisitor(FileQCVisitor):
    """Defines a QC reporting visitor for gathering error report for a file."""

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

        self.add(self.__transformer(self.gear_name, file_error))
