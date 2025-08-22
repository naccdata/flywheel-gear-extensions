"""Defines components related to user authorizations."""

from typing import Dict, Literal, Sequence, Set

from keys.types import DatatypeNameType
from pydantic import BaseModel

ActivityPrefixType = Literal["submit-audit", "view"]


def convert_to_activity(
    activity_prefix: ActivityPrefixType, datatype: DatatypeNameType
) -> str:
    """Converts the datatype to a authorization activity by adding the prefix.

    Args:
      activity_prefix: the prefix to add
      datatype: the datatype
    """
    return f"{activity_prefix}-{datatype}"


def convert_to_activities(
    activity_prefix: ActivityPrefixType, datatypes: Sequence[DatatypeNameType]
) -> list[str]:
    """Creates a list of activities from the list of datatypes using the
    activity name prefix.

    Args:
      activity_prefix: the activity name prefix
      datatypes: a sequence of datatype names
    """
    return [convert_to_activity(activity_prefix, datatype) for datatype in datatypes]


class StudyAuthorizations(BaseModel):
    """Type class for authorizations."""

    study_id: str
    activities: list[str]


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

        activity_map = self.project_authorizations[pipeline_label]
        for activity in authorizations.activities:
            role_name = activity_map.get(activity)
            if role_name:
                roles.add(role_name)

        return roles
