"""Module for working with a Group representing a center.

Should be used when starting from centers already created using
`projects.CenterMappingAdaptor`.
"""
import logging
import re
from typing import Dict, List, Optional

import flywheel
from centers.center_adaptor import CenterAdaptor
from flywheel.models.group import Group
from flywheel.models.role_output import RoleOutput
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import (FlywheelProxy, GroupAdaptor,
                                             ProjectAdaptor)
from projects.study import Center, Study
from projects.template_project import TemplateProject
from pydantic import AliasGenerator, BaseModel, ConfigDict, ValidationError
from users.authorizations import AuthMap
from users.nacc_directory import Authorizations

log = logging.getLogger(__name__)


class CenterGroup(CenterAdaptor):
    """Defines an adaptor for a group representing a center."""

    def __init__(self, *, adcid: int, active: bool, group: flywheel.Group,
                 proxy: FlywheelProxy) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__datatypes: List[str] = []
        self.__ingest_stages = ['ingest', 'retrospective', 'sandbox']
        self.__adcid = adcid
        self.__is_active = active
        self.__center_portal: Optional[ProjectAdaptor] = None

    @classmethod
    def create_from_group(cls, *, proxy: FlywheelProxy,
                          group: Group) -> 'CenterGroup':
        """Creates a CenterGroup from either a center or an existing group.

        Args:
          group: an existing group
          proxy: the flywheel proxy object
        Returns:
          the CenterGroup for created group
        """
        project = proxy.get_project(group=group, project_label='metadata')
        if not project:
            raise CenterError(
                f"Unable to create center from group {group.label}")

        metadata_project = ProjectAdaptor(project=project, proxy=proxy)
        metadata_info = metadata_project.get_info()
        if 'adcid' not in metadata_info:
            raise CenterError(
                f"Expected group {group.label}/metadata.info to have ADCID")

        adcid = metadata_info['adcid']
        active = metadata_info.get('active', False)

        center_group = CenterGroup(adcid=adcid,
                                   active=active,
                                   group=group,
                                   proxy=proxy)
        metadata_project.add_admin_users(center_group.get_user_access())

        return center_group

    @classmethod
    def create_from_group_adaptor(cls, *,
                                  adaptor: GroupAdaptor) -> 'CenterGroup':
        """Creates a CenterGroup from a GroupAdaptor.

        Args:
          adaptor: the group adaptor
          proxy: the flywheel proxy object
        Returns:
          the CenterGroup for the group
        """
        # pylint: disable=protected-access
        return CenterGroup.create_from_group(proxy=adaptor.proxy(),
                                             group=adaptor._group)

    @classmethod
    def create_from_center(cls, *, proxy: FlywheelProxy,
                           center: Center) -> 'CenterGroup':
        """Creates a CenterGroup from a center object.

        Args:
          center: the study center
          proxy: the flywheel proxy object
        Returns:
          the CenterGroup for the center
        """
        group = proxy.get_group(group_label=center.name,
                                group_id=center.center_id)
        assert group, "No group for center"
        center_group = CenterGroup(adcid=center.adcid,
                                   active=center.is_active(),
                                   group=group,
                                   proxy=proxy)

        tags = list(center.tags)
        adcid_tag = f"adcid-{center.adcid}"
        if adcid_tag not in tags:
            tags.append(adcid_tag)
        center_group.add_tags(tags)

        metadata_project = center_group.get_metadata()
        assert metadata_project, "expecting metadata project"
        metadata_project.add_admin_users(center_group.get_user_access())
        metadata_project.update_info({
            'adcid': center.adcid,
            'active': center.is_active()
        })

        return center_group

    @property
    def adcid(self) -> int:
        """The ADCID of this center."""
        return self.__adcid

    def is_active(self) -> bool:
        """Indicates whether the center is active."""
        return self.__is_active

    def __get_matching_projects(self, prefix: str) -> List[ProjectAdaptor]:
        """Returns the projects for the center with labels that match the
        prefix.

        Returns:
          the list of matching projects for the group
        """
        pattern = re.compile(rf"^{prefix}")
        return [
            ProjectAdaptor(project=project, proxy=self.proxy())
            for project in self.projects() if pattern.match(project.label)
        ]

    def get_ingest_projects(self) -> List[ProjectAdaptor]:
        """Returns the ingest projects for the center.

        Returns:
          the list of ingest projects
        """
        projects: List[ProjectAdaptor] = []
        for stage in self.__ingest_stages:
            projects = projects + self.__get_matching_projects(f"{stage}-")

        return projects

    def get_accepted_project(self) -> Optional[ProjectAdaptor]:
        """Returns the accepted project for this center.

        Returns:
          the project labeled 'accepted', None if there is none
        """
        projects = self.__get_matching_projects('accepted')
        if not projects:
            return None

        return projects[0]

    @classmethod
    def get_datatype(cls, *, stage: str, label: str) -> Optional[str]:
        """Gets the datatype from a string with format `<stage-
        name>-<datatype>`.

        Args:
          stage: stage name
          label: string with stage and datatype
        Returns:
          the datatype in the string if matches pattern. Otherwise, None
        """
        pattern = re.compile(rf"^{stage}-(\w+)")
        match = pattern.match(label)
        if not match:
            return None

        return match.group(1)

    def get_datatypes(self) -> List[str]:
        """Returns the list of data types for the ingest projects of this
        center.

        Returns:
          list of datatype names
        """
        if self.__datatypes:
            return self.__datatypes

        datatypes = []
        for stage in self.__ingest_stages:
            projects = self.__get_matching_projects(f"{stage}-")
            for project in projects:
                datatype = CenterGroup.get_datatype(stage=stage,
                                                    label=project.label)
                if datatype:
                    datatypes.append(datatype)
        self.__datatypes = list(set(datatypes))

        return self.__datatypes

    def apply_to_ingest(
            self, *, stage: str,
            template_map: Dict[str, Dict[str, TemplateProject]]) -> None:
        """Applies the templates to the ingest stage projects in group.

        Expects that project labels match pattern
        `<stage-name>-<datatype-name>`.
        For instance, `ingest-form` or `retrospective-dicom`.

        Args:
          stage: name of ingest stage
          template_map: map from datatype to stage to template project
        """
        ingest_projects = self.__get_matching_projects(f"{stage}-")
        if not ingest_projects:
            log.warning('no ingest stage projects for group %s', self.label)
            return

        for project in ingest_projects:
            datatype = CenterGroup.get_datatype(stage=stage,
                                                label=project.label)
            if not datatype:
                log.info('ingest project %s has no datatype', project.label)
                continue

            self.__apply_to(stage=stage,
                            template_map=template_map,
                            project=project,
                            datatype=datatype)

    def apply_to_accepted(
            self, template_map: Dict[str, Dict[str, TemplateProject]]) -> None:
        """Applies the templates in the map to the accepted project in the
        group.

        Expects the accepted project to be named `accepted`.

        Args:
          template_map: map from datatype to stage to template project
        """
        stage = 'accepted'
        accepted_projects = self.__get_matching_projects(stage)
        if not accepted_projects:
            log.warning('no accepted stage project in center group %s',
                        self.label)
            return

        self.__apply_to(template_map=template_map,
                        project=accepted_projects[0],
                        stage=stage,
                        datatype='all')

    def __apply_to(self, *, template_map: Dict[str, Dict[str,
                                                         TemplateProject]],
                   project: ProjectAdaptor, stage: str, datatype: str):
        """Applies the template map to the project for stage and datatype.

        Args:
          template_map: map from datatype to stage to template project
          project: the destination project
          stage: the stage for the destination
          datatype: the datatype for the destination
        """
        stage_map = template_map.get(datatype)
        if stage_map:
            template_project = stage_map.get(stage)
            if template_project:
                template_project.copy_to(project,
                                         value_map={
                                             'adrc': self.label,
                                             'project_id': project.id,
                                             'site': self.proxy().get_site()
                                         })

    def apply_template_map(
            self, template_map: Dict[str, Dict[str, TemplateProject]]) -> None:
        """Applies the template map to the pipeline projects within the center
        group.

        Args:
          template_map: map from datatype to stage to template project
        """
        for stage in self.__ingest_stages:
            self.apply_to_ingest(stage=stage, template_map=template_map)

        self.apply_to_accepted(template_map)

    def get_portal(self) -> ProjectAdaptor:
        """Returns the center-portal project.

        Returns:
          The center-portal project
        """
        if not self.__center_portal:
            self.__center_portal = self.get_project('center-portal')
            assert self.__center_portal, "expecting center-portal project"

        return self.__center_portal

    def add_study(self, study: Study) -> None:
        """Adds pipeline details for study.

        Args:
          study: the study
        """
        portal_info = self.get_project_info()

        study_info = portal_info.get(study)

        suffix = f"-{study.study_id}"
        if study.is_primary():
            suffix = ""

        admin_access = self.get_user_access()

        accepted_label = f"accepted{suffix}"
        accepted_project = self.__add_project(accepted_label)
        study_info.add_accepted(
            ProjectMetadata(study_id=study.study_id,
                            project_id=accepted_project.id,
                            project_label=accepted_label))
        accepted_project.add_admin_users(admin_access)

        if self.__is_active:
            for pipeline in ['ingest', 'sandbox']:
                for datatype in study.datatypes:
                    project_label = f"{pipeline}-{datatype.lower()}{suffix}"
                    project = self.__add_project(project_label)
                    study_info.add_ingest(
                        IngestProjectMetadata(study_id=study.study_id,
                                              project_id=project.id,
                                              project_label=project_label,
                                              datatype=datatype))
                    project.add_admin_users(admin_access)

        portal_project = self.__add_project('center-portal')
        portal_project.add_admin_users(admin_access)

        self.update_project_info(portal_info)

        labels = [
            f"retrospective-{datatype.lower()}" for datatype in study.datatypes
        ]
        for label in labels:
            project = self.__add_project(label)
            project.add_admin_users(admin_access)

    def add_redcap_project(self, redcap_project: 'REDCapProjectInput') -> None:
        """Adds the REDCap project to the center group.

        Args:
          redcap_project: the REDCap project input
        """
        project_info = self.get_project_info()
        study_info = project_info.studies.get(redcap_project.study_id, None)
        if not study_info:
            log.warning('no study info for study %s in center %s',
                        redcap_project.study_id, self.label)
            return

        ingest_project = study_info.get_ingest(redcap_project.project_label)
        if not ingest_project:
            log.warning('no ingest project for study %s in center %s',
                        redcap_project.study_id, self.label)
            return

        form_ingest_project = FormIngestProjectMetadata.create_from_ingest(
            ingest_project)
        for form_project in redcap_project.projects:
            form_ingest_project.add(form_project)

        study_info.add_ingest(form_ingest_project)
        project_info.add(study_info)
        self.update_project_info(project_info)

    def get_project_info(self) -> 'CenterProjectMetadata':
        """Gets the portal info for this center.

        Returns:
          the center portal metadata object for the info of the portal project
        Raises:
            CenterError: if info in portal project is not in expected format
        """
        metadata_project = self.get_metadata()
        if not metadata_project:
            log.error('no metadata project for %s, cannot get info',
                      self.label)
            raise CenterError(f"no metadata project for {self.label}")

        info = metadata_project.get_info()
        if not info:
            return CenterProjectMetadata(studies={})

        if 'studies' not in info:
            return CenterProjectMetadata(studies={})

        try:
            return CenterProjectMetadata.model_validate(info)
        except ValidationError as error:
            raise CenterError(f"Info in {self.label}/{metadata_project.label}"
                              " does not match expected format") from error

    def update_project_info(self,
                            project_info: 'CenterProjectMetadata') -> None:
        """Updates the portal info for this center.

        Args:
          portal_info: the center portal metadata object
        """
        metadata_project = self.get_metadata()
        if not metadata_project:
            log.error('no metadata project for %s, cannot update info',
                      self.label)
            return

        metadata_project.update_info(
            project_info.model_dump(by_alias=True, exclude_none=True))

    def __add_project(self, label: str) -> ProjectAdaptor:
        """Adds a project with the label to this group and returns the
        corresponding ProjectAdaptor.

        Args:
          label: the label for the project
        Returns:
          the ProjectAdaptor for the project
        """
        project = self.get_project(label)
        if not project:
            raise CenterError(f"failed to create project {self.label}/{label}")

        project.add_tags(self.get_tags())
        return project

    def add_user_roles(self, user: User, authorizations: Authorizations,
                       auth_map: AuthMap) -> None:
        """Adds user authorized projects in the center group.

        Args:
          user: the user to add
          authorizations: the authorizations for the user
        """
        assert user.id, "requires user has ID"
        log.info("Adding roles for user %s", user.id)

        portal_info = self.get_project_info()
        study_info = portal_info.studies.get(authorizations.study_id, None)
        if not study_info:
            log.warning('No study info for study %s in center %s',
                        authorizations.study_id, self.label)
            return

        accepted_project = study_info.accepted_project
        if accepted_project:
            self.__add_user_roles_to_project(
                user=user,
                project_id=accepted_project.project_id,
                auth_map=auth_map,
                authorizations=authorizations)

        ingest_projects = study_info.ingest_projects
        for project in ingest_projects.values():
            self.__add_user_roles_to_project(user=user,
                                             project_id=project.project_id,
                                             auth_map=auth_map,
                                             authorizations=authorizations)

        metadata_project = self.get_metadata()
        if metadata_project:
            self.__add_user_roles_to_project(user=user,
                                             project_id=metadata_project.id,
                                             auth_map=auth_map,
                                             authorizations=authorizations)

        center_portal = self.get_portal()
        if center_portal:
            self.__add_user_roles_to_project(user=user,
                                             project_id=center_portal.id,
                                             auth_map=auth_map,
                                             authorizations=authorizations)

    def __add_user_roles_to_project(self, *, user: User, project_id: str,
                                    authorizations: Authorizations,
                                    auth_map: AuthMap) -> bool:
        """Adds user to the project with the role.

        Args:
          user: the user to add
          role: the role to add
          project_id: the project ID
        Returns:
          True if user was added, False otherwise
        """
        assert user.id, "requires user has ID"

        project = self.get_project_by_id(project_id)
        if not project:
            return False

        role_set = auth_map.get(project_label=project.label,
                                authorizations=authorizations)
        if not role_set:
            log.warning('No roles found for user %s in project %s/%s', user.id,
                        self.id, project.label)
            return False

        role_map = self._fw.get_roles()
        roles: List[RoleOutput] = []
        for role_name in role_set:
            role = role_map.get(role_name)
            if role:
                roles.append(role)
            else:
                log.warning('No role %s found', role_name)

        return project.add_user_roles(user=user, roles=roles)


