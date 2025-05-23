"""Methods to generate mock configs for local testing."""

from configs.ingest_configs import ModuleConfigs


def uds_ingest_configs() -> ModuleConfigs:
    """Create form ingest configs for UDS module."""
    module_configs = {
        "hierarchy_labels": {
            "session": {
                "template": "FORMS-VISIT-${visitnum}",
                "transform": "upper"
            },
            "acquisition": {
                "template": "${module}",
                "transform": "upper"
            },
            "filename": {
                "template": "${subject}_${session}_${module}.json",
                "transform": "upper"
            }
        },
        "required_fields":
        ["ptid", "adcid", "visitnum", "visitdate", "packet", "formver"],
        "initial_packets": ["I", "I4"],
        "followup_packets": ["F"],
        "versions": ["4.0"],
        "date_field":
        "visitdate",
        "legacy_module":
        "UDS",
        "legacy_date":
        "visitdate",
        "optional_forms": {
            "4.0": {
                "I": ["a1a", "a2", "b1", "b3", "b5", "b6", "b7"],
                "I4": ["a1a", "a2", "b1", "b3", "b5", "b6", "b7"],
                "F": ["a1a", "a2", "b1", "b3", "b5", "b6", "b7"]
            }
        },
        "preprocess_checks": [
            "duplicate-record", "version", "packet", "optional-forms", "ivp",
            "udsv4-ivp", "visit-conflict"
        ]
    }

    return ModuleConfigs.model_validate(module_configs)
