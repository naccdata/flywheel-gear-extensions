"""Tests the UDS CSVTransformVisitor, mainly tests the batch CSV records error
checks."""

import json
from typing import Any, Dict, Optional, Tuple

from configs.ingest_configs import FormProjectConfigs
from error_logging.error_logger import ErrorLogTemplate
from form_csv_app.main import CSVTransformVisitor
from keys.keys import DefaultValues, SysErrorCodes
from nacc_common.error_models import ValidationModel
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    preprocess_errors,
)
from preprocess.preprocessor import FormPreprocessor
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_flywheel import MockProjectAdaptor
from test_mocks.mock_forms_store import MockFormsStore
from transform.transformer import (
    FieldTransformations,
    TransformerFactory,
)

# global date field key
DATE_FIELD = "visitdate"


def run_header_test(visitor: CSVTransformVisitor, error_writer: ListErrorWriter):
    """Test the visit_header method."""
    assert not visitor.visit_header(["invalid", "headers", "formver"])

    # just look at specific fields since stuff like time/set order will vary
    errors = error_writer.errors()
    assert len(errors) == 1
    assert errors[0].error_code == "missing-field"
    assert errors[0].message.startswith("Missing one or more required field(s)")


def create_uds_visitor(
    test_header: bool = False, transform_schema: Optional[Dict[str, Any]] = None
) -> Tuple[CSVTransformVisitor, MockProjectAdaptor, MockFormsStore]:
    """Create a visitor with some default/consistent values for testing.
    Returns the visitor, mocked project, and mocked form store.

    Args:
        test_header: Whether or not to test the header. This
            only needs to be set to true once.
    """

    # dummy error writer
    error_writer = ListErrorWriter(container_id="dummy_id", fw_path="dummy_path")

    # transformer
    if transform_schema:
        transformer_factory = TransformerFactory(
            FieldTransformations.model_validate_json(json.dumps(transform_schema))
        )
    else:
        transformer_factory = TransformerFactory(FieldTransformations())

    # just use UDS for testing
    module_configs = uds_ingest_configs()
    form_store = MockFormsStore(date_field=DATE_FIELD)
    project = MockProjectAdaptor(label="uds-project")

    form_configs = FormProjectConfigs(
        primary_key=FieldNames.NACCID,
        accepted_modules=["UDS"],
        module_configs={"UDS": module_configs},
    )

    preprocessor = FormPreprocessor(
        form_configs=form_configs,
        forms_store=form_store,
        module=DefaultValues.UDS_MODULE,
        module_configs=module_configs,
        error_writer=error_writer,
    )

    visitor = CSVTransformVisitor(
        id_column="naccid",
        module=DefaultValues.UDS_MODULE,
        error_writer=error_writer,
        transformer_factory=transformer_factory,
        preprocessor=preprocessor,
        module_configs=module_configs,
        gear_name="form-transformer",
        project=project,
    )

    # test the header if specified
    if test_header:
        run_header_test(visitor, error_writer)
        error_writer.clear()

    # have the visitor visit the header already so
    # individual tests don't have to do it
    assert visitor.visit_header(
        [
            FieldNames.NACCID,
            DATE_FIELD,
            FieldNames.MODULE,
            FieldNames.VISITNUM,
            FieldNames.FORMVER,
            FieldNames.PTID,
            FieldNames.ADCID,
            FieldNames.PACKET,
        ]
    )
    assert not error_writer.errors()

    return visitor, project, form_store


