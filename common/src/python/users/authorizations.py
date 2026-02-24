"""Defines components related to user authorizations."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal, Self, Union, get_args

from flywheel.models.role_output import RoleOutput
from keys.types import DatatypeNameType
from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    ValidationError,
    ValidationInfo,
    model_serializer,
    model_validator,
)

log = logging.getLogger(__name__)

ActionType = Literal["submit-audit", "view"]


class Resource(ABC, BaseModel):
    """Abstract base class for authorization resources.

    Resources represent the target of an authorization activity. They can be
    datatypes (e.g., form, enrollment) or dashboards (e.g., reports).

    Resources are frozen (immutable) and hashable, allowing them to be used as
    dictionary keys in authorization mappings.

    String representation follows the pattern: "{prefix}-{name}"
    Examples: "datatype-form", "dashboard-reports"

    Subclasses must implement:
        - name: property returning the resource identifier
        - prefix(): class method returning the resource type prefix
        - field_name(): class method returning the field name for validation
    """

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        """Return string representation in format: {prefix}-{name}."""
        return f"{self.prefix()}-{self.name}"

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the resource identifier (e.g., 'form', 'reports')."""
        pass

    @classmethod
    @abstractmethod
    def prefix(cls) -> str:
        """Return the string prefix for this resource type.

        Examples: 'datatype', 'dashboard'
        """
        pass

    @classmethod
    @abstractmethod
    def field_name(cls) -> str:
        """Return the field name for the resource value.

        Used during validation to construct the appropriate field dictionary.
        Examples: 'datatype', 'dashboard'
        """
        pass

    @classmethod
    def _try_subclasses(cls, value: Any, value_type: str) -> Self:
        """Try to validate value with each Resource subclass.

        Iterates through all Resource subclasses and attempts validation with each.
        Returns the first successful validation result.

        Args:
            value: The value to validate (string or dict)
            value_type: Description of value type for error message ("string" or "dict")

        Returns:
            Validated Resource instance from successful subclass

        Raises:
            ValueError: If no subclass can validate the value
        """
        errors = []
        for resource_cls in cls.__subclasses__():
            try:
                return resource_cls.model_validate(value)
            except ValidationError as e:
                errors.append(f"{resource_cls.__name__}: {e!s}")
                continue

        raise ValueError(
            f"Could not parse resource {value_type} '{value}'. "
            f"Tried: {', '.join(errors)}"
        )

    @model_validator(mode="wrap")
    @classmethod
    def string_validator(
        cls, value: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        """Validate Resource from string, dict, or Resource instance.

        Supports multiple input formats:
        - Resource instance: pass through
        - Dict: validate normally or try all subclasses for base Resource
        - String: parse prefixed format (e.g., "datatype-form" -> DatatypeResource)

        For string inputs to subclasses, expects format: "{prefix}-{value}"
        For string inputs to base Resource, tries all subclasses.

        Args:
            value: Input value to validate
            handler: Pydantic validation handler

        Returns:
            Validated Resource instance

        Raises:
            ValueError: If string format is invalid or no subclass matches
            TypeError: If value type is unexpected
        """
        if isinstance(value, cls):
            return handler(value)

        if isinstance(value, dict):
            # For base Resource class with dict input, try each subclass
            if cls is Resource:
                return cls._try_subclasses(value, "dict")
            # For subclasses with dict, pass through to normal validation
            return handler(value)

        if not isinstance(value, str):
            return handler(value)

        # For base Resource class with string, try all subclasses
        if cls is Resource:
            return cls._try_subclasses(value, "string")

        # For subclasses, parse the prefixed string
        expected_prefix = f"{cls.prefix()}-"
        if value.startswith(expected_prefix):
            field_value = value[len(expected_prefix) :]
            return handler({cls.field_name(): field_value})

        # No prefix match, pass through (will likely fail validation)
        return handler(value)


class DatatypeResource(Resource):
    """Resource representing a data type (e.g., form, enrollment, scan-analysis).

    Used for authorization activities related to data processing pipelines.

    String format: "datatype-{datatype}"
    Examples: "datatype-form", "datatype-enrollment", "datatype-scan-analysis"

    Attributes:
        datatype: The data type identifier (validated against DatatypeNameType)
    """

    datatype: DatatypeNameType

    @property
    def name(self) -> str:
        """Return the datatype identifier."""
        return self.datatype

    @classmethod
    def prefix(cls) -> str:
        """Return 'datatype' as the prefix for this resource type."""
        return "datatype"

    @classmethod
    def field_name(cls) -> str:
        """Return 'datatype' as the field name for validation."""
        return "datatype"


class DashboardResource(Resource):
    """Resource representing a dashboard (e.g., reports, analytics).

    Used for authorization activities related to dashboard access and viewing.

    String format: "dashboard-{dashboard}"
    Examples: "dashboard-reports", "dashboard-analytics"

    Attributes:
        dashboard: The dashboard identifier (any string)
    """

    dashboard: str

    @property
    def name(self) -> str:
        """Return the dashboard identifier."""
        return self.dashboard

    @classmethod
    def prefix(cls) -> str:
        """Return 'dashboard' as the prefix for this resource type."""
        return "dashboard"

    @classmethod
    def field_name(cls) -> str:
        """Return 'dashboard' as the field name for validation."""
        return "dashboard"


class Activity(BaseModel):
    """Data model representing an user activity for authorization.

    Consists of an action and datatype.
    """

    model_config = ConfigDict(frozen=True)

    resource: Resource
    action: ActionType

    def __str__(self) -> str:
        return f"{self.action}-{self.resource}"

    @model_serializer
    def string_activity(self) -> str:
        """Serializes this activity as a string of the form action-datatype.

        Returns:
          string representation of activity
        """
        return f"{self.action}-{self.resource}"

    @model_validator(mode="wrap")
    @classmethod
    def string_validator(
        cls, activity: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        if isinstance(activity, Activity):
            return handler(activity)
        if isinstance(activity, dict):
            return handler(activity)
        if not isinstance(activity, str):
            raise TypeError(f"Unexpected type for activity: {type(activity)}")

        resource_string = ""
        action_string = ""
        tokens = activity.split("-")
        for index, token in enumerate(tokens):
            action_string = f"{action_string}-{token}" if action_string else token
            if action_string in get_args(ActionType):
                resource_string = "-".join(tokens[index + 1 :])
                break

        if not action_string:
            raise ValueError(f"No valid action found in: {activity}")
        if not resource_string:
            raise ValueError(f"No resource found in: {activity}")

        resource = Resource.model_validate(resource_string)

        return handler({"resource": resource, "action": action_string})


class StudyAuthorizations(BaseModel):
    """Type class for authorizations."""

    study_id: str
    activities: dict[Resource, Activity] = {}

    def __str__(self) -> str:
        activity_str = ",".join(
            [str(activity) for activity in self.activities.values()]
        )
        return f"study_id='{self.study_id}' activities=[{activity_str}]"

    def add(self, datatype: DatatypeNameType, action: ActionType) -> None:
        """Adds an activity with the datatype and action to the authorizations.

        Args:
          datatype: the datatype
          action: the action
        """
        resource = DatatypeResource(datatype=datatype)
        self.activities[resource] = Activity(resource=resource, action=action)

    def __contains__(self, activity: Union[str, Activity]) -> bool:
        try:
            input_activity = (
                Activity.model_validate(activity)
                if isinstance(activity, str)
                else activity
            )
        except ValidationError:
            # TODO: needs to raise error
            return False

        datatype_activity = self.activities.get(input_activity.resource)
        if datatype_activity is None:
            return False

        return input_activity.action == datatype_activity.action


class AuthMap(BaseModel):
    """Type class for mapping authorizations to roles.

    Represents table as project label -> activity -> role.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_authorizations: dict[str, dict[Activity, list[RoleOutput]]]
    read_only_role: RoleOutput

    def __get_roles(
        self, label: str, authorizations: StudyAuthorizations
    ) -> list[RoleOutput]:
        role_map: dict[str, RoleOutput] = {}
        activity_map = self.project_authorizations.get(label, {})
        for activity in authorizations.activities.values():
            role_list = activity_map.get(activity, [])
            for role in role_list:
                role_map[role.label] = role
        return list(role_map.values())

    def get(
        self, *, project_label: str, authorizations: StudyAuthorizations
    ) -> list[RoleOutput]:
        """Gets the roles for a project and authorizations.

        Matches project label against the project keys of this map.
        If the label is either "center-portal" or "metadata", looks up roles.
        Otherwise, assumes a pipeline project where label may have a study
        suffix, e.g. "ingest-form-dvcid".
        So, first checks the full label, and if that fails, removes the suffix and
        retries (e.g., "ingest-form").
        This allows the authorization data to have study-specific role mappings.

        Args:
            project_id: the project ID
            authorizations: the authorizations
        Returns:
            The list of roles
        """
        if project_label in {"center-portal", "metadata"}:
            return self.__get_roles(label=project_label, authorizations=authorizations)

        pipeline_label = project_label
        if pipeline_label not in self.project_authorizations:
            # remove the suffix in case it is a study ID
            pipeline_label = "-".join(project_label.split("-")[:-1])

        if pipeline_label not in self.project_authorizations:
            return []

        return self.__get_roles(label=pipeline_label, authorizations=authorizations)

    @model_validator(mode="wrap")
    @classmethod
    def create_auth_map(
        cls,
        auth_object: Any,
        handler: ModelWrapValidatorHandler[Self],
        info: ValidationInfo,
    ) -> Self:
        """Creates an AuthMap object for the input auth map object where roles
        are represented as strings.

        Note: does not require that auth_object has the "project_authorizations"
        key, which simplifies loading the config file.

        Args:
          auth_object: the authorization map as a dictionary of strings
          role_map: the map of role name to role
        Raises:
          TypeError if the auth_object is not structured correctly
          ValidationError if activity names do not parse as Activity objects
        """
        if isinstance(auth_object, AuthMap):
            return handler(auth_object)
        if not isinstance(auth_object, dict):
            raise TypeError("expected dictionary for authmap")

        if not isinstance(info.context, dict):
            raise TypeError("role map is required")
        role_map = info.context.get("role_map", {})

        project_auth = auth_object.get("project_authorizations")
        project_auth = project_auth if project_auth else auth_object
        if not isinstance(project_auth, dict):
            raise TypeError('Expecting "project_authorizations" to be a dict')

        auth_dict = {}
        for project_label, role_assignment in project_auth.items():
            if not isinstance(role_assignment, dict):
                raise TypeError(
                    f"Expecting role assignment for project {project_label}"
                )

            project_dict = {}
            for activity_name, role_name_list in role_assignment.items():
                activity = Activity.model_validate(activity_name)
                role_list = []
                for role_name in role_name_list:
                    role = role_map.get(role_name)
                    if not role:
                        raise TypeError(
                            "No matching role for "
                            f"{project_label}:{activity_name}:{role_name}"
                        )
                    role_list.append(role)
                project_dict[activity] = role_list

            auth_dict[project_label] = project_dict

        read_only_role = role_map.get("read-only")
        assert read_only_role

        return handler(
            {"project_authorizations": auth_dict, "read_only_role": read_only_role}
        )
