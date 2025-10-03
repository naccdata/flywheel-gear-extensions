"""Defines components related to user authorizations."""

import logging
from typing import Any, Literal, Self, get_args

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


class Activity(BaseModel):
    """Data model representing an user activity for authorization.

    Consists of an action and datatype.
    """

    model_config = ConfigDict(frozen=True)

    datatype: DatatypeNameType
    action: ActionType

    def __str__(self) -> str:
        return f"{self.action}-{self.datatype}"

    @model_serializer
    def string_activity(self) -> str:
        """Serializes this activity as a string of the form action-datatype.

        Returns:
          string representation of activity
        """
        return f"{self.action}-{self.datatype}"

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

        datatype = ""
        action_string = ""
        tokens = activity.split("-")
        for index, token in enumerate(tokens):
            action_string = f"{action_string}-{token}" if action_string else token
            if action_string in get_args(ActionType):
                datatype = "-".join(tokens[index + 1 :])
                break

        return handler({"datatype": datatype, "action": action_string})


class StudyAuthorizations(BaseModel):
    """Type class for authorizations."""

    study_id: str
    activities: dict[DatatypeNameType, Activity] = {}

    def add(self, datatype: DatatypeNameType, action: ActionType) -> None:
        """Adds an activity with the datatype and action to the authorizations.

        Args:
          datatype: the datatype
          action: the action
        """
        self.activities[datatype] = Activity(datatype=datatype, action=action)

    def __contains__(self, activity_name: str) -> bool:
        try:
            input_activity = Activity.model_validate(activity_name)
        except ValidationError:
            # TODO: needs to raise error
            return False

        activity = self.activities.get(input_activity.datatype)
        if activity is None:
            return False

        return input_activity.action == activity.action


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
