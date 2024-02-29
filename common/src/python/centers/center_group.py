"""Module for working with a Group representing a center.

Should be used when starting from centers already created using
`projects.CenterMappingAdaptor`.
"""
import logging
import re
from typing import Dict, List, Optional

import flywheel
from flywheel.models.group import Group
from flywheel_adaptor.flywheel_proxy import (FlywheelProxy, GroupAdaptor,
                                             ProjectAdaptor)
from projects.study import Center, Study
from projects.template_project import TemplateProject
from pydantic import AliasGenerator, BaseModel, ConfigDict, ValidationError

log = logging.getLogger(__name__)


class CenterGroup(GroupAdaptor):
    """Defines an adaptor for a group representing a center."""

    def __init__(self, *, adcid: int, active: bool, group: flywheel.Group,
                 proxy: FlywheelProxy) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__datatypes: List[str] = []
        self.__ingest_stages = ['ingest', 'retrospective']
        self.__adcid = adcid
        self.__is_active = active
        self.__center_portal: Optional[ProjectAdaptor] = None
        self.__metadata: Optional[ProjectAdaptor] = None

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

        return center_group

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
        metadata_project.update_info({
            'adcid': center.adcid,
            'active': center.is_active()
        })

        return center_group

    @property
    def adcid(self) -> int:
        """The ADCID of this center."""
        return self.__adcid

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

    def get_metadata(self) -> Optional[ProjectAdaptor]:
        """Returns the metadata project for this center.

        Returns:
          the project labeled 'metadata', None if there is none
        """
        if not self.__metadata:
            self.__metadata = self.get_project('metadata')
            assert self.__metadata, "expecting metadata project"

        return self.__metadata

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
        portal_info = self.get_portal_info()

        study_info = portal_info.get(study)

        suffix = f"-{study.study_id}"
        if study.is_primary():
            suffix = ""

        site = self.proxy().get_site()

        accepted_label = f"accepted{suffix}"
        accepted_project = self.__add_project(accepted_label)
        study_info.add_accepted(
            ProjectMetadata.create(site=site,
                                   study_id=study.study_id,
                                   project_id=accepted_project.id,
                                   project_label=accepted_label))

        if self.__is_active:
            for pipeline in ['ingest', 'sandbox']:
                for datatype in study.datatypes:
                    project_label = f"{pipeline}-{datatype.lower()}{suffix}"
                    project = self.__add_project(project_label)
                    study_info.add_ingest(
                        IngestProjectMetadata.create(
                            site=site,
                            study_id=study.study_id,
                            project_id=project.id,
                            project_label=project_label,
                            datatype=datatype))

        self.update_portal_info(portal_info)

        labels = [
            f"retrospective-{datatype.lower()}" for datatype in study.datatypes
        ]
        for label in labels:
            self.__add_project(label)

    def get_portal_info(self) -> 'CenterPortalMetadata':
        """Gets the portal info for this center.

        Returns:
          the center portal metadata object for the info of the portal project
        Raises:
            CenterError: if info in portal project is not in expected format
        """
        portal_project = self.get_portal()
        info = portal_project.get_info()
        if not info:
            return CenterPortalMetadata(studies={})

        if not 'studies' in info:
            return CenterPortalMetadata(studies={})
        
        try:
            return CenterPortalMetadata.model_validate(info)
        except ValidationError as error:
            raise CenterError(f"Info in {self.label}/{portal_project.label}"
                              " does not match expected format") from error

    def update_portal_info(self, portal_info: 'CenterPortalMetadata') -> None:
        """Updates the portal info for this center.

        Args:
          portal_info: the center portal metadata object
        """
        portal_project = self.get_portal()
        portal_project.update_info(
            portal_info.model_dump(by_alias=True, exclude_none=True))

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
    project_url: str

    @staticmethod
    def create(*, site: str, study_id: str, project_id: str,
               project_label: str) -> 'ProjectMetadata':
        """Creates a ProjectMetadata object.

        Args:
          site: the site url
          study_id: the study
          project_id: the project id
          project_label: the project label
        Returns:
          the constructed ProjectMetadata object
        """
        return ProjectMetadata(
            study_id=study_id,
            project_id=project_id,
            project_label=project_label,
            project_url=f"{site}/#/projects/{project_id}/information")


class IngestProjectMetadata(ProjectMetadata):
    """Metadata for an ingest project of a center."""
    datatype: str

    # pylint: disable=(arguments-differ)
    @staticmethod
    def create(
            *,
            site: str,
            study_id: str,
            project_id: str,  # type: ignore
            project_label: str,
            datatype: str) -> 'IngestProjectMetadata':
        """Creates an IngestProjectMetadata object.

        Args:
            site: the site url
            study_id: the study
            project_id: the project id
            project_label: the project label
            datatype: the datatype
        Returns:
            the constructed IngestProjectMetadata object
        """
        return IngestProjectMetadata(
            study_id=study_id,
            project_id=project_id,
            project_label=project_label,
            project_url=f"{site}/#/projects/{project_id}/information",
            datatype=datatype)


class FormIngestProjectMetadata(IngestProjectMetadata):
    """Metadata for a form ingest project.

    This class represents the metadata for a form ingest project within
    a center. It inherits from the FormIngestProjectMetadata class and
    adds additional attributes specific to form ingest projects.
    """
    redcap_project_id: int
    redcap_url: str

    # pylint: disable=(arguments-differ)
    @staticmethod
    def create(
            *,
            site: str,
            study_id: str,
            project_id: str,  # type: ignore
            project_label: str,
            datatype: str,
            redcap_site: str,
            redcap_project_id: int) -> 'FormIngestProjectMetadata':
        """Creates a FormIngestProjectMetadata object.

        Args:
            site: the site url
            study_id: the study
            project_id: the project id
            project_label: the project label
            datatype: the datatype
            redcap_site: the REDCap site url
            redcap_project_id: the REDCap project id

        Returns:
            the constructed FormIngestProjectMetadata object
        """
        return FormIngestProjectMetadata(
            study_id=study_id,
            project_id=project_id,
            project_label=project_label,
            project_url=f"{site}/#/projects/{project_id}/information",
            datatype=datatype,
            redcap_project_id=redcap_project_id,
            redcap_url=f"{redcap_site}/index.php?pid={redcap_project_id}")


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


class CenterPortalMetadata(BaseModel):
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
