import logging
from typing import Mapping, Optional

from centers.center_group import (
    AbstractCenterMetadataVisitor,
    CenterGroup,
    CenterMetadata,
    CenterStudyMetadata,
    DashboardProjectMetadata,
    DistributionProjectMetadata,
    FormIngestProjectMetadata,
    IngestProjectMetadata,
    PageProjectMetadata,
    ProjectMetadata,
    REDCapFormProjectMetadata,
)
from centers.nacc_group import NACCGroup
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import ProjectError
from redcap_api.redcap_project import REDCapRoles

from users.authorizations import (
    AuthMap,
    Authorizations,
    PageResource,
    StudyAuthorizations,
)
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)

log = logging.getLogger(__name__)


class AuthorizationError(Exception):
    """Exception class for errors during authorization."""


class CenterAuthorizationVisitor(AbstractCenterMetadataVisitor):
    """Assigns roles to a user within a center based on the center metadata
    objects."""

    def __init__(
        self,
        user: User,
        auth_email: str,
        user_authorizations: dict[str, StudyAuthorizations],
        auth_map: AuthMap,
        center_group: CenterGroup,
    ) -> None:
        self.__user = user
        self.__auth_email = auth_email
        self.__authorizations = user_authorizations
        self.__auth_map = auth_map
        self.__center = center_group
        self.__current_authorization: Optional[StudyAuthorizations] = None

    def visit_center(self, center: CenterMetadata) -> None:
        """Sets roles for the user in this authorization visitor based on the
        center metadata.

        Applies this visitor to each of the studies in the center metadata.
        And, adds the read-only role to the center metadata and portal projects.

        Args:
          center: the center metadata
        """
        for study in center.studies.values():
            study.apply(self)

        read_only_role = self.__auth_map.read_only_role
        metadata_project = self.__center.get_metadata()
        metadata_project.add_user_role(user=self.__user, role=read_only_role)

        center_portal = self.__center.get_portal()
        center_portal.add_user_role(user=self.__user, role=read_only_role)

    def __apply_authorizations(
        self, projects: Mapping[str, ProjectMetadata], pipeline_name: str
    ) -> None:
        log.info(
            "checking authorizations for user %s in %s %s projects",
            self.__user.id,
            len(projects),
            pipeline_name,
        )
        for project in projects.values():
            try:
                project.apply(self)
            except AuthorizationError as error:
                log.warning("Skipping authorization: %s", error)

    def visit_study(self, study: CenterStudyMetadata) -> None:
        """Sets roles for the user within the center projects for the study.

        Assigns roles to each ingest project, and to the accepted project.

        Note: this sets the current user authorization for this study
        required by the visit project methods.

        Args:
          study: center study metadata
        """
        authorizations = self.__authorizations.get(study.study_id)
        if authorizations is None:
            log.warning(
                "User %s has no authorization for study %s, skipping",
                self.__user.id,
                study.study_id,
            )
            return

        self.__current_authorization = authorizations

        ingest_projects = study.ingest_projects
        if ingest_projects:
            self.__apply_authorizations(
                projects=ingest_projects, pipeline_name="ingest"
            )

        dashboard_projects = study.dashboard_projects
        if dashboard_projects:
            self.__apply_authorizations(
                projects=dashboard_projects, pipeline_name="dashboard"
            )

        distribution_projects = study.distribution_projects
        if distribution_projects:
            self.__apply_authorizations(
                projects=distribution_projects, pipeline_name="distribution"
            )

        self.__current_authorization = None

    def visit_project(self, project_info: ProjectMetadata) -> None:
        """Assigns roles to the user for this project using the user's study
        authorizations and the role map.

        Note that subclasses of ProjectMetadata have their own visit methods
        that call this one.

        Args:
          project_info: the project metadata
        Raises:
          AuthorizationError if the project doesn't exist, there are no roles,
          or the role assignment failed.
        """
        if self.__current_authorization is None:
            raise AuthorizationError("User authorizations expected")

        project = self.__center.get_project_by_id(project_info.project_id)
        if not project:
            raise AuthorizationError(
                f"No project found with ID {project_info.project_id}"
            )

        role_set = self.__auth_map.get(
            project_label=project.label, authorizations=self.__current_authorization
        )
        if not role_set:
            raise AuthorizationError(
                f"No roles found for user {self.__user.id} in "
                f"project {self.__center.id}/{project.label}"
            )

        try:
            project.add_user_roles(user=self.__user, roles=role_set)
            log.info(
                "Added roles for user %s to project %s/%s",
                self.__user.id,
                self.__center.id,
                project.label,
            )
        except ProjectError as error:
            raise AuthorizationError(error) from error

    def visit_ingest_project(self, project_info: IngestProjectMetadata) -> None:
        """Assigns roles for the ingest project.

        Args:
          project_info: the ingest project
        """
        self.visit_project(project_info)

    def visit_form_ingest_project(self, project: FormIngestProjectMetadata) -> None:
        """Authorizes the user for the form ingest project.

        Args:
          project: the form ingest project metadata
        """
        if self.__current_authorization is None:
            raise AuthorizationError("User authorizations expected")

        self.visit_project(project)

        if not project.redcap_projects:
            log.warning(
                "REDCap project metadata not available for %s",
                project.project_label,
            )
            return

        log.info(
            "Checking REDCap permissions for ingest project %s/%s/%s",
            self.__current_authorization.study_id,
            self.__center.label,
            project.project_label,
        )
        redcap_authorized = False
        for redcap_metadata in project.redcap_projects.values():
            submission_activity = redcap_metadata.get_submission_activity()
            if submission_activity not in self.__current_authorization:
                continue

            redcap_authorized = True
            self.visit_redcap_form_project(redcap_metadata)

        if not redcap_authorized:
            log.info(
                "No REDCap access: no authorizations matched for user %s",
                self.__user.id,
            )

    def visit_redcap_form_project(self, project: REDCapFormProjectMetadata) -> None:
        """Assigns REDCap roles for the user to the project.

        Args:
          project: the REDCap form project metadata
        """
        redcap_project = self.__center.get_redcap_project(project.redcap_pid)

        if not redcap_project:
            log.error("No REDCap project %s found", project.redcap_pid)
            return

        if not redcap_project.assign_update_user_role_by_label(
            self.__auth_email, REDCapRoles.CENTER_USER_ROLE
        ):
            return

        log.info(
            "User %s (%s) is assigned %s permissions in REDCap project %s",
            self.__user.email,
            self.__auth_email,
            REDCapRoles.CENTER_USER_ROLE,
            redcap_project.title,
        )

    def visit_distribution_project(self, project: DistributionProjectMetadata) -> None:
        """Assigns user roles to the distribution project.

        Args:
          project: the distribution project metadata
        """
        self.visit_project(project)

    def visit_dashboard_project(self, project: DashboardProjectMetadata) -> None:
        """Assigns user roles to the dashboard project.

        Args:
          project: the dashboard project metadata
        """
        self.visit_project(project)

    def visit_page_project(self, project: PageProjectMetadata) -> None:
        """Assigns user roles to the page project.

        Args:
          project: the page project metadata
        """
        self.visit_project(project)


