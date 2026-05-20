"""Resource hierarchy seeder for the Authorization Service.

Seeds parent relationships for resources created by the
project_management gear, enabling inherited permissions via OpenFGA
computed relations.
"""

import logging

from authorization.client import AuthorizationClient
from authorization.exceptions import AuthorizationClientError
from authorization.models import ParentRelationshipModel

log = logging.getLogger(__name__)


class ResourceHierarchySeeder:
    """Seeds resource parent relationships in the Authorization Service.

    Calls set_resource_parents for each resource the gear creates or
    visits, establishing the hierarchy that enables inherited
    permissions.
    """

    def __init__(self, client: AuthorizationClient) -> None:
        """Initialize with an authorization client.

        Args:
            client: The authorization client for API calls.
        """
        self._client = client
        self._failure_count = 0

    @property
    def failure_count(self) -> int:
        """Number of set_parents calls that failed during this run."""
        return self._failure_count

    def seed_center_pipeline(
        self,
        resource_id: str,
        study_id: str,
        center_id: str,
    ) -> None:
        """Set parents for a center-scoped data pipeline.

        Args:
            resource_id: The pipeline resource ID (Flywheel project label).
            study_id: The study identifier.
            center_id: The research center identifier.
        """
        parents = _center_scoped_parents(study_id=study_id, center_id=center_id)
        self._set_parents(
            resource_type="data_pipeline",
            resource_id=resource_id,
            parents=parents,
        )

    def seed_center_dashboard(
        self,
        resource_id: str,
        study_id: str,
        center_id: str,
    ) -> None:
        """Set parents for a center-scoped dashboard.

        Args:
            resource_id: The dashboard resource ID.
            study_id: The study identifier.
            center_id: The research center identifier.
        """
        parents = _center_scoped_parents(study_id=study_id, center_id=center_id)
        self._set_parents(
            resource_type="dashboard",
            resource_id=resource_id,
            parents=parents,
        )

    def seed_center_page(
        self,
        resource_id: str,
        study_id: str,
        center_id: str,
    ) -> None:
        """Set parents for a center-scoped page.

        Args:
            resource_id: The page resource ID.
            study_id: The study identifier.
            center_id: The research center identifier.
        """
        parents = _center_scoped_parents(study_id=study_id, center_id=center_id)
        self._set_parents(
            resource_type="page",
            resource_id=resource_id,
            parents=parents,
        )

    def seed_study_dashboard(
        self,
        resource_id: str,
        study_id: str,
    ) -> None:
        """Set parents for a study-scoped dashboard.

        Args:
            resource_id: The dashboard resource ID.
            study_id: The study identifier.
        """
        parents = _study_scoped_parents(study_id=study_id)
        self._set_parents(
            resource_type="dashboard",
            resource_id=resource_id,
            parents=parents,
        )

    def seed_study_page(
        self,
        resource_id: str,
        study_id: str,
    ) -> None:
        """Set parents for a study-scoped page.

        Args:
            resource_id: The page resource ID.
            study_id: The study identifier.
        """
        parents = _study_scoped_parents(study_id=study_id)
        self._set_parents(
            resource_type="page",
            resource_id=resource_id,
            parents=parents,
        )

    def seed_community_page(
        self,
        resource_id: str,
    ) -> None:
        """Set parents for a community-scoped page.

        Args:
            resource_id: The page resource ID.
        """
        parents = _community_scoped_parents()
        self._set_parents(
            resource_type="page",
            resource_id=resource_id,
            parents=parents,
        )

    def _set_parents(
        self,
        resource_type: str,
        resource_id: str,
        parents: list[ParentRelationshipModel],
    ) -> None:
        """Call set_resource_parents with error handling.

        Args:
            resource_type: The type of resource.
            resource_id: The resource identifier.
            parents: List of parent relationships to set.
        """
        try:
            self._client.set_resource_parents(
                resource_type=resource_type,
                resource_id=resource_id,
                parents=parents,
            )
            log.debug(
                "Set parents for %s/%s: %s",
                resource_type,
                resource_id,
                [(p.structural_relation, p.parent_type, p.parent_id) for p in parents],
            )
        except AuthorizationClientError as error:
            self._failure_count += 1
            log.error(
                "Failed to set parents for %s/%s: %s",
                resource_type,
                resource_id,
                error,
            )


def _center_scoped_parents(
    study_id: str,
    center_id: str,
) -> list[ParentRelationshipModel]:
    """Build parent relationships for a center-scoped resource.

    Args:
        study_id: The study identifier.
        center_id: The research center identifier.

    Returns:
        List with parent_study and parent_center relationships.
    """
    return [
        ParentRelationshipModel(
            structural_relation="parent_study",
            parent_type="study",
            parent_id=study_id,
        ),
        ParentRelationshipModel(
            structural_relation="parent_center",
            parent_type="research_center",
            parent_id=center_id,
        ),
    ]


def _study_scoped_parents(
    study_id: str,
) -> list[ParentRelationshipModel]:
    """Build parent relationships for a study-scoped resource.

    Args:
        study_id: The study identifier.

    Returns:
        List with parent_study relationship only.
    """
    return [
        ParentRelationshipModel(
            structural_relation="parent_study",
            parent_type="study",
            parent_id=study_id,
        ),
    ]


def _community_scoped_parents() -> list[ParentRelationshipModel]:
    """Build parent relationships for a community-scoped resource.

    Returns:
        List with parent_community relationship (parent_id "nacc").
    """
    return [
        ParentRelationshipModel(
            structural_relation="parent_community",
            parent_type="community",
            parent_id="nacc",
        ),
    ]
