"""Module for working with a Group representing a center.

Should be used when starting from centers already created using
`projects.CenterMappingAdaptor`.
"""
import logging
import re
from typing import Dict, List, Optional

import flywheel
from flywheel_adaptor.flywheel_proxy import (FlywheelProxy, GroupAdaptor,
                                             ProjectAdaptor)
from projects.study import Center
from projects.template_project import TemplateProject

log = logging.getLogger(__name__)


class CenterGroup(GroupAdaptor):
    """Defines an adaptor for a group representing a center."""

    def __init__(self, *, group: flywheel.Group, proxy: FlywheelProxy) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__datatypes: List[str] = []
        self.__ingest_stages = ['ingest', 'retrospective']
        self.__center_id = None

    @classmethod
    def create(cls, center: Center, proxy: FlywheelProxy) -> 'CenterGroup':
        """Creates a flywheel.Group for the center and returns as a
        CenterGroup.

        Args:
          center: the study center
          proxy: the flywheel proxy object
        Returns:
          the CenterGroup for created group
        """
        group = proxy.get_group(group_label=center.name,
                                group_id=center.center_id)
        center_group = CenterGroup(group=group, proxy=proxy)
        for tag in center.tags:
            center_group.add_tag(tag)
        return center_group

    def center_id(self) -> Optional[int]:
        """Returns the center ID for this group."""
        if self.__center_id:
            return self.__center_id

        pattern = re.compile(r'adcid-(\d+)')
        tag = list(filter(pattern.match, self.get_tags()))[0]
        match = pattern.match(tag)
        if not match:
            return None

        return int(match.group(1))

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

    def get_metadata_project(self) -> Optional[ProjectAdaptor]:
        """Returns the metadata project for this center.

        Returns:
          the project labeled 'metadata', None if there is none
        """
        projects = self.__get_matching_projects('metadata')
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
