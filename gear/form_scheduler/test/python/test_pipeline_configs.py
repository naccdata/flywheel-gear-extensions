"""Tests the PipelineConfigs and PipelineQueue pydantic classes."""

from pathlib import Path
from typing import Any, Dict

from configs.ingest_configs import PipelineConfigs
from form_scheduler_app.form_scheduler_queue import PipelineQueue
from form_scheduler_app.run import load_form_pipeline_configurations
from pydantic import ValidationError

TEST_FILES_DIR = Path(__file__).parent.resolve() / 'data'


class TestPipelineConfigs:
    """Tests the PipelineConfigs and PipelineQueue pydantic classes."""

    def test_invalid_config(self):
        """Test an invalid configurations file."""

        # assert that config with invalid input raises ValidationError
        try:
            load_form_pipeline_configurations(
                str(TEST_FILES_DIR / 'invalid-pipeline-configs.json'))
        except ValidationError as error:
            assert str(error).find('validation error') != -1

    def test_valid_config(self):
        """Test a valid configurations file."""

        # assert Pipeline with no inputs and empty gear configs
        assert load_form_pipeline_configurations(
            str(TEST_FILES_DIR /
                'valid-pipeline-with-empty-configs.json')) is not None

        # assert PipelineConfigs
        pipeline_configs: PipelineConfigs = load_form_pipeline_configurations(
            str(TEST_FILES_DIR / 'valid-pipeline-configs.json'))

        assert pipeline_configs is not None

        configs: Dict[str, Any] = {
            "gears": ["gear_one", "gear_two"],
            "pipelines": [{
                "name": "submission",
                "modules": ["module1", "module2", "module3"],
                "tags": ["submission-tag"],
                "extensions": [".csv"],
                "starting_gear": {
                    "gear_name":
                    "gear_one",
                    "inputs": [{
                        "label": "input_file1",
                        "file_locator": "matched",
                        "file_name": None
                    }, {
                        "label": "input_file2",
                        "file_locator": "module",
                        "file_name": "${module}-schema.json"
                    }],
                    "configs": {
                        "config1": "value1",
                        "config2": 10
                    }
                },
                "notify_user": True
            }]
        }

        assert pipeline_configs.model_dump() == configs

        pipeline_queue = PipelineQueue.create_from_pipeline(
            pipeline_configs.pipelines[0])

        assert pipeline_queue is not None

        pipeline = {
            "index": -1,
            "name": "submission",
            "modules": ["module1", "module2", "module3"],
            "tags": ["submission-tag"],
            "subqueues": {
                "module1": [],
                "module2": [],
                "module3": []
            }
        }
        assert pipeline_queue.model_dump() == pipeline
