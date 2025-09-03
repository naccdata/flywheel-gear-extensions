# ruff: noqa: SLF001
"""Tests preprocessing checks.

NOTE: Many of these checks rely heavily on Flywheel querying, which
isn't easily mocked. So some tests are more sanity checks than
anything, and some checks aren't yet tested here in the interest
of time.
"""

import copy
from typing import Dict, List, Optional, Tuple

from configs.ingest_configs import ModuleConfigs
from datastore.forms_store import FormsStore
from keys.keys import DefaultValues, FieldNames, MetadataKeys, SysErrorCodes
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

    def query_form_data_with_custom_filters(
        self,
        **kwargs,
    ) -> Optional[List[Dict[str, str]]]:
        return self.__form_data

    def get_visit_data(self, **kwargs) -> Dict[str, str] | None:
        return self.__form_data[0] if self.__form_data else None


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
        error_writer.clear()  # clear for next test

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

    def test_check_initial_visit_new_subject(self, uds_module_configs, uds_pp_context):
        """Tests the _check_initial_visit check when it is an initial packet
        and new subject."""
        processor, error_writer, _ = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        # make it a new subject
        uds_pp_context.subject_lbl = "new-subject"

        for packet in ["I", "I4"]:
            uds_pp_context.input_record[FieldNames.PACKET] = packet
            assert processor._check_initial_visit(uds_pp_context)

        # will fail if FVP since no initial packet exists
        uds_pp_context.input_record[FieldNames.PACKET] = "F"
        assert not processor._check_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.MISSING_IVP)

    def test_check_initial_visit_ivp_in_same_batch(
        self, uds_module_configs, uds_pp_context
    ):
        """Tests the _check_initial_visit check when an IVP visit was passed in
        the same batch."""
        processor, error_writer, _ = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        # make them the same but FVP packet so they conflict
        uds_pp_context.ivp_record = copy.deepcopy(uds_pp_context.input_record)
        uds_pp_context.input_record[FieldNames.PACKET] = "F"
        assert not processor._check_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.LOWER_FVP_VISITDATE)

        # make it an earlier date, should still fail
        uds_pp_context.input_record[FieldNames.DATE_COLUMN] = "1900-01-01"
        assert not processor._check_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.LOWER_FVP_VISITDATE)

        # make it a later date, should now pass
        uds_pp_context.input_record[FieldNames.DATE_COLUMN] = "3000-01-01"
        assert processor._check_initial_visit(uds_pp_context)

    def test_check_initial_visit_ivp_exists(self, uds_module_configs, uds_pp_context):
        """Tests the _check_initial_visit check when an IVP visit exists in FW
        and is queried."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        # first fail on multiple IVP
        forms_store.set_form_data([{"dummy": "dummy"} for _ in range(2)])
        assert not processor._check_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.MULTIPLE_IVP)

        # next set same record in forms store; since still IVP, make it
        # the exact same record, so seen as an update
        input_record = uds_pp_context.input_record
        input_record.update(
            {
                f"{MetadataKeys.FORM_METADATA_PATH}.visitdate": "2025-01-01",
                f"{MetadataKeys.FORM_METADATA_PATH}.visitnum": "1",
                f"{MetadataKeys.FORM_METADATA_PATH}.packet": "I",
            }
        )
        forms_store.set_form_data([copy.deepcopy(input_record)])
        assert processor._check_initial_visit(uds_pp_context)

        # now make a "different" IVP record by changing the date, so will fail
        input_record[FieldNames.DATE_COLUMN] = "2025-02-02"
        assert not processor._check_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.IVP_EXISTS)

        # alternatively different visitnumber
        input_record[FieldNames.DATE_COLUMN] = "2025-01-01"
        input_record[FieldNames.VISITNUM] = "0"
        assert not processor._check_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.IVP_EXISTS)

        # allow if I4
        input_record[FieldNames.PACKET] = "I4"
        assert processor._check_initial_visit(uds_pp_context)

    def test_check_udsv4_initial_visit(self, uds_module_configs, uds_pp_context):
        """Tests the _check_udsv4_initial_visit check, i.e. I4 requirements."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )
        input_record = uds_pp_context.input_record
        input_record.update(
            {
                FieldNames.PACKET: "I4",
                f"{MetadataKeys.FORM_METADATA_PATH}.visitdate": "2025-01-01",
                f"{MetadataKeys.FORM_METADATA_PATH}.visitnum": "1",
            }
        )

        # fail on missing UDSv3 visit for I4
        assert not processor._check_udsv4_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.MISSING_UDS_V3)

        # fail when legacy visit exists but is same as current I4 record
        legacy_record = copy.deepcopy(input_record)
        forms_store.set_form_data([legacy_record])
        assert not processor._check_udsv4_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.LOWER_I4_VISITDATE)

        # fail when there is an I4/FVP conflict
        input_record[FieldNames.PACKET] = "F"
        assert not processor._check_udsv4_initial_visit(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.MISSING_UDS_I4)

        # pass when just FVP (ensured valid by other preprocessing checks)
        forms_store.set_form_data([])
        assert processor._check_udsv4_initial_visit(uds_pp_context)

    def test_check_supplement_module_exact_match(
        self, uds_module_configs, uds_pp_context
    ):
        """Tests the _check_supplement_module check - exact matches."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        # will fail at first since nothing in forms store; different error code
        # from not an exact match though
        assert not processor._check_supplement_module(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.UDS_NOT_MATCH)

        # add input record to form store so they match exactly
        input_record = uds_pp_context.input_record
        input_record.update(
            {
                f"{MetadataKeys.FORM_METADATA_PATH}.{k}": v
                for k, v in input_record.items()
            }
        )

        forms_store.set_form_data([copy.deepcopy(input_record)])
        assert processor._check_supplement_module(uds_pp_context)

        # modify packet to followup visit so that they don't match anymore
        input_record[FieldNames.PACKET] = "F"
        assert not processor._check_supplement_module(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.INVALID_MODULE_PACKET)

        # I4 should pass
        input_record[FieldNames.PACKET] = "I4"
        assert processor._check_supplement_module(uds_pp_context)

        # modify visitnum so that they don't match anymore
        input_record[FieldNames.VISITNUM] = "dummy"
        assert not processor._check_supplement_module(uds_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.UDS_NOT_MATCH)

    def test_check_supplement_module_not_exact(self, np_module_configs, np_pp_context):
        """Tests the _check_supplement_module check - exact match not required."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.NP_MODULE, np_module_configs
        )

        # will fail at first since nothing in forms store; different error
        # code from an exact match though
        assert not processor._check_supplement_module(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.UDS_NOT_EXIST)

        # add dummy record to store; should pass because it just has to exit
        forms_store.set_form_data([{"dummy": "dummy"}])
        assert processor._check_supplement_module(np_pp_context)

    def test_is_existing_visit(self, uds_module_configs, uds_pp_context):
        """Tests the is_existing_visit method."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        # will return false at first since nothing in form store, so NOT an
        # existing visit
        input_record = uds_pp_context.input_record
        input_record.update(
            {
                "file_id": "12345",
                "file.file_id": "12345",
                "file.name": "dummy.csv",
                "file.parents.acquisition": "dummy-acquisition",
            }
        )
        assert not processor.is_existing_visit(input_record=input_record)

        # add input record to form store so they match exactly
        forms_store.set_form_data([input_record])
        assert processor.is_existing_visit(input_record=input_record)

        # modify it slightly so they don't match exactly
        form_data = copy.deepcopy(input_record)
        form_data["dummy"] = "dummy"
        forms_store.set_form_data([form_data])
        assert not processor.is_existing_visit(input_record=input_record)

    def test_check_clinical_forms(self, np_module_configs, np_pp_context):
        """Tests the _check_clinical_forms check."""
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.NP_MODULE, np_module_configs
        )

        # should fail at first because there are no supplement visits in our form store
        assert not processor._check_clinical_forms(np_pp_context)
        self.__assert_error_raised(
            error_writer, SysErrorCodes.CLINICAL_FORM_REQUIRED_NP
        )

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
        """Tests the _check_np_mlst_restrictions check.

        file.info.forms.json must be added to all MLST record values
        just by the way the data is queried.
        """
        processor, error_writer, forms_store = self.__setup_processor(
            DefaultValues.NP_MODULE, np_module_configs
        )

        # fails if there is no MLST form
        assert not processor._check_np_mlst_restrictions(np_pp_context)

        # add MLST forms; make sure it actually tests the most recent
        test_record = {
            f"{MetadataKeys.FORM_METADATA_PATH}.deathyr": "2025",
            f"{MetadataKeys.FORM_METADATA_PATH}.deathmo": "8",
            f"{MetadataKeys.FORM_METADATA_PATH}.deathdy": "27",
            f"{MetadataKeys.FORM_METADATA_PATH}.deceased": "1",
            f"{MetadataKeys.FORM_METADATA_PATH}.autopsy": "1",
        }
        forms_store.set_form_data(
            [
                test_record,
                {
                    f"{MetadataKeys.FORM_METADATA_PATH}.deathyr": "INVALID",
                    f"{MetadataKeys.FORM_METADATA_PATH}.deathmo": "INVALID",
                    f"{MetadataKeys.FORM_METADATA_PATH}.deathdy": "INVALID",
                    f"{MetadataKeys.FORM_METADATA_PATH}.autopsy": "0",
                },
            ]
        )

        np_pp_context.input_record.update(
            {"npdodyr": "2025", "npdodmo": "8", "npdoddy": "27"}
        )

        # pass on DODs match and autopsy and deceased == 1
        assert processor._check_np_mlst_restrictions(np_pp_context)

        # fail on autopsy != 1 or deceased != 1
        for value in [0, 2, None]:
            test_record[f"{MetadataKeys.FORM_METADATA_PATH}.autopsy"] = value  # type: ignore
            assert not processor._check_np_mlst_restrictions(np_pp_context)
            self.__assert_error_raised(
                error_writer, SysErrorCodes.DEATH_DENOTED_ON_MLST
            )

            test_record[f"{MetadataKeys.FORM_METADATA_PATH}.autopsy"] = 1  # type: ignore
            test_record[f"{MetadataKeys.FORM_METADATA_PATH}.deceased"] = value  # type: ignore
            assert not processor._check_np_mlst_restrictions(np_pp_context)
            self.__assert_error_raised(
                error_writer, SysErrorCodes.DEATH_DENOTED_ON_MLST
            )
            test_record[f"{MetadataKeys.FORM_METADATA_PATH}.deceased"] = 1  # type: ignore

        # fail when the DODs don't match
        test_record.update(
            {
                f"{MetadataKeys.FORM_METADATA_PATH}.deathmo": 12,  # type: ignore
            }
        )
        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)

        # fail DOD when day/month is 99
        test_record.update(
            {
                f"{MetadataKeys.FORM_METADATA_PATH}.deathmo": 99,  # type: ignore
                f"{MetadataKeys.FORM_METADATA_PATH}.deathdy": "99",
            }
        )

        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)

        # fail DOD when MLST is None
        test_record.update(
            {
                f"{MetadataKeys.FORM_METADATA_PATH}.deathyr": None,  # type: ignore
                f"{MetadataKeys.FORM_METADATA_PATH}.deathmo": None,  # type: ignore
                f"{MetadataKeys.FORM_METADATA_PATH}.deathdy": None,  # type: ignore
            }
        )
        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)

        # fail DOD when both dates are None
        np_pp_context.input_record.update(
            {"npdodyr": None, "npdodmo": None, "npdoddy": None}
        )
        assert not processor._check_np_mlst_restrictions(np_pp_context)
        self.__assert_error_raised(error_writer, SysErrorCodes.DEATH_DATE_MISMATCH)

        # fail when all fail
        test_record[f"{MetadataKeys.FORM_METADATA_PATH}.autopsy"] = None  # type: ignore
        test_record[f"{MetadataKeys.FORM_METADATA_PATH}.deceased"] = None  # type: ignore
        assert not processor._check_np_mlst_restrictions(np_pp_context)

        assert len(error_writer.errors()) == 3
        file_error_dec = error_writer.errors()[0]
        file_error_aut = error_writer.errors()[1]
        file_error_dod = error_writer.errors()[2]

        assert file_error_dec.error_code == SysErrorCodes.DEATH_DENOTED_ON_MLST
        assert file_error_aut.error_code == SysErrorCodes.DEATH_DENOTED_ON_MLST
        assert file_error_dod.error_code == SysErrorCodes.DEATH_DATE_MISMATCH
