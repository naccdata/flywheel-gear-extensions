import pytest
from configs.ingest_configs import ModuleConfigs
from preprocess.preprocessor_helpers import (
    PreprocessingContext,
)


@pytest.fixture(scope="function")
def uds_module_configs():
    """Create UDS ModuleConfigs."""
    configs = {
        "hierarchy_labels": {
            "session": {"template": "FORMS-VISIT-${visitnum}", "transform": "upper"},
            "acquisition": {"template": "${module}", "transform": "upper"},
            "filename": {"template": "${subject}_${session}_${acquisition}.json"},
        },
        "required_fields": [
            "ptid",
            "adcid",
            "visitnum",
            "visitdate",
            "packet",
            "formver",
        ],
        "initial_packets": ["I", "I4"],
        "followup_packets": ["F"],
        "versions": ["4.0"],
        "date_field": "visitdate",
        "legacy_module": "UDS",
        "legacy_date": "visitdate",
        "optional_forms": {
            "4.0": {
                "I": ["a1a", "a2", "b1", "b3", "b5", "b6", "b7"],
                "I4": ["a1a", "a2", "b1", "b3", "b5", "b6", "b7"],
                "F": ["a1a", "a2", "b1", "b3", "b5", "b6", "b7"],
            }
        },
        "preprocess_checks": [
            "duplicate-record",
            "version",
            "packet",
            "optional-forms",
            "ivp",
            "udsv4-ivp",
            "visit-conflict",
        ],
    }
    return ModuleConfigs(**configs)


@pytest.fixture(scope="function")
def uds_pp_context():
    """Creates a dummy UDS PreprocessingContext for testing."""
    naccid = "NACC000000"
    input_record = {
        "naccid": naccid,
        "ptid": "dummy-ptid",
        "adcid": "0",
        "visitnum": "1",
        "visitdate": "2025-01-01",
        "packet": "I",
        "formver": "4.0",
    }

    return PreprocessingContext(
        subject_lbl=naccid,
        input_record=input_record,
        line_num=1,
    )


@pytest.fixture(scope="function")
def np_module_configs():
    """Create NP ModuleConfigs."""
    configs = {
        "hierarchy_labels": {
            "session": {"template": "NP-RECORD-${npformdate}", "transform": "upper"},
            "acquisition": {"template": "${module}", "transform": "upper"},
            "filename": {
                "template": "${subject}_${session}_${acquisition}.json",
                "transform": "upper",
            },
        },
        "required_fields": ["packet", "formver", "adcid", "ptid", "npformdate"],
        "initial_packets": ["NP"],
        "followup_packets": [],
        "versions": ["11.0"],
        "date_field": "npformdate",
        "preprocess_checks": [
            "duplicate-record",
            "version",
            "packet",
            "clinical-forms",
            "np-mlst-restrictions",
        ],
    }
    return ModuleConfigs(**configs)


@pytest.fixture(scope="function")
def np_pp_context():
    """Creates a dummy NP PreprocessingContext for testing."""
    naccid = "NACC000000"
    input_record = {
        "naccid": naccid,
        "ptid": "dummy-ptid",
        "adcid": "0",
        "npformdate": "2025-01-01",
        "packet": "NP",
        "formver": "4.0",
    }

    return PreprocessingContext(
        subject_lbl=naccid,
        input_record=input_record,
        line_num=1,
    )
