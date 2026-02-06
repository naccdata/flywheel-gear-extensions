"""Tests the milestone forms transform and pre-processing checks."""

import json
from typing import Any, Dict, Optional, Tuple

from configs.ingest_configs import FormProjectConfigs
from form_csv_app.main import CSVTransformVisitor
from keys.keys import SysErrorCodes
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    preprocess_errors,
)
from preprocess.preprocessor import FormPreprocessor
from test_mocks.mock_configs import milestone_ingest_configs
from test_mocks.mock_flywheel import MockProjectAdaptor
from test_mocks.mock_forms_store import MockFormsStore
from transform.transformer import (
    FieldTransformations,
    TransformerFactory,
)


def create_mlst_visitor(
    transform_schema: Optional[Dict[str, Any]] = None,
) -> Tuple[CSVTransformVisitor, MockProjectAdaptor, MockFormsStore]:
    """Create a visitor with some default/consistent values for testing.

    Returns the visitor, mocked project, and mocked form store.
    """

    module = "MLST"
    module_configs = milestone_ingest_configs()
    header = [
        FieldNames.NACCID,
        FieldNames.DATE_COLUMN,
        FieldNames.MODULE,
        FieldNames.FORMVER,
        FieldNames.PTID,
        FieldNames.ADCID,
        FieldNames.PACKET,
    ]
    date_field = FieldNames.DATE_COLUMN

    # dummy error writer
    error_writer = ListErrorWriter(container_id="dummy_id", fw_path="dummy_path")

    # transformer
    if transform_schema:
        transformer_factory = TransformerFactory(
            FieldTransformations.model_validate_json(json.dumps(transform_schema))
        )
    else:
        transformer_factory = TransformerFactory(FieldTransformations())

    form_store = MockFormsStore(date_field=date_field)
    project = MockProjectAdaptor(label="mlst-project")

    form_configs = FormProjectConfigs(
        primary_key=FieldNames.NACCID,
        accepted_modules=[module.upper()],
        module_configs={module.upper(): module_configs},
    )

    preprocessor = FormPreprocessor(
        form_configs=form_configs,
        forms_store=form_store,
        module=module,
        module_configs=module_configs,
        error_writer=error_writer,
    )

    visitor = CSVTransformVisitor(
        id_column="naccid",
        module=module,
        error_writer=error_writer,
        transformer_factory=transformer_factory,
        preprocessor=preprocessor,
        module_configs=module_configs,
        gear_name="form-transformer",
        project=project,
    )

    # have the visitor visit the header already so
    # individual tests don't have to do it
    assert visitor.visit_header(header)
    assert not error_writer.errors()

    return visitor, project, form_store


def create_milestones_record(data: Dict[str, Any]):
    """Create milestones record with default values, then append test-specific
    data.

    Args:
        data: Data to add for specific test
    """
    record = {
        FieldNames.NACCID: "dummy-naccid",
        FieldNames.MODULE: "mlst",
        FieldNames.FORMVER: "3.0",
        FieldNames.PACKET: "M",
        FieldNames.PTID: "dummy-ptid",
        FieldNames.ADCID: 0,
        FieldNames.DATE_COLUMN: "2025-01-01",
        "dummy": "dummy_val",
    }

    record.update(data)
    return record


def get_qc_errors(project: MockProjectAdaptor):
    """Get the first QC error from mock project.

    Args:
        project: The MockProject to pull the error log from
    """
    # tests are designed to only expect 1 error log but there
    # will often be multiple in real scenarios
    error_logs = [
        file for file in project.files if file.name.endswith("_qc-status.log")
    ]
    assert error_logs

    error_file = error_logs[0]
    return error_file.info["qc"]["form-transformer"]["validation"]["data"]


class TestMilestonesTransform:
    """Tests the Milestones form transforms and pre-processing checks."""

    def test_valid_milestones_record(self):
        """Test valid milestones record."""
        visitor, project, _ = create_mlst_visitor()
        record = create_milestones_record({})
        assert visitor.visit_row(record, 0)

    def test_invalid_milestones_record(self):
        """Test missing required fields."""

        visitor, project, _ = create_mlst_visitor()
        record = create_milestones_record({})
        record.pop(FieldNames.FORMVER)
        assert not visitor.visit_row(record, 0)

    def test_missing_supplement_module(self):
        """Test missing supplement module."""
        visitor, project, _ = create_mlst_visitor()
        record = create_milestones_record({})
        assert visitor.visit_row(record, 0)
        assert not visitor.process_current_batch()
        qc = get_qc_errors(project)
        assert len(qc) == 1
        code = SysErrorCodes.UDS_NOT_EXIST
        assert qc[0]["code"] == code
        assert qc[0]["message"] == preprocess_errors[code]

    def test_duplicate_milestones_record(self):
        """Test duplicate milestones records."""
        visitor, project, _ = create_mlst_visitor()
        record = create_milestones_record({})

        for i in range(3):
            assert visitor.visit_row(record, i)

        assert not visitor.process_current_batch()
        qc = get_qc_errors(project)
        assert len(qc) == 3
        for failed_form in qc:
            code = SysErrorCodes.DUPLICATE_VISIT
            assert failed_form["code"] == code
            assert failed_form["message"] == preprocess_errors[code]
