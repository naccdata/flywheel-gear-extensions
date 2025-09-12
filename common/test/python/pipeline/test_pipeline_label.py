from pydantic import ValidationError
import pytest
from pipeline.pipeline_label import PipelineLabel


class TestPipelineLabel:
    def test_valid(self):
        label_object = PipelineLabel(
            pipeline="distribution", datatype="genetic-availability", study_id="dummy"
        )
        label_string = label_object.model_dump()
        assert label_string == "distribution-genetic-availability-dummy"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(
            pipeline="distribution", datatype="genetic-availability"
        )
        label_string = label_object.model_dump()
        assert label_string == "distribution-genetic-availability"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(
            pipeline="distribution", datatype="form", study_id="dummy"
        )
        label_string = label_object.model_dump()
        assert label_string == "distribution-form-dummy"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(pipeline="distribution", datatype="form")
        label_string = label_object.model_dump()
        assert label_string == "distribution-form"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(pipeline="accepted", study_id="dummy")
        label_string = label_object.model_dump()
        assert label_string == "accepted-dummy"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(pipeline="accepted")
        label_string = label_object.model_dump()
        assert label_string == "accepted"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

    def test_non_pipeline(self):
        label_string = "center-portal"
        with pytest.raises(ValidationError):
            PipelineLabel.model_validate(label_string)

        label_string = "metadata"
        with pytest.raises(ValidationError):
            PipelineLabel.model_validate(label_string)
