"""Classes for representing NACC studies (or, if you must, projects)."""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Mapping, Optional, Self

from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from serialization.case import kebab_case


def convert_to_slug(name: str) -> str:
    """Converts center name to a slug for use as a human-readable ID.

    Removes non-word, non-whitespace characters, replaces runs of
    whitespace with a single hyphen, and returns in lower case.

    Args:
      name: the name of the center

    Returns:
      The transformed name.
    """
    name = re.sub(r"[/]", " ", name)
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", "-", name)
    return name.lower()


class StudyCenterModel(BaseModel):
    """Data model to represent study enrollment pattern."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )

    center_id: str
    pipeline_adcid: Optional[int] = None
    enrollment_pattern: Literal["co-enrollment", "separate"] = "co-enrollment"

    @model_validator(mode="after")
    def validate_enrollment(self) -> Self:
        """Ensures that the enrollment pattern and."""
        if self.enrollment_pattern == "separate" and self.pipeline_adcid is None:
            raise ValueError(
                f"Center {self.center_id} has separate enrollment without a "
                "pipeline ADCID"
            )

        return self


class StudyVisitor(ABC):
    """Abstract class for a visitor object for studies."""

    @abstractmethod
    def visit_study(self, study: "StudyModel") -> None:
        """Method to visit the given study.

        Args:
          study: the study to visit.
        """

    @abstractmethod
    def visit_center(self, center: StudyCenterModel) -> None:
        """Method to visit the given center within a study.

        Args:
          center_id: the ID of the center to visit
        """

    @abstractmethod
    def visit_datatype(self, datatype: str):
        """Method to visit the given datatype within a study.

        Args:
          datatype: the name of the datatype within a study.
        """


StudyMode = Literal["aggregation", "distribution"]
StudyType = Literal["primary", "affiliated"]


class StudyModel(BaseModel):
    """Data model for studies based on the model used in the project-management
    gear.

    The `mode` indicates whether the study is meant to aggregate or distribute data
    relative to the centers:
    * 'aggregation' should be used when data is gathered from the centers and
      aggregated.
    * 'distribution' should be used when data is distributed to the centers.

    The `study_type` indicates whether the study is 'primary' or 'affiliated'.
    Affiliated study participants may be co-enrolled in the primary study or
    separately enrolled.
    So, for an affiliated study the enrollment pattern of a center determines
    how data is managed:
    * for a co-enrollment pattern, participant data will be associated to the
      primary study.
    * for separate enrollment, participant data will be associated with the
      affiliated study.
    For the primary study, the center enrollment pattern is meaningless.

    A study with data from the legacy system, should have legacy set to True.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )

    name: str = Field(alias="study")
    study_id: str
    centers: List[StudyCenterModel]
    datatypes: List[str]
    dashboards: Optional[List[str]] = None
    mode: Literal["aggregation", "distribution"]
    study_type: Literal["primary", "affiliated"]
    legacy: bool = Field(True)
    published: bool = Field(False)

    def apply(self, visitor: StudyVisitor) -> None:
        """Apply visitor to this Study."""
        visitor.visit_study(self)

    def is_published(self) -> bool:
        """Study published predicate."""
        return self.published

    def is_primary(self) -> bool:
        """Predicate to indicate whether is the main study of coordinating
        center."""
        return self.study_type == "primary"

    def has_legacy(self) -> bool:
        """Predicate to indicate whether the study has legacy data."""
        return self.legacy

    def project_suffix(self) -> str:
        """Creates the suffix that should be added to study pipelines."""
        if self.is_primary():
            return ""

        return f"-{self.study_id}"

    @classmethod
    def create(cls, study: Mapping[str, Any]) -> "StudyModel":
        try:
            return StudyModel.model_validate(study)
        except ValidationError as error:
            raise StudyError(error) from error

    @field_validator("centers", mode="before")
    @classmethod
    def center_list(cls, centers: List[str | Dict[str, str]]) -> List[StudyCenterModel]:
        """Allows validation of an object where centers are given as strings.

        Converts center-ids to CenterStudyModel with co-enrollment enrollment pattern.

        Args:
          centers: list of string or CenterStudyModel
        Returns:
          List with center-ids converted to CenterStudyModel
        """

        def center_model(
            value: str | Dict[str, str] | StudyCenterModel,
        ) -> StudyCenterModel:
            """Converts value to a CenterStudyModel if required.

            Creates a CenterStudyModel from a center-id by adding the
            co-enrollment enrollment pattern.

            Args:
              value: the center-id or a CenterStudyModel
            Returns:
              the CenterStudyModel for the value
            """
            if isinstance(value, StudyCenterModel):
                return value
            if isinstance(value, Dict):
                return StudyCenterModel.model_validate(value)
            return StudyCenterModel(center_id=value, enrollment_pattern="co-enrollment")

        return [center_model(value) for value in centers]

    @model_validator(mode="after")
    def check_mode_consistency(self) -> Self:
        """Checks consistency within a study model."""
        if self.study_type == "primary" and self.mode != "aggregation":
            raise ValueError("The mode of a primary study must be aggregation")

        return self


class StudyError(Exception):
    """Exception for loading a study."""
