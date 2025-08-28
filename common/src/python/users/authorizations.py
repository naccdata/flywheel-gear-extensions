"""Defines components related to user authorizations."""

from typing import Dict, List, Literal, Optional, Sequence, Set

from pydantic import BaseModel

DatatypeNameType = Literal["form", "dicom", "enrollment"]
AuthNameType = Literal[
    "submit-form",
    "submit-dicom",
    "submit-enrollment",
    "audit-data",
    "approve-data",
    "view-reports",
]


class Authorizations(BaseModel):
    """Type class for authorizations."""

    study_id: str
    submit: List[DatatypeNameType]
    audit_data: bool
    approve_data: bool
    view_reports: bool
    _activities: Optional[List[AuthNameType]] = None

    def get_activities(self) -> List[AuthNameType]:
        """Returns the list of names of authorized activities.

        Returns:
          The list of names of authorized activities
        """
        if self._activities:
            return self._activities

        activities: List[AuthNameType] = []
        if self.submit:
            for datatype in self.submit:
                activities.append(f"submit-{datatype}")  # type: ignore
        if self.audit_data:
            activities.append("audit-data")
        if self.approve_data:
            activities.append("approve-data")
        if self.view_reports:
            activities.append("view-reports")

        self._activities = activities
        return self._activities

    @classmethod
    def create_from_record(
        cls, *, study_id: str, activities: Sequence[str]
    ) -> "Authorizations":
        """Creates an Authorizations object directory access activities.

        Activities from the NACC directory are represented as a string
        consisting of a comma-separated list of letters.

        The letters represent the following activities:
        - a: submit form data
        - b: submit image data
        - c: audit data
        - d: approve data
        - e: view reports

        Args:
          study_id: the study ID for scope of authorizations
          activities: a string containing activities
        Returns:
          The Authorizations object
        """
        modalities: List[DatatypeNameType] = []
        if "a" in activities:
            modalities.append("form")
            modalities.append("enrollment")
        if "b" in activities:
            modalities.append("dicom")

        return Authorizations(
            study_id=study_id,
            submit=modalities,
            audit_data=bool("c" in activities),
            approve_data=("d" in activities),
            view_reports=("e" in activities),
        )


class AuthMap(BaseModel):
    """Type class for mapping authorizations to roles.

    Represents table as project label -> activity -> role.
    """

    project_authorizations: Dict[str, Dict[str, str]]

    def get(self, *, project_label: str, authorizations: Authorizations) -> Set[str]:
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
        for activity in authorizations.get_activities():
            role_name = activity_map.get(activity)
            if role_name:
                roles.add(role_name)

        return roles
