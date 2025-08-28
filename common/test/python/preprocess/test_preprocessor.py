"""Tests preprocessing checks."""

from typing import Dict, List, Optional, Tuple

from datastore.forms_store import FormsStore
from keys.keys import DefaultValues, FieldNames
from outputs.error_writer import ListErrorWriter
from preprocess.preprocessor import FormPreprocessor


class MockFormsStore(FormsStore):
    """Mock form store for testing."""
    def __init__(self):
        self.__form_data = None

    def is_new_subject(self, subject_lbl: str) -> bool:
        return subject_lbl == "new-subject"

    def set_form_data(self, form_data: List[Dict[str, str]]) -> None:
        """Set the form data to control what query_form_data returns."""
        self.__form_data = form_data

    def query_form_data(self, **kwargs) -> Optional[List[Dict[str, str]]]:
        return self.__form_data


class TestFormPreprocessor:
    """Tests FormPreprocessor methods and preprocessing checks."""

    def __setup_processor(
        self, uds_module_configs
    ) -> Tuple[MockFormsStore, FormPreprocessor]:
        """Create a generic UDS preprocessor for testing.

        Returns both the MockFormStore (to be able to control form data per test)
            and the FormProcessor.
        """
        forms_store = MockFormsStore()
        processor = FormPreprocessor(
            primary_key=FieldNames.NACCID,
            forms_store=forms_store,
            module=DefaultValues.UDS_MODULE,
            module_configs=uds_module_configs,
            error_writer=ListErrorWriter(
                container_id="dummy",
                fw_path="dummy/dummy",
            )
        )

        return processor, forms_store

    def test_is_accepted_packet(self, uds_module_configs, uds_pp_context):
        """Tests the is_accepted_packet method."""
        processor, _ = self.__setup_processor(uds_module_configs)
        for packet in ["I", "I4", "F"]:
            uds_pp_context.input_record.update({"packet": packet})
            assert processor.is_accepted_packet(uds_pp_context)

        uds_pp_context.input_record.update({"packet": "invalid"})
        assert not processor.is_accepted_packet(uds_pp_context)
