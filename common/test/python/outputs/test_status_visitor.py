from typing import Callable

import pytest
from nacc_common.error_models import (
    FileQCModel,
    GearQCModel,
    QCStatus,
    ValidationModel,
    VisitKeys,
)
from nacc_common.qc_report import (
    QCReportBaseModel,
    StatusReportVisitor,
    extract_visit_keys,
)
from test_mocks.mock_flywheel import MockFile


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


@pytest.fixture(scope="session")
def mock_file():
    return MockFile("dummy01_2023-01-01_UDS_qc-status.log")


class TestStatusVisitor:
    def test_empty(
        self, mock_file, test_transformer: Callable[..., StatusReportTestModel]
    ):
        qc_model = FileQCModel(qc={})
        visit = extract_visit_keys(mock_file)
        visit.adcid = 999
        visitor = StatusReportVisitor(visit, transformer=test_transformer)
        qc_model.apply(visitor)

        assert visitor.table == []

    def test_status(self, mock_file, status_file_model, test_transformer):
        qc_model = status_file_model
        visit = extract_visit_keys(mock_file)
        visit.adcid = 999
        visitor = StatusReportVisitor(visit, transformer=test_transformer)
        qc_model.apply(visitor)

        assert visitor.table == [
            StatusReportTestModel(stage="one", ptid="dummy01", status="FAIL"),
            StatusReportTestModel(stage="two", ptid="dummy01", status="PASS"),
        ]
