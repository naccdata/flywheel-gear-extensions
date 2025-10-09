"""Defines a data model for pipeline project labels."""

from typing import Any, Optional, Self, get_args

from keys.types import DatatypeNameType, PipelineStageType
from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    model_serializer,
    model_validator,
)


class PipelineLabel(BaseModel):
    """Data model to a project label in terms of a pipeline stage, datatype and
    study ID.

    Serialization uses a string representation
    """

    model_config = ConfigDict(frozen=True)

    pipeline: PipelineStageType
    datatype: Optional[DatatypeNameType] = None
    study_id: str = "adrc"

    @model_serializer
    def string_pipeline_label(self) -> str:
        """"""
        result = f"{self.pipeline}"
        result = f"{result}-{self.datatype}" if self.datatype else result
        result = f"{result}-{self.study_id}" if self.study_id != "adrc" else result
        return result

    @model_validator(mode="wrap")
    @classmethod
    def string_validator(
        cls, label: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        if isinstance(label, PipelineLabel):
            return handler(label)
        if isinstance(label, dict):
            return handler(label)
        if not isinstance(label, str):
            raise TypeError(f"Unexpected type for pipeline label: {type(label)}")

        tokens = label.split("-")
        if not tokens:
            raise TypeError("Empty pipeline label")

        study_id = "adrc"
        datatype = None
        pipeline = tokens[0]

        if len(tokens) > 1:
            datatype = "-".join(tokens[1:])
            if datatype not in get_args(DatatypeNameType):
                datatype = "-".join(tokens[1:-1])
                study_id = tokens[-1:][0]

        datatype = datatype if datatype else None
        return handler(
            {"pipeline": pipeline, "datatype": datatype, "study_id": study_id}
        )
