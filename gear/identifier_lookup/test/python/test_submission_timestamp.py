"""Tests for the submission timestamp in identifier-lookup QC status logs."""

import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from identifier_app.run import IdentifierLookupVisitor
from keys.keys import MetadataKeys

CREATED = datetime(2026, 10, 16, 10, 15, 30, tzinfo=timezone.utc)


def create_configs(errorlog_template: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "primary_key": "naccid",
        "accepted_modules": ["UDS"],
        "errorlog_template": errorlog_template,
        "module_configs": {
            "UDS": {
                "initial_packets": ["I"],
                "followup_packets": ["F"],
                "versions": ["4.0"],
                "date_field": "visitdate",
                "hierarchy_labels": {
                    "session": {
                        "template": "FORMS-VISIT-${visitnum}",
                        "transform": "upper",
                    },
                    "acquisition": {"template": "${module}", "transform": "upper"},
                    "filename": {
                        "template": "${subject}_${session}_${acquisition}",
                        "transform": "upper",
                    },
                },
                "required_fields": ["ptid", "adcid", "visitnum", "visitdate"],
            }
        },
    }


def run_gear(tmp_path: Path, errorlog_template: Dict[str, Any]):
    """Runs identifier-lookup with the given template and returns the
    QCStatusLogManager mock and gear context."""
    configs_path = tmp_path / "form-configs.json"
    configs_path.write_text(json.dumps(create_configs(errorlog_template)))
    input_path = tmp_path / "input-uds.csv"
    input_path.write_text("adcid,ptid\n")

    config_input = Mock()
    config_input.filepath = str(configs_path)

    file_entry = Mock()
    file_entry.info = {}
    file_entry.created = CREATED

    file_input = Mock()
    file_input.filename = "input-uds.csv"
    file_input.filepath = str(input_path)
    file_input.file_entry.return_value = file_entry
    file_input.get_module_name_from_file_suffix.return_value = "uds"

    project = Mock()
    project.get_pipeline_adcid.return_value = 1

    context = MagicMock()
    context.config.destination = {"type": "project"}

    visitor = IdentifierLookupVisitor(
        client=Mock(),
        admin_id="admin",
        file_input=file_input,
        identifiers_mode="dev",
        direction="nacc",
        gear_name="identifier-lookup",
        preserve_case=False,
        config_input=config_input,
    )

    with (
        patch("identifier_app.run.IdentifiersLambdaRepository"),
        patch("identifier_app.run.LambdaClient"),
        patch("identifier_app.run.create_lambda_client"),
        patch("identifier_app.run.ProjectAdaptor") as project_adaptor,
        patch("identifier_app.run.QCStatusLogManager") as log_manager,
        patch("identifier_app.run.run", return_value=True),
        patch("identifier_app.run.StringIO", return_value=StringIO("naccid\n")),
    ):
        project_adaptor.from_project.return_value = project
        visitor.run(context)

    return log_manager, context


@pytest.mark.parametrize("add_timestamp", [True, False])
def test_submission_timestamp(tmp_path: Path, add_timestamp: bool):
    log_manager, context = run_gear(
        tmp_path, {"suffix": "update-request", "add_timestamp": add_timestamp}
    )

    timestamp = log_manager.call_args.kwargs["timestamp"]
    output_infos = [
        call.kwargs["info"]
        for call in context.metadata.update_file_metadata.call_args_list
        if "info" in call.kwargs
    ]

    if add_timestamp:
        assert timestamp == CREATED
        assert output_infos == [
            {MetadataKeys.SUBMISSION_TIMESTAMP: "2026-10-16 10:15:30"}
        ]
        update_call = context.metadata.update_file_metadata.call_args
        assert update_call.args[0] == "input-uds_identifiers.csv"
    else:
        assert timestamp is None
        assert output_infos == []
