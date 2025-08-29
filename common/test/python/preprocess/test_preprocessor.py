# ruff: noqa: SLF001
"""Tests preprocessing checks."""

from typing import Dict, List, Optional, Tuple

from configs.ingest_configs import ModuleConfigs
from datastore.forms_store import FormsStore
from keys.keys import DefaultValues, FieldNames, SysErrorCodes
from outputs.error_writer import ListErrorWriter
from outputs.errors import preprocess_errors
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
        self,
        module: str,
        module_configs: ModuleConfigs,
    ) -> Tuple[FormPreprocessor, ListErrorWriter, MockFormsStore]:
        """Create a generic UDS preprocessor for testing.

        Returns FormProcessor
                ListErrorWriter - to ensure the correct error was raised
                MockFormStore - to be able to control form data per test
        """
        forms_store = MockFormsStore()
        error_writer = ListErrorWriter(
            container_id="dummy",
            fw_path="dummy/dummy",
        )

        processor = FormPreprocessor(
            primary_key=FieldNames.NACCID,
            forms_store=forms_store,
            module=module,
            module_configs=module_configs,
            error_writer=error_writer,
        )

        return processor, error_writer, forms_store

    def __assert_error_raised(
        self,
        error_writer: ListErrorWriter,
        error_code: str,
        message: Optional[str] = None,
    ) -> None:
        """Ensure the correct error was set in the error writer."""
        if not message:
            message = preprocess_errors[error_code]

        assert len(error_writer.errors()) == 1
        file_error = error_writer.errors()[0]

        assert file_error.error_code == error_code
        assert file_error.message == message

    def test_is_accepted_packet(self, uds_module_configs, uds_pp_context):
        """Tests the is_accepted_packet check."""
        processor, error_writer, _ = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        for packet in ["I", "I4", "F"]:
            uds_pp_context.input_record.update({"packet": packet})
            assert processor.is_accepted_packet(uds_pp_context)

        uds_pp_context.input_record.update({"packet": "invalid"})
        assert not processor.is_accepted_packet(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.INVALID_PACKET)

    def test_is_accepted_version(self, uds_module_configs, uds_pp_context):
        """Tests the is_accepted_version check."""
        processor, error_writer, _ = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )
        assert processor.is_accepted_version(uds_pp_context)

        uds_pp_context.input_record.update({"formver": "5.0"})
        assert not processor.is_accepted_version(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.INVALID_VERSION)

    def test_check_optional_forms_status_none(self, np_module_configs, np_pp_context):
        """Tests the _check_optional_forms_status check when there are no
        optional forms."""
        processor, error_writer, _ = self.__setup_processor(
            DefaultValues.NP_MODULE, np_module_configs
        )
        assert processor._check_optional_forms_status(np_pp_context)

    def test_check_optional_forms_status_set(self, uds_module_configs, uds_pp_context):
        """Tests the _check_optional_forms_status check when there are optional
        forms."""
        processor, error_writer, _ = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        # requires us setting all the MODExx variables
        uds_pp_context.input_record.update(
            {
                "modea1a": 0,
                "modea2": 1,
                "modeb1": 2,
                "modeb3": 3,
                "modeb5": 2,
                "modeb6": 1,
                "modeb7": 0,
            }
        )
        assert processor._check_optional_forms_status(uds_pp_context)

        # requires us setting all the MODExx variables
        uds_pp_context.input_record.update({"modeb1": None, "modeb7": None})
        assert not processor._check_optional_forms_status(uds_pp_context)
        self.__assert_error_raised(
            error_writer,
            SysErrorCodes.MISSING_SUBMISSION_STATUS,
            message=(
                "Missing submission status (MODE<form name>) variables "
                "['modeb1', 'modeb7'] for one or more optional forms"
            ),
        )

    def test_check_clinical_forms(self, np_module_configs, np_pp_context):
        """Tests the _check_clinical_forms check."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.NP_MODULE, np_module_configs
        )

        # should fail at first because there are no supplement visits in our form store
        assert not processor._check_clinical_forms(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.CLINICAL_FORM_REQUIRED)

        # test for each allowed module
        # for each module, add a proper supplement visit to the forms store; should not
        # matter how many visits are found
        for i, module in enumerate(
            [
                DefaultValues.UDS_MODULE,
                DefaultValues.BDS_MODULE,
                DefaultValues.MDS_MODULE,
            ]
        ):
            forms_store.set_form_data([{"module": module} for _ in range(i + 1)])
            assert processor._check_clinical_forms(np_pp_context)

    def test_check_np_mlst_restrictions(self, np_module_configs, np_pp_context):
        """Tests the _check_np_mlst_restrictions check."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.NP_MODULE, np_module_configs
        )

        # passes by default if there is no MLST form
        assert processor._check_np_mlst_restrictions(np_pp_context)

        # add MLST forms; make sure it actually tests the most recent
        test_record = {
            "deathyr": "2025",
            "deathmo": "8",
            "deathdy": "27",
            "autopsy": "1",
        }
        forms_store.set_form_data(
            [
                test_record,
                {
                    "deathyr": "INVALID",
                    "deathmo": "INVALID",
                    "deathdy": "INVALID",
                    "autopsy": "0",
                },
            ]
        )

        np_pp_context.input_record.update(
            {"npdodyr": "2025", "npdodmo": "8", "npdoddy": "27"}
        )

        # pass on DODs match and autopsy == 1
        assert processor._check_np_mlst_restrictions(np_pp_context)

        # fail on autopsy != 1
        for value in [0, 2, None]:
            test_record["autopsy"] = value  # type: ignore
            assert not processor._check_np_mlst_restrictions(np_pp_context)
            self.__assert_error_raised(error_writer, SysErrorCodes.AUTOPSY_NP_INVALID)
            error_writer.clear()

        # fail when the DODs don't match
        test_record.update({"deathmo": 12, "autopsy": 1})  # type: ignore
        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)
        error_writer.clear()

        # pass DOD when day/month is 99, so it compares years
        test_record.update({"deathmo": 99, "deathdy": "99"})  # type: ignore
        assert processor._check_np_mlst_restrictions(np_pp_context)

        # fail DOD when MLST is None
        test_record.update({"deathyr": None, "deathmo": None, "deathdy": None})  # type: ignore
        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)
        error_writer.clear()

        # fail DOD when both dates are None
        np_pp_context.input_record.update(
            {"npdodyr": None, "npdodmo": None, "npdoddy": None}
        )
        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)
        error_writer.clear()

        # fail when both fail
        test_record["autopsy"] = None  # type: ignore
        assert not processor._check_np_mlst_restrictions(np_pp_context)

        assert len(error_writer.errors()) == 2
        file_error_dod = error_writer.errors()[0]
        file_error_aut = error_writer.errors()[1]

        assert file_error_dod.error_code == SysErrorCodes.DEATH_DATE_MISMATCH
        assert file_error_aut.error_code == SysErrorCodes.AUTOPSY_NP_INVALID
