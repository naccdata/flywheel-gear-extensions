"""Tests for the form ingest configurations."""

from configs.ingest_configs import FormProjectConfigs

MODULE_CONFIGS = {
    "initial_packets": ["I"],
    "followup_packets": ["F"],
    "versions": ["4.0"],
    "date_field": "visitdate",
    "hierarchy_labels": {
        "session": {"template": "FORMS-VISIT-${visitnum}"},
        "acquisition": {"template": "${module}"},
        "filename": {"template": "${subject}_${session}_${acquisition}.json"},
    },
    "required_fields": ["ptid", "visitdate"],
}


def create_configs(**kwargs) -> FormProjectConfigs:
    return FormProjectConfigs.model_validate(
        {
            "primary_key": "naccid",
            "accepted_modules": ["UDS"],
            "module_configs": {"UDS": MODULE_CONFIGS},
            **kwargs,
        }
    )


class TestErrorLogTemplateConfigs:
    def test_default_errorlog_template(self):
        configs = create_configs()
        assert configs.errorlog_template.suffix == "qc-status"
        assert configs.errorlog_template.extension == "log"

    def test_configured_errorlog_template(self):
        configs = create_configs(
            errorlog_template={"suffix": "update-request", "extension": "txt"}
        )
        assert configs.errorlog_template.suffix == "update-request"
        assert configs.errorlog_template.extension == "txt"

    def test_partial_errorlog_template(self):
        configs = create_configs(errorlog_template={"suffix": "update-request"})
        assert configs.errorlog_template.suffix == "update-request"
        assert configs.errorlog_template.extension == "log"

    def test_add_timestamp_default(self):
        assert not create_configs().errorlog_template.add_timestamp

    def test_add_timestamp_configured(self):
        configs = create_configs(
            errorlog_template={"suffix": "update-request", "add_timestamp": True}
        )
        assert configs.errorlog_template.add_timestamp

    def test_module_level_errorlog_template_ignored(self):
        module_configs = {
            **MODULE_CONFIGS,
            "errorlog_template": {
                "id_field": "ptid",
                "date_field": "visitdate",
                "suffix": "module-suffix",
                "extension": "log",
            },
        }
        configs = FormProjectConfigs.model_validate(
            {
                "primary_key": "naccid",
                "accepted_modules": ["UDS"],
                "module_configs": {"UDS": module_configs},
            }
        )
        assert configs.errorlog_template.suffix == "qc-status"
        assert not hasattr(configs.module_configs["UDS"], "errorlog_template")