def create_record(data: Dict[str, Any]):
    """Create record with default values, then append test-specific data.

    Args:
        data: Data to add for specific test
    """
    record = {
        FieldNames.NACCID: "dummy-naccid",
        FieldNames.MODULE: "uds",
        FieldNames.FORMVER: "4.0",
        FieldNames.VISITNUM: "1",
        FieldNames.PACKET: "I",
        FieldNames.PTID: "dummy-ptid",
        FieldNames.ADCID: 0,
        DATE_FIELD: "2025-01-01",
        "modea1a": 0,
        "modea2": 0,
        "modeb1": 0,
        "modeb3": 0,
        "modeb5": 0,
        "modeb6": 0,
        "modeb7": 0,
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


class TestUDSTransform:
    """Tests the UDS transforms and pre-processing checks."""

    def test_visit_header(self):
        """Test visit_header."""
        create_uds_visitor(test_header=True)

    def test_bad_row(self):
        """Test row is missing required fields."""
        visitor, project, _ = create_uds_visitor()
        record = create_record({})
        record.pop("naccid")
        assert not visitor.visit_row(record, 0)

        qc = get_qc_errors(project)
        assert len(qc) == 1
        assert qc[0]["code"] == "empty-field"
        assert qc[0]["message"].startswith("Required field(s)")
        assert qc[0]["message"].endswith("cannot be blank")

    def test_mismatched_modules(self):
        """Test records in CSV belong to different modules."""
        visitor, project, _ = create_uds_visitor()

        record = create_record({"module": "ftld"})
        assert not visitor.visit_row(record, 0)
        qc = get_qc_errors(project)
        assert len(qc) == 1

        record = create_record({"module": "lbd"})
        assert not visitor.visit_row(record, 1)
        qc = get_qc_errors(project)
        assert len(qc) == 2

        assert qc[0]["code"] == "unexpected-value"
        assert qc[0]["message"] == "Expected UDS for field module"
        assert qc[0]["expected"] == "UDS"
        assert qc[0]["value"] == "FTLD"
        assert qc[1]["code"] == "unexpected-value"
        assert qc[1]["message"] == "Expected UDS for field module"
        assert qc[1]["expected"] == "UDS"
        assert qc[1]["value"] == "LBD"

    def test_bad_transform(self):
        """Test bad transform - does a simple one just to check
        the errors."""
        schema = {
            "UDS": [
                {
                    "version_map": {
                        "fieldname": "transform",
                        "value_map": {"1": "do_transform"},
                        "default": "no_transform",
                    },
                    "nofill": True,
                    "fields": {"do_transform": ["bad1", "bad2", "bad3"]},
                }
            ]
        }
        visitor, project, _ = create_uds_visitor(transform_schema=schema)
        record = create_record(
            {"transform": "1", "bad1": True, "bad2": "hello", "bad3": 4}
        )
        assert not visitor.visit_row(record, 0)
        qc = get_qc_errors(project)
        assert len(qc) == 1

        # will pass this
        record = create_record({"bad1": None, "bad2": None, "bad3": None})
        assert visitor.visit_row(record, 1)

        qc = get_qc_errors(project)
        assert len(qc) == 1
        code = SysErrorCodes.EXCLUDED_FIELDS
        assert qc[0]["code"] == code
        assert qc[0]["message"] == preprocess_errors[code].format(
            ["bad1", "bad2", "bad3"]
        )

    def test_already_exists(self):
        """Test that the subject already exists - this is allowed"""
        visitor, project, form_store = create_uds_visitor()
        record = create_record({})
        form_store.add_subject(
            subject_lbl=record["naccid"],
            form_data=record,
            file_name=f"{record['naccid']}.json",
        )

        # allowed when exactly the same
        assert visitor.visit_row(record, 0)

    def test_update_existing_visits_error_logs(self):
        """Tests the existing_visits_error_logs method works as expected.

        Adds a bunch of records that "already exist but failed before".
        """
        visitor, project, form_store = create_uds_visitor()

        # create "failed" files that already exist in the project
        records = [create_record({"naccid": f"failed-{x}"}) for x in range(3)]
        for i, record in enumerate(records):
            file_name = ErrorLogTemplate().instantiate(
                module=record["module"], record=record
            )
            assert file_name
            form_store.add_subject(
                subject_lbl=record["naccid"], form_data=record, file_name=file_name
            )  # type: ignore

            # also update the project file's metadata to a failed state
            project.upload_file(
                file={
                    "name": file_name,
                    "contents": json.dumps(record),
                    "info": {
                        "qc": {
                            "form-transformer": {
                                "validation": {
                                    "state": "FAIL",
                                    "data": [{"msg": "some old failures"}],
                                }
                            }
                        }
                    },
                }
            )

            assert visitor.visit_row(record, i)

        # all records should now be in the visitor.__existing_visits
        # check that after updating the states get set to TRUE
        visitor.update_existing_visits_error_log()
        validation_passed = ValidationModel(
            data=[], cleared=[], state="PASS"
        ).model_dump(by_alias=True)
        for record in records:
            file_name = ErrorLogTemplate().instantiate(
                module=record["module"], record=record
            )
            assert file_name

            file = project.get_file(file_name)
            assert file
            assert file.info
            assert (
                file.info["qc"]["form-transformer"]["validation"] == validation_passed
            )

    def test_current_batch_duplicates(self):
        """Test duplicates in current batch."""
        visitor, project, _ = create_uds_visitor()
        record = create_record({})

        for i in range(3):
            assert visitor.visit_row(record, i)

        assert not visitor.process_current_batch()
        qc = get_qc_errors(project)
        assert len(qc) == 3
        for failed_form in qc:
            code = SysErrorCodes.DUPLICATE_VISIT
            assert failed_form["code"] == code
            assert failed_form["message"] == preprocess_errors[code]

    def test_current_batch_different_visit_date(self):
        """Tests same visit number but different visit date correctly raises
        error."""
        visitor, project, _ = create_uds_visitor()
        record = create_record({"visitnum": "3", "visitdate": "2025-01-01"})
        assert visitor.visit_row(record, 0)
        record = create_record({"visitnum": "3", "visitdate": "2024-01-01"})
        assert visitor.visit_row(record, 1)

        assert not visitor.process_current_batch()
        qc = get_qc_errors(project)
        assert len(qc) == 1
        code = SysErrorCodes.DIFF_VISITDATE
        assert qc[0]["code"] == code
        assert qc[0]["message"] == preprocess_errors[code]

    # def test_current_batch_lower_visit_num(self):
    #     """Tests invalid visit numbers correctly raises error.

    #     In this case only one of the rows is marked "invalid".
    #     """
    #     visitor, project, _ = create_visitor()
    #     record = create_record({'visitnum': "3", 'visitdate': '2025-01-01'})
    #     assert visitor.visit_row(record, 0)
    #     record = create_record({'visitnum': "5", 'visitdate': '2024-01-01'})
    #     assert visitor.visit_row(record, 1)

    #     assert not visitor.process_current_batch()
    #     qc = get_qc_errors(project)
    #     assert len(qc) == 1
    #     code = SysErrorCodes.LOWER_VISITNUM
    #     assert qc[0]['code'] == code
    #     assert qc[0]['message'] == preprocess_errors[code]

    def test_non_numeric_visitnum(self):
        """Tests non-numeric visit numbers."""
        visitor, project, _ = create_uds_visitor()
        record = create_record(
            {
                "ptid": "new-ptid1",
                "packet": "I",
                "visitnum": "1N",
                "visitdate": "2023-01-01",
            }
        )
        assert visitor.visit_row(record, 0)
        record = create_record(
            {
                "ptid": "new-ptid1",
                "packet": "F",
                "visitnum": "1F",
                "visitdate": "2025-01-01",
            }
        )
        assert visitor.visit_row(record, 1)

        assert visitor.process_current_batch()
