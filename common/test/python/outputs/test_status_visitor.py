from typing import Callable

import pytest
from outputs.error_models import (
    FileQCModel,
    GearQCModel,
    QCStatus,
    ValidationModel,
    VisitKeys,
)
from outputs.qc_report import QCReportBaseModel, StatusReportVisitor


class StatusReportTestModel(QCReportBaseModel):
    status: QCStatus
    ptid: str


@pytest.fixture(scope="session")
def test_transformer():
    def transformer(
        gear_name: str, visit: VisitKeys, validation_model: ValidationModel
    ) -> StatusReportTestModel:
        assert validation_model.state, "expect validation state to be set"
        assert visit.ptid, "expect visit ptid to be set"
        return StatusReportTestModel(
            stage=gear_name, ptid=visit.ptid, status=validation_model.state
        )

    return transformer


@pytest.fixture(scope="session")
def status_file_model():
    return FileQCModel(
        qc={
            "one": GearQCModel(
                validation=ValidationModel(data=[], cleared=None, state="FAIL")
            ),
            "two": GearQCModel(
                validation=ValidationModel(data=[], cleared=None, state="PASS")
            ),
        }
    )


class TestStatusVisitor:
    def test_empty(self, test_transformer: Callable[..., StatusReportTestModel]):
        qc_model = FileQCModel(qc={})
        visitor = StatusReportVisitor(test_transformer)
        visitor.set_visit(VisitKeys(ptid="dummy"))
        qc_model.apply(visitor)

        assert visitor.table == []

    def test_status(self, status_file_model, test_transformer):
        qc_model = status_file_model
        visitor = StatusReportVisitor(test_transformer)
        visitor.set_visit(VisitKeys(ptid="dummy"))
        qc_model.apply(visitor)

        assert visitor.table == [
            StatusReportTestModel(stage="one", ptid="dummy", status="FAIL"),
            StatusReportTestModel(stage="two", ptid="dummy", status="PASS"),
        ]