class CenterError(Exception):
    """Exception classes for errors related to using group to capture center
    details."""

    def __init__(self, message: str) -> None:
        self.__message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.__message

    @property
    def message(self) -> str:
        """Returns the message for this error.

        Returns:
          the message
        """
        return self.__message


def kebab_case(name: str) -> str:
    """Converts the name to kebab case.

    Args:
      name: the name to convert
    Returns:
      the name in kebab case
    """
    return name.lower().replace('_', '-')


class ProjectMetadata(BaseModel):
    """Metadata for a center project. Set datatype for ingest projects.

    Dump with by_alias and exclude_none set to True.
    """
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case),
                              extra='forbid')

    study_id: str
    project_id: str
    project_label: str


class IngestProjectMetadata(ProjectMetadata):
    """Metadata for an ingest project of a center."""
    datatype: str


class REDCapFormProject(BaseModel):
    """Metadata for a REDCap form project."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))

    redcap_pid: int
    label: str
    report_id: Optional[int] = None


class FormIngestProjectMetadata(IngestProjectMetadata):
    """Metadata for a form ingest project.

    This class represents the metadata for a form ingest project within
    a center. It inherits from the FormIngestProjectMetadata class and
    adds additional attributes specific to form ingest projects.
    """
    redcap_projects: Dict[str, REDCapFormProject] = {}

    @classmethod
    def create_from_ingest(
            cls, ingest: IngestProjectMetadata) -> 'FormIngestProjectMetadata':
        """Creates a FormIngestProjectMetadata from an IngestProjectMetadata.

        Args:
            ingest: the ingest project metadata
        Returns:
            the FormIngestProjectMetadata for the ingest project
        """
        return FormIngestProjectMetadata(study_id=ingest.study_id,
                                         project_id=ingest.project_id,
                                         project_label=ingest.project_label,
                                         datatype=ingest.datatype)

    def add(self, redcap_project: REDCapFormProject) -> None:
        """Adds the REDCap project to the form ingest project metadata.

        Args:
            redcap_project: the REDCap project metadata
        """
        self.redcap_projects[redcap_project.label] = redcap_project

    def get(self, module_name: str) -> Optional[REDCapFormProject]:
        """Gets the REDCap project metadata for the module name.

        Args:
            module_name: the module name
        Returns:
            the REDCap project metadata for the module name
        """
        return self.redcap_projects.get(module_name, None)


class StudyMetadata(BaseModel):
    """Metadata for study details within a participating center."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))

    study_id: str
    study_name: str
    ingest_projects: Dict[str, (IngestProjectMetadata
                                | FormIngestProjectMetadata)] = {}
    accepted_project: Optional[ProjectMetadata] = None

    def add_accepted(self, project: ProjectMetadata) -> None:
        """Adds the accepted project to the study metadata.

        Args:
            project: the accepted project metadata
        """
        self.accepted_project = project

    def add_ingest(self, project: IngestProjectMetadata) -> None:
        """Adds the ingest project to the study metadata.

        Args:
            project: the ingest project metadata
        """
        self.ingest_projects[project.project_label] = project

    def get_ingest(self,
                   project_label: str) -> Optional[IngestProjectMetadata]:
        """Gets the ingest project metadata for the project label.

        Args:
            project_label: the project label
        Returns:
            the ingest project metadata for the project label
        """
        return self.ingest_projects.get(project_label, None)


