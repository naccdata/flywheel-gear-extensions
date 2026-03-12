"""Classes for representing NACC studies (or, if you must, projects)."""

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Mapping, Optional, Self

from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from serialization.case import kebab_case

logger = logging.getLogger(__name__)


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


class DatatypeConfig(BaseModel):
    """Configuration for a single datatype within a study.

    This model pairs a datatype name with its mode (aggregation or distribution),
    enabling mixed-mode studies where different datatypes can have different modes.

    Attributes:
        name: The datatype name (e.g., "form", "dicom", "csv")
        mode: The mode for this datatype ("aggregation" or "distribution")
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )

    name: str
    mode: Literal["aggregation", "distribution"]


class DashboardConfig(BaseModel):
    """Configuration for a single dashboard within a study.

    This model pairs a dashboard name with its organizational level,
    enabling dashboards to be created at different levels (center or study).

    Attributes:
        name: The dashboard name
        level: The organizational level for this dashboard ("center" or "study")
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )

    name: str
    level: Literal["center", "study"] = "center"


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
    mode: Optional[Literal["aggregation", "distribution"]] = None
    datatypes: List[str] | List[DatatypeConfig]
    dashboards: Optional[List[str] | List[DashboardConfig]] = None
    pages: Optional[List[str]] = None
    study_type: Literal["primary", "affiliated"]
    legacy: bool = Field(True)
    published: bool = Field(False)
    funding_organization: Optional[str] = None

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

    def get_datatype_mode(
        self, datatype: str
    ) -> Literal["aggregation", "distribution"]:
        """Get the mode for a specific datatype.

        Args:
            datatype: The name of the datatype to look up

        Returns:
            The mode for the specified datatype

        Raises:
            ValueError: If the datatype is not found in the study configuration
        """
        configs = self.get_datatype_configs()
        for config in configs:
            if config.name == datatype:
                return config.mode
        raise ValueError(f"Datatype '{datatype}' not found in study configuration")

    def get_datatype_configs(self) -> List[DatatypeConfig]:
        """Get all datatype configurations.

        Returns:
            List of DatatypeConfig objects for all datatypes in the study
        """
        if not self.datatypes:
            return []

        # If datatypes is already a list of DatatypeConfig, return it
        if isinstance(self.datatypes[0], DatatypeConfig):
            return self.datatypes  # type: ignore

        # Otherwise, it's a list of strings (shouldn't happen after validation)
        # This is a fallback for type safety
        return []

    def get_datatypes_by_mode(
        self, mode: Literal["aggregation", "distribution"]
    ) -> List[str]:
        """Get list of datatypes with the specified mode.

        Args:
            mode: The mode to filter by ("aggregation" or "distribution")

        Returns:
            List of datatype names that have the specified mode
        """
        configs = self.get_datatype_configs()
        return [config.name for config in configs if config.mode == mode]

    def get_dashboard_level(self, dashboard: str) -> Literal["center", "study"]:
        """Get the level for a specific dashboard.

        Args:
            dashboard: The name of the dashboard to look up

        Returns:
            The level for the specified dashboard

        Raises:
            ValueError: If the dashboard is not found in the study configuration
        """
        configs = self.get_dashboard_configs()
        for config in configs:
            if config.name == dashboard:
                return config.level
        raise ValueError(f"Dashboard '{dashboard}' not found in study configuration")

    def get_dashboard_configs(self) -> List[DashboardConfig]:
        """Get all dashboard configurations.

        Returns:
            List of DashboardConfig objects for all dashboards in the study.
            Returns empty list if no dashboards are configured.
        """
        if not self.dashboards:
            return []

        # If dashboards is already a list of DashboardConfig, return it
        if isinstance(self.dashboards[0], DashboardConfig):
            return self.dashboards  # type: ignore

        # Otherwise, it's a list of strings (shouldn't happen after validation)
        # This is a fallback for type safety
        return []

    def get_dashboards_by_level(self, level: Literal["center", "study"]) -> List[str]:
        """Get list of dashboards with the specified level.

        Args:
            level: The level to filter by ("center" or "study")

        Returns:
            List of dashboard names that have the specified level
        """
        configs = self.get_dashboard_configs()
        return [config.name for config in configs if config.level == level]

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

    @field_validator("datatypes", mode="before")
    @classmethod
    def normalize_datatypes(
        cls, value: Any, info: ValidationInfo
    ) -> List[DatatypeConfig]:
        """Normalize datatypes to DatatypeConfig list.

        Handles:
        - List[str] with study-level mode (migrates to datatype-level)
        - List[DatatypeConfig]
        - Mixed formats

        Args:
            value: The datatypes value to normalize
            info: Validation context containing other field values

        Returns:
            List of DatatypeConfig objects

        Raises:
            ValueError: If mode values are invalid or study-level mode is missing
                       when using List[str] format
        """
        if not value:
            return []

        if not isinstance(value, list) or len(value) == 0:
            raise ValueError(f"Invalid datatypes format: {type(value)}")

        first_item = value[0]

        # If already DatatypeConfig objects, validate modes and return
        if isinstance(first_item, DatatypeConfig):
            return cls._validate_datatype_configs(value)

        # If dicts with 'name' and 'mode' keys, convert to DatatypeConfig
        if isinstance(first_item, dict) and "name" in first_item:
            return cls._convert_datatype_dicts(value)

        # If list of strings, migrate from study-level mode
        if isinstance(first_item, str):
            return cls._migrate_from_study_mode(value, info)

        raise ValueError(f"Invalid datatypes format: {type(value)}")

    @classmethod
    def _validate_datatype_configs(
        cls, configs: List[DatatypeConfig]
    ) -> List[DatatypeConfig]:
        """Validate that all datatype configs have valid modes."""
        for config in configs:
            if config.mode not in ["aggregation", "distribution"]:
                raise ValueError(
                    f"Invalid mode '{config.mode}' for datatype "
                    f"'{config.name}'. Mode must be 'aggregation' or "
                    "'distribution'"
                )
        return configs

    @classmethod
    def _convert_datatype_dicts(
        cls, items: List[Dict[str, Any]]
    ) -> List[DatatypeConfig]:
        """Convert list of dicts to DatatypeConfig objects."""
        configs = []
        for item in items:
            if "mode" not in item:
                raise ValueError(
                    f"Datatype configuration for "
                    f"'{item.get('name', 'unknown')}' is missing 'mode' field"
                )
            mode = item["mode"]
            if mode not in ["aggregation", "distribution"]:
                raise ValueError(
                    f"Invalid mode '{mode}' for datatype '{item['name']}'. "
                    "Mode must be 'aggregation' or 'distribution'"
                )
            configs.append(DatatypeConfig(name=item["name"], mode=mode))
        return configs

    @classmethod
    def _migrate_from_study_mode(
        cls, datatypes: List[str], info: ValidationInfo
    ) -> List[DatatypeConfig]:
        """Migrate from study-level mode to datatype-level modes.

        Note: This method looks for the mode field in the raw input data.
        Since datatypes is validated before mode in field order, we need to
        access the raw input data rather than validated data.
        """
        # Get mode from the raw input data (not yet validated)
        # info.data contains fields that have been validated so far
        # For fields that come after this one, we need to check the raw data
        study_mode = info.data.get("mode")

        if not study_mode:
            raise ValueError(
                "Datatypes specified as list of strings requires study-level "
                "'mode' field for migration. Please specify mode at datatype "
                "level or provide study-level mode."
            )

        if study_mode not in ["aggregation", "distribution"]:
            raise ValueError(
                f"Invalid study-level mode '{study_mode}'. "
                "Mode must be 'aggregation' or 'distribution'"
            )

        # Log deprecation warning
        logger.warning(
            "Using study-level 'mode' field is deprecated. "
            "Please migrate to datatype-level mode configuration. "
            f"Applying mode '{study_mode}' to all datatypes: {datatypes}"
        )

        return [DatatypeConfig(name=dt, mode=study_mode) for dt in datatypes]

    @field_validator("dashboards", mode="before")
    @classmethod
    def normalize_dashboards(
        cls, value: Any, info: ValidationInfo
    ) -> Optional[List[DashboardConfig]]:
        """Normalize dashboards to DashboardConfig list.

        Handles:
        - List[str] (defaults to level "center")
        - List[DashboardConfig]
        - Mixed formats
        - None

        Args:
            value: The dashboards value to normalize
            info: Validation context containing other field values

        Returns:
            List of DashboardConfig objects or None

        Raises:
            ValueError: If level values are invalid
        """
        if value is None:
            return None

        if not value:
            return []

        if not isinstance(value, list) or len(value) == 0:
            raise ValueError(f"Invalid dashboards format: {type(value)}")

        first_item = value[0]

        # If already DashboardConfig objects, validate levels and return
        if isinstance(first_item, DashboardConfig):
            return cls._validate_dashboard_configs(value)

        # If dicts with 'name' key, convert to DashboardConfig
        if isinstance(first_item, dict) and "name" in first_item:
            return cls._convert_dashboard_dicts(value)

        # If list of strings, default to level "center"
        if isinstance(first_item, str):
            return [DashboardConfig(name=db, level="center") for db in value]

        raise ValueError(f"Invalid dashboards format: {type(value)}")

    @classmethod
    def _validate_dashboard_configs(
        cls, configs: List[DashboardConfig]
    ) -> List[DashboardConfig]:
        """Validate that all dashboard configs have valid levels."""
        for config in configs:
            if config.level not in ["center", "study"]:
                raise ValueError(
                    f"Invalid level '{config.level}' for dashboard "
                    f"'{config.name}'. Level must be 'center' or 'study'"
                )
        return configs

    @classmethod
    def _convert_dashboard_dicts(
        cls, items: List[Dict[str, Any]]
    ) -> List[DashboardConfig]:
        """Convert list of dicts to DashboardConfig objects."""
        configs = []
        for item in items:
            level = item.get("level", "center")
            if level not in ["center", "study"]:
                raise ValueError(
                    f"Invalid level '{level}' for dashboard '{item['name']}'. "
                    "Level must be 'center' or 'study'"
                )
            configs.append(DashboardConfig(name=item["name"], level=level))
        return configs

    @model_validator(mode="after")
    def check_mode_consistency(self) -> Self:
        """Checks consistency within a study model.

        Note: This validator checks the deprecated study-level mode field for
        backward compatibility. The validate_configuration validator handles
        the new datatype-level mode validation.
        """
        # Only check if mode field is explicitly set (backward compatibility)
        if (
            self.mode is not None
            and self.study_type == "primary"
            and self.mode != "aggregation"
        ):
            raise ValueError("The mode of a primary study must be aggregation")

        return self

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Validate complete study configuration.

        Checks:
        - Primary studies have aggregation-only datatypes
        - All datatypes have mode configuration
        - All dashboard levels are valid

        Returns:
            Self for method chaining

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate primary studies have aggregation-only datatypes
        if self.study_type == "primary":
            datatype_configs = self.get_datatype_configs()
            for config in datatype_configs:
                if config.mode != "aggregation":
                    raise ValueError(
                        f"Primary study cannot have datatype '{config.name}' with mode "
                        f"'{config.mode}'. All datatypes in primary studies must have "
                        "mode 'aggregation'"
                    )

        # Validate all datatypes have mode configuration
        # This is already enforced by normalize_datatypes validator,
        # but we double-check here for completeness
        datatype_configs = self.get_datatype_configs()
        if not datatype_configs and self.datatypes:
            raise ValueError(
                "All datatypes must have mode configuration. "
                "Use datatype-level mode or provide study-level mode for migration."
            )

        # Validate all dashboard levels are valid
        # This is already enforced by normalize_dashboards validator,
        # but we verify here for completeness
        dashboard_configs = self.get_dashboard_configs()
        for dashboard_config in dashboard_configs:
            if dashboard_config.level not in ["center", "study"]:
                raise ValueError(
                    f"Invalid level '{dashboard_config.level}' for dashboard "
                    f"'{dashboard_config.name}'. Level must be 'center' or 'study'"
                )

        return self


class StudyError(Exception):
    """Exception for loading a study."""
