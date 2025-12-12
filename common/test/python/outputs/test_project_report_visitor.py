from csv import DictReader, DictWriter
from datetime import date
from io import StringIO
from typing import Any, Generator

import pytest
from configs.ingest_configs import ErrorLogTemplate
from nacc_common.error_models import (
    FileQCModel,
    GearQCModel,
    QCStatus,
    ValidationModel,
    VisitKeys,
)
from nacc_common.qc_report import (
    DictReportWriter,
    ProjectReportVisitor,
    QCReportBaseModel,
    StatusReportVisitor,
    WriterTableVisitor,
)
from pydantic import ValidationError
from test_mocks.mock_flywheel import MockProject


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


class StatusReportTestModel(QCReportBaseModel):
    status: QCStatus
    adcid: int
    ptid: str


@pytest.fixture(scope="session")
def test_transformer():
    def transformer(
        gear_name: str, visit: VisitKeys, validation_model: ValidationModel
    ) -> StatusReportTestModel:
        assert validation_model.state, "expect validation state to be set"
        assert visit.adcid, "expect visit adcid to be set"
        assert visit.ptid, "expect visit ptid to be set"
        return StatusReportTestModel(
            stage=gear_name,
            adcid=visit.adcid,
            ptid=visit.ptid,
            status=validation_model.state,
        )

    return transformer


@pytest.fixture(scope="session")
def visit_details():
    yield VisitKeys(
        adcid=999, ptid="delta01", module="UDS", date=date.today().isoformat()
    )


@pytest.fixture(scope="session")
def file_project(status_file_model, visit_details) -> Generator[MockProject, Any, Any]:
    project = MockProject("dummy_project")
    qc_model = status_file_model
    log_filename = ErrorLogTemplate().instantiate(
        {"ptid": visit_details.ptid, "visitdate": visit_details.date},
        module=visit_details.module,
    )
    project.upload_file(
        file={"name": log_filename, "contents": "blah", "info": qc_model.model_dump()}
    )
    project.upload_file(
        file={"name": "not_a_log_file.csv", "contents": "blah", "info": {}}
    )
    yield project


class TestProjectReportVisitor:
    def test_fieldnames(self):
        fields = list(StatusReportTestModel.model_fields.keys())
        assert fields == ["stage", "status", "adcid", "ptid"]

    def test_project(self, file_project, test_transformer, visit_details):
        assert file_project.label == "dummy_project"

        stream = StringIO()
        writer = DictWriter(
            stream, fieldnames=list(StatusReportTestModel.model_fields.keys())
        )
        writer.writeheader()

        # Create factory function for StatusReportVisitor
        def file_visitor_factory(file, adcid):
            return StatusReportVisitor(file, adcid, test_transformer)

        visitor = ProjectReportVisitor(
            adcid=visit_details.adcid,
            modules={visit_details.module},
            ptid_set={visit_details.ptid},
            file_visitor_factory=file_visitor_factory,
            table_visitor=WriterTableVisitor(DictReportWriter(writer)),
        )
        visitor.visit_project(file_project)
        stream.seek(0)
        assert bool(stream.readline())
        stream.seek(0)
        reader = DictReader(stream)
        model_list = []
        for row in reader:
            try:
                model = StatusReportTestModel.model_validate(row)
                model_list.append(model)
            except ValidationError as error:
                print(error)
                raise AssertionError("should load") from error

        assert model_list == [
            StatusReportTestModel(
                stage="one",
                status="FAIL",
                adcid=visit_details.adcid,
                ptid=visit_details.ptid,
            ),
            StatusReportTestModel(
                stage="two",
                status="PASS",
                adcid=visit_details.adcid,
                ptid=visit_details.ptid,
            ),
        ]
