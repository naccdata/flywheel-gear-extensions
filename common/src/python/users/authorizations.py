"""Defines components related to user authorizations."""

from typing import Dict, Literal, Set

from keys.types import DatatypeNameType
from pydantic import BaseModel, model_serializer

ActionType = Literal["submit-audit", "view"]


class Activity(BaseModel):
    data: DatatypeNameType
    action: ActionType

    @model_serializer
    def string_activity(self) -> str:
        return f"{self.action}-{self.data}"


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
        self.activities[datatype] = Activity(data=datatype, action=action)


class AuthMap(BaseModel):
    """Type class for mapping authorizations to roles.

    Represents table as project label -> activity -> role.
    """

    project_authorizations: Dict[str, Dict[str, str]]

    def get(
        self, *, project_label: str, authorizations: StudyAuthorizations
    ) -> Set[str]:
        """Gets the roles for a project and authorizations.

        Matches project label against the authorization keys.
        If the label has a study suffix, e.g. "ingest-form-dvcid", will first
        check the full label, and if that fails will remove the suffix and
        retry (e.g., "ingest-form").

        Args:
            project_id: the project ID
            authorizations: the authorizations
        Returns:
            The list of roles
        """
        roles: Set[str] = set()

        pipeline_label = project_label
        if pipeline_label not in self.project_authorizations:
            # remove the suffix in case it is a study ID
            pipeline_label = "-".join(project_label.split("-")[:-1])

        if pipeline_label not in self.project_authorizations:
            return roles

        activity_map = self.project_authorizations.get(pipeline_label, {})
        for activity in authorizations.activities:
            role_name = activity_map.get(activity)
            if role_name:
                roles.add(role_name)

        return roles
