"""Mappings from NACC projects and centers to Flywheel groups and projects.

A coordinating center project is a multicenter study that collects data of one
or more datatypes.
For each center, there is a pipeline consisting of ingest and accepted stages.
A center has one ingest stage for each datatype collected by the project that
holds data that has not passed QC and been accepted by center curators.
The accepted stage holds all curated data that has been approved for general
use by the center curators.
This stage consolodates data accepted from ingest for all datatypes.

A Flywheel group is used to represent a center that contains Flywheel projects
for each stage of a project in which the center participates.
The mapping defined in this module is from a project P and center C to
1. one FW group for center C
2. one ingest FW project in this group for each datatype in project P
3. one accepted FW project in this group
The name of project P is used in the names of FW projects unless project P is
the primary project of the coordinating center.

For projects for which data shared externally by the coordinating center, there
is an additional release stage where data across centers is consolodated.
To represent this a project release group is created with a single "master"
project for managing the consolodated data.
"""
import logging
from typing import Dict, List, Optional

import flywheel  # type: ignore
from centers.center_group import CenterGroup
from flywheel.models.permission_access_permission import \
    PermissionAccessPermission
from flywheel.models.roles_role import RolesRole
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.group_adaptor import GroupAdaptor
from flywheel_adaptor.project_adaptor import ProjectAdaptor
from projects.project import Center, Project

log = logging.getLogger(__name__)


class ProjectMappingAdaptor:
    """Defines an adaptor for the coordinating center Project class that
    supports mapping to a data pipeline using Flywheel groups and projects."""

    def __init__(self,
                 *,
                 project: Project,
                 flywheel_proxy: FlywheelProxy,
                 admin_access: Optional[
                     List[PermissionAccessPermission]] = None,
                 center_roles: List[RolesRole]) -> None:
        """Creates an adaptor mapping the given project to the corresponding
        objects in the flywheel instance linked by the proxy.

        Args:
            project: the domain project
            flywheel_proxy: the proxy for the flywheel instance
            admin_access: the administrative users
            template_map: mapping from data types to template projects
            center_roles: the roles for center users
        """
        self.__fw = flywheel_proxy
        self.__project = project
        self.__release_group: Optional[GroupAdaptor] = None
        self.__admin_access = admin_access
        self.__center_roles = center_roles

    def has_datatype(self, datatype: str) -> bool:
        """Indicates whether this project has the datatype.

        Args:
            datatype: name of the datatype
        Returns:
            True if datatype is in this project, False otherwise
        """
        return datatype in self.__project.datatypes

    @property
    def datatypes(self) -> List[str]:
        """Exposes datatypes of this project."""
        return self.__project.datatypes

    @property
    def name(self) -> str:
        """Exposes project name."""
        return self.__project.name

    def build_project_id(self, prefix: str) -> str:
        """Builds a FW project ID string from the given prefix.

        Concatenates the name of the project, if is not the primary
        project of the coordinating center.

        Args:
            prefix: the prefix for the project ID
        Returns:
          the project id built using prefix
        """
        assert self.__project
        if self.__project.is_primary():
            return prefix
        return prefix + "-" + self.__project.project_id

    @property
    def accepted_id(self) -> str:
        """Builds a project ID for the accepted stage of this project."""
        return self.build_project_id('accepted')

    def get_ingest_id(self, datatype: str) -> Optional[str]:
        """Builds a project ID for the ingest for the data type of this
        project.

        Args:
            datatype: the name of the datatype
        Returns:
            the ingest project ID, or None if datatype is not in this project
        """
        if datatype not in self.__project.datatypes:
            return None

        return self.build_project_id('ingest-' + datatype.lower())

    @property
    def release_id(self) -> Optional[str]:
        """Builds the FW project ID string for the release stage for this
        project."""
        if not self.__project.is_published():
            return None

        return "release-" + self.__project.project_id

    def get_release_group(self) -> Optional[GroupAdaptor]:
        """Returns the release group for this project if it is published.
        Otherwise, returns None.

        Returns:
            the release group if project is published, otherwise None
        """
        if not self.__project.is_published():
            return None

        release_id = self.release_id
        assert release_id
        if not self.__release_group:
            group = self.__fw.get_group(group_label=self.__project.name +
                                        " Release",
                                        group_id=release_id)
            assert group
            self.__release_group = GroupAdaptor(group=group, proxy=self.__fw)
        return self.__release_group

    def get_master_project(self) -> Optional[flywheel.Project]:
        """Returns the FW consolidation project for this project if it is
        published. Otherwise, returns None.

        Returns:
            the consolidation project if published, otherwise None
        """
        if not self.__project.is_published():
            return None

        release_group = self.get_release_group()
        assert release_group
        return release_group.get_project(label='master-project')

    def create_center_pipelines(self) -> None:
        """Creates data pipelines for centers in this project."""
        if not self.__project.centers:
            log.warning(
                "Not creating center groups for project %s: no centers given",
                self.__project.name)
            return

        for center in self.__project.centers:
            center_adaptor = CenterMappingAdaptor(
                center=center,
                flywheel_proxy=self.__fw,
                admin_access=self.__admin_access,
                center_roles=self.__center_roles)
            center_adaptor.create_center_pipeline(self)

    def create_release_pipeline(self) -> None:
        """Creates the release pipeline for this project if the project is
        published."""
        if not self.__project.is_published():
            log.info("Project %s has no release project", self.__project.name)
            return

        release_group = self.get_release_group()
        master_project = self.get_master_project()

        if self.__project.is_published() and self.__admin_access:
            assert release_group
            for permission in self.__admin_access:
                release_group.add_user_access(permission)

            assert master_project
            master_project.add_admin_users(self.__admin_access)

    def create_project_pipelines(self) -> None:
        """Creates the pipelines for this project."""
        self.create_center_pipelines()
        self.create_release_pipeline()


