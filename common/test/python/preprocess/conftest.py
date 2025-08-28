import pytest
from configs.ingest_configs import ModuleConfigs
from preprocess.preprocess_helpers import (
    PreprocessingContext,
)


@pytest.fixture(scope="function")
def uds_module_configs():
    """Create default UDS ModuleConfigs for general testing."""
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
        # leave empty for tests to define which they are testing
        "preprocess_checks": [],
    }
    return ModuleConfigs(**configs)


@pytest.fixture(scope="function")
def uds_pp_context():
    """Creates a dummy UDS PreprocessingContext for testing."""
    input_record = {
        "naccid": "NACC000000",
        "ptid": "dummy-ptid",
        "adcid": "0",
        "visitnum": "1",
        "visitdate": "2025-01-01",
        "packet": "I",
        "formver": "4.0",
    }

    return PreprocessingContext(
        input_record=input_record,
        line_num=1,
    )
