"""
Tests the CSVTransformVisitor
Mainly tests the batch CSV internal record duplicates since that
doesn't require querying Flywheel.
"""
import json
import pytest

from typing import Any, Dict, List, Optional, Tuple

from configs.ingest_configs import ModuleConfigs
from form_csv_app.main import CSVTransformVisitor
from keys.keys import DefaultValues, FieldNames, SysErrorCodes
from outputs.errors import ListErrorWriter, preprocess_errors
from preprocess.preprocessor import FormPreprocessor
from transform.transformer import (
    FieldTransformations,
    TransformerFactory,
)

from test_mocks.mock_flywheel import MockProject
from test_mocks.mock_forms_store import MockFormsStore

# global date field key
DATE_FIELD = 'visitdate'


def run_header_test(
    visitor: CSVTransformVisitor, error_writer: ListErrorWriter):
    """Test the visit_header method"""
    assert not visitor.visit_header(['invalid', 'headers', 'formver'])

    # just look at specific fields since stuff like time/set order will vary
    errors = error_writer.errors()
    assert len(errors) == 1
    assert errors[0]['code'] == 'missing-field'
    assert errors[0]['message'].startswith(
        "Missing one or more required field(s)")


def create_visitor(
    test_header: bool = False,
    transform_schema: Dict[str, Any] = None
    ) -> Tuple[CSVTransformVisitor, MockProject, MockFormsStore]:
    """Create a visitor with some default/consistent values
    for testing. Returns the visitor, mocked project, and mocked
    form store.

    Args:
        test_header: Whether or not to test the header. This
            only needs to be set to true once.
    """

    # dummy error writer
    error_writer = ListErrorWriter(
        container_id='dummy_id',
        fw_path='dummy_path')

    # transformer
    if transform_schema:
        transformer_factory = TransformerFactory(FieldTransformations.\
            model_validate_json(json.dumps(transform_schema)))
    else:
        transformer_factory = TransformerFactory(FieldTransformations())

    # just use UDS for testing
    module_configs = ModuleConfigs(
        initial_packets=['I', 'I4'],
        followup_packets=['F'],
        versions=['4'],
        date_field=DATE_FIELD,
        legacy_module=DefaultValues.UDS_MODULE,
        legacy_date=DATE_FIELD)

    form_store = MockFormsStore(date_field=DATE_FIELD)
    project = MockProject()

    preprocessor = FormPreprocessor(
        primary_key='naccid',
        forms_store=form_store,
        module_info={DefaultValues.UDS_MODULE: module_configs},
        error_writer=error_writer
    )

    visitor = CSVTransformVisitor(
        id_column='naccid',
        module=DefaultValues.UDS_MODULE,
        error_writer=error_writer,
        transformer_factory=transformer_factory,
        preprocessor=preprocessor,
        module_configs=module_configs,
        gear_name='form-transformer',
        project=project)

    # test the header if specified
    if test_header:
        run_header_test(visitor, error_writer)
        error_writer.clear()

    # have the visitor visit the header already so
    # individual tests don't have to do it
    assert visitor.visit_header(
        ['naccid', DATE_FIELD, FieldNames.MODULE,
         FieldNames.VISITNUM, FieldNames.FORMVER,
         FieldNames.PTID])
    assert not error_writer.errors()

    return visitor, project, form_store


def create_record(data: Dict[str, str]):
    """Create record with default values, then append
    test-specific data.

    Args:
        data: Data to add for specific test
    """
    record = {
        FieldNames.MODULE: 'uds',
        FieldNames.FORMVER: '4.0',
        FieldNames.VISITNUM: '1',
        DATE_FIELD: '2025-01-01',
        'naccid': 'local-test',
        'dummy': 'dummy_val',
        'ptid': 'dummy-ptid',
        'packet': 'I'
    }

    record.update(data)
    return record


def get_qc_errors(project: MockProject):
    """Get the first QC error from mock project

    Args:
        project: The MockProject to pull the error log from
    """
    # tests are designed to only expect 1 error log but there
    # will often be multiple in real scenarios
    error_logs = {k: v for k, v in project.files.items()
                  if k.endswith('_qc-status.log')}
    assert error_logs

    error_file = list(error_logs.values())[0]
    return error_file.info['qc']['form-transformer']['validation']['data']


class TestCSVTransformVisitor:
    """Tests the CSVTransformVisitor."""

    def test_visit_header(self):
        """Test visit_header."""
        create_visitor(test_header=True)

    def test_bad_row(self):
        """Test row is missing required fields."""
        visitor, project, _ = create_visitor()
        record = create_record({})
        record.pop('naccid')
        assert not visitor.visit_row(record, 0)

        qc = get_qc_errors(project)
        assert len(qc) == 1
        assert qc[0]['code'] == 'empty-field'
        assert qc[0]['message'].startswith("Required field(s)")
        assert qc[0]['message'].endswith('cannot be blank')

    def test_mismatched_modules(self):
        """Test records in CSV belong to different modules."""
        visitor, project, _ = create_visitor()
        record = create_record({'module': 'ftld'})
        assert not visitor.visit_row(record, 0)
        record = create_record({'module': 'lbd'})
        assert not visitor.visit_row(record, 1)

        qc = get_qc_errors(project)
        assert len(qc) == 2
        assert qc[0]['code'] == 'unexpected-value'
        assert qc[0]['message'] == 'Expected UDS for field module'
        assert qc[0]['expected'] == 'UDS'
        assert qc[0]['value'] == 'FTLD'
        assert qc[1]['code'] == 'unexpected-value'
        assert qc[1]['message'] == 'Expected UDS for field module'
        assert qc[1]['expected'] == 'UDS'
        assert qc[1]['value'] == 'LBD'

    def test_bad_transform(self):
        """Test bad transform - does a simple one just to check
        the errors."""
        schema = {
            'UDS': [{
                'version_map': {
                    'fieldname': 'transform',
                    'value_map': {"1": "do_transform"},
                    'default': 'no_transform'
                },
                'nofill': True,
                'fields': {
                    'do_transform': ['bad1', 'bad2', 'bad3']
                }
            }]
        }
        visitor, project, _ = create_visitor(transform_schema=schema)
        record = create_record({
            'transform': "1", 'bad1': True, 'bad2': 'hello', 'bad3': 4})
        assert not visitor.visit_row(record, 0)

        # will pass this
        record = create_record({'bad1': None, 'bad2': None, 'bad3': None})
        assert visitor.visit_row(record, 1)

        qc = get_qc_errors(project)
        assert len(qc) == 1
        code = SysErrorCodes.EXCLUDED_FIELDS
        assert qc[0]['code'] == code
        assert qc[0]['message'] == preprocess_errors[code]