class CenterMappingAdaptor:
    """Defines an adaptor mapping a center to Flywheel groups and projects to
    implement data pipelines for projects."""

    def __init__(self,
                 *,
                 center: Center,
                 flywheel_proxy: FlywheelProxy,
                 admin_access: Optional[
                     List[PermissionAccessPermission]] = None,
                 center_roles: Optional[List[RolesRole]]) -> None:
        """Initializes an adaptor for the given center using the Flywheel
        instance linked by the proxy.

        Args:
          center: the center object
          flywheel_proxy: the flywheel instance proxy
          admin_access: the administrative users from admin group
          template_map: template projects for project resources
          center_roles: the list of custom roles for user in center
        """
        self.__center = center
        self.__fw = flywheel_proxy
        self.__group: Optional[CenterGroup] = None
        self.__admin_access = admin_access
        self.__center_roles = center_roles

    def get_group(self) -> CenterGroup:
        """Gets the FW group for this center.

        Uses memoization - gets the group once.

        Returns:
            the Flywheel group for this center
        """
        if not self.__group:
            group = self.__fw.get_group(group_label=self.__center.name,
                                        group_id=self.__center.center_id)
            self.__group = CenterGroup(group=group, proxy=self.__fw)
        return self.__group

    def get_accepted_project(
            self, project: ProjectMappingAdaptor) -> Optional[ProjectAdaptor]:
        """Returns the FW project for the accepted stage of the project for
        this center.

        Args:
          project: the project mapping adaptor for project
        Returns:
            the Flywheel project
        """
        accepted_project = self.__fw.get_project(
            group=self.get_group(), project_label=project.accepted_id)
        if not accepted_project:
            return None

        return ProjectAdaptor(project=accepted_project, proxy=self.__fw)

    def get_ingest_project(self, *, project: ProjectMappingAdaptor,
                           datatype: str) -> Optional[ProjectAdaptor]:
        """Returns the FW project for the ingest stage of this center for the
        project and datatype. Requires that the center is active in the
        project, and that the datatype is included in the project.

        Args:
          project: the mapping for the project
          datatype: the datatype for ingest
        Returns:
            the ingest FW project, or None if datatype not in project or
            center is not active in project
        """
        if not self.__center.is_active():
            return None
        if not project.has_datatype(datatype):
            return None

        ingest_id = project.get_ingest_id(datatype)
        assert ingest_id

        ingest_project = self.__fw.get_project(group=self.get_group(),
                                               project_label=ingest_id)
        if not ingest_project:
            return None

        return ProjectAdaptor(project=ingest_project, proxy=self.__fw)

    def get_metadata_project(self) -> Optional[ProjectAdaptor]:
        """Returns the FW project for storing center metadata.

        Returns:
            the FW project
        """
        metadata_project = self.__fw.get_project(group=self.get_group(),
                                                 project_label="metadata")
        if not metadata_project:
            return None

        return ProjectAdaptor(project=metadata_project, proxy=self.__fw)

    def get_retrospective_project(self, *, project: ProjectMappingAdaptor,
                                  datatype: str) -> Optional[ProjectAdaptor]:
        """Returns the FW project for the retrospective stage of this center
        for the project and datatype. Requires that the datatype is included in
        the project. Essentially, ingest for previously QC'd data.

        Args:
          project: the mapping for the project
          datatype: the datatype for ingest
        Returns:

          project
        """
        if not project.has_datatype(datatype):
            return None

        retrospective_id = project.build_project_id('retrospective-' +
                                                    datatype.lower())
        assert retrospective_id

        retro_project = self.__fw.get_project(group=self.get_group(),
                                              project_label=retrospective_id)
        if not retro_project:
            return None

        return ProjectAdaptor(project=retro_project, proxy=self.__fw)

    def create_ingest_projects(
            self, project: ProjectMappingAdaptor) -> Dict[str, ProjectAdaptor]:
        """Creates ingest projects for the given project within the group for
        this center.

        Args:
            project: the mapping adaptor for the project
        Returns:
            map of data type to ingest created ingest projects
        """
        if not self.__center.is_active():
            log.info("Not creating ingest for inactive center %s",
                     self.__center.name)
            return {}
        if not project.datatypes:
            log.warning("No ingest groups created for %s: no datatypes given",
                        project.name)
            return {}

        project_map = {}
        for datatype in project.datatypes:
            ingest_project = self.get_ingest_project(project=project,
                                                     datatype=datatype)
            if ingest_project:
                project_map[datatype] = ProjectAdaptor(project=ingest_project,
                                                       proxy=self.__fw)
                self.add_tags(ingest_project)

        return project_map

    def create_retrospective_projects(
            self, project: ProjectMappingAdaptor) -> Dict[str, ProjectAdaptor]:
        """Creates retrospective ingest projects for the given project within
        the group for this center.

        Args:
          project: the mapping adaptor for the project
        Returns:
          map of datatype to created retrospective ingest projects
        """
        if not project.datatypes:
            log.warning(
                "No retrospective ingest projects created for %s: "
                "no datatypes given", project.name)
            return {}

        project_map = {}
        for datatype in project.datatypes:
            retrospective_project = self.get_retrospective_project(
                project=project, datatype=datatype)
            if retrospective_project:
                project_map[datatype] = ProjectAdaptor(
                    project=retrospective_project, proxy=self.__fw)
                self.add_tags(retrospective_project)

        return project_map

    def add_tags(self, project: ProjectAdaptor) -> None:
        """Adds tags from this center to the project.

        Note: requires that tag is enabled in the group for the center.

        Args:
          project: the project to add tags to
        """
        for tag in self.__center.tags:
            project.add_tag(tag)

    def create_center_pipeline(self, project: ProjectMappingAdaptor) -> None:
        """Creates FW groups and projects for data pipeline of the given
        project in this center.

        Args:
            project: the project mapping adaptor
        """
        center_group = self.get_group()
        for tag in self.__center.tags:
            if tag not in center_group.get_tags():
                center_group.add_tag(tag)
        if self.__center_roles:
            for role in self.__center_roles:
                center_group.add_role(role)
        if self.__admin_access:
            for permission in self.__admin_access:
                center_group.add_user_access(permission)

        self.create_ingest_projects(project)
        self.create_retrospective_projects(project)
        self.get_accepted_project(project)
        self.get_metadata_project()