class GeneralAuthorizationVisitor:
    """Assigns roles to a user for general (non-center) resources based on
    authorizations.

    Follows the visitor pattern established by CenterAuthorizationVisitor.
    Handles page resources by assigning roles on page projects in the nacc admin group.

    This visitor processes general authorizations (not tied to specific centers) and
    assigns appropriate Flywheel roles to users for page projects. It collects error
    events for missing projects, missing roles, and role assignment failures to enable
    notification and troubleshooting without blocking processing.
    """

    def __init__(
        self,
        user: User,
        authorizations: "Authorizations",
        auth_map: AuthMap,
        nacc_group: "NACCGroup",
        collector: "UserEventCollector",
    ) -> None:
        """Initialize the general authorization visitor.

        Args:
            user: The Flywheel user to authorize
            authorizations: The general authorizations containing activities
            auth_map: The authorization map for looking up roles
            nacc_group: The NACC admin group containing page projects
            collector: Event collector for error tracking
        """
        self.__user = user
        self.__authorizations = authorizations
        self.__auth_map = auth_map
        self.__nacc_group = nacc_group
        self.__collector = collector

    def _create_user_context(self) -> UserContext:
        """Create UserContext from the current user.

        Returns:
            UserContext with user's email, name, and registry ID
        """
        return UserContext(
            email=self.__user.email,
            name=f"{self.__user.firstname} {self.__user.lastname}"  # type: ignore
            if self.__user.firstname  # type: ignore
            else "Unknown",
            registry_id=self.__user.id,
        )

    def visit_page_resource(self, page_resource: "PageResource") -> None:
        """Assigns user roles for a page resource.

        Constructs the project label as "page-{page_name}", retrieves the project
        from the NACC admin group, queries the authorization map for roles, and
        assigns the roles to the user.

        Handles errors gracefully by logging and collecting error events without
        raising exceptions, allowing processing to continue for other resources.

        Args:
            page_resource: The page resource to process
        """
        # Construct project label
        project_label = f"page-{page_resource.name}"

        # Retrieve project from NACC admin group
        project = self.__nacc_group.get_project(project_label)
        if not project:
            log.warning(
                "Page project not found: %s/%s", self.__nacc_group.id, project_label
            )
            # Create and collect error event
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.FLYWHEEL_ERROR,
                user_context=self._create_user_context(),
                message=(
                    f"Page project not found: {self.__nacc_group.id}/{project_label}"
                ),
                action_needed="create_page_project_or_update_authorization_config",
            )
            self.__collector.collect(error_event)
            return

        # Create temporary StudyAuthorizations for auth_map lookup
        study_authorizations = StudyAuthorizations(
            study_id="general", activities=self.__authorizations.activities
        )

        # Query authorization map for roles
        roles = self.__auth_map.get(
            project_label=project_label, authorizations=study_authorizations
        )

        if not roles:
            log.warning(
                "No roles found for user %s in page project %s",
                self.__user.id,
                project_label,
            )
            # Create and collect error event
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.INSUFFICIENT_PERMISSIONS,
                user_context=self._create_user_context(),
                message=(
                    f"No roles found for user {self.__user.id} "
                    f"in page project {project_label}"
                ),
                action_needed="update_authorization_map_for_page_project",
            )
            self.__collector.collect(error_event)
            return

        # Assign roles to user
        try:
            project.add_user_roles(user=self.__user, roles=roles)
            log.info(
                "Added roles for user %s to page project %s/%s",
                self.__user.id,
                self.__nacc_group.id,
                project_label,
            )
        except ProjectError as error:
            log.error(
                "Failed to assign roles to page project %s: %s",
                project_label,
                str(error),
            )
            # Create and collect error event
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.FLYWHEEL_ERROR,
                user_context=self._create_user_context(),
                message=(
                    f"Failed to assign roles to page project {project_label}: {error!s}"
                ),
                action_needed="check_flywheel_permissions_and_project_state",
            )
            self.__collector.collect(error_event)