class CenterProjectMetadata(BaseModel):
    """Metadata to be stored in center portal project."""
    studies: Dict[str, StudyMetadata]

    def add(self, study: StudyMetadata) -> None:
        """Adds study metadata to the studies.

        Args:
            study: The StudyMetadata object to be added.

        Returns:
            None
        """
        self.studies[study.study_id] = study

    def get(self, study: Study) -> StudyMetadata:
        """Gets the study metadata for the study id.

        Creates a new StudyMetadata object if it does not exist.

        Args:
            study_id: the study id
        Returns:
            the study metadata for the study id
        """
        study_info = self.studies.get(study.study_id, None)
        if study_info:
            return study_info

        study_info = StudyMetadata(study_id=study.study_id,
                                   study_name=study.name)
        self.add(study_info)
        return study_info


class REDCapProjectInput(BaseModel):
    """Metadata for REDCap project details."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))

    center_id: str
    study_id: str
    project_label: str
    projects: List[REDCapFormProject]


class REDCapModule(BaseModel):
    """Information required to create a REDCap project for a module."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))
    label: str
    title: str
    template: Optional[str] = None


class REDCapProjectMapping(BaseModel):
    """List of REDCap projects associated with a Flywheel project."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))
    project_label: str
    modules: List[REDCapModule]


class StudyREDCapMetadata(BaseModel):
    """REDCap project info associated with a study."""
    model_config = ConfigDict(populate_by_name=True,
                              alias_generator=AliasGenerator(alias=kebab_case))
    study_id: str
    centers: List[str]
    projects: List[REDCapProjectMapping]
