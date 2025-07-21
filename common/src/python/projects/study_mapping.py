"""Mappings from NACC studies and centers to Flywheel groups and projects.

A coordinating center study is a multi-center study that collects data of one
or more datatypes.
For each center, there is a pipeline consisting of ingest and accepted stages.
A center has one ingest stage for each datatype collected by the study that
holds data that has not passed QC and been accepted by center curators.
The accepted stage holds all curated data that has been approved for general
use by the center curators.
This stage consolidates data accepted from ingest for all datatypes.

A Flywheel group is used to represent a center that contains Flywheel projects
for each stage of a study in which the center participates.
The mapping defined in this module is from a study P and center C to
1. one FW group for center C
2. one ingest and one sandbox FW project in this group for each datatype in
   study P
3. one accepted FW project in this group
The name of study P is used in the names of FW projects unless study P is
the primary study of the coordinating center.

For studies for which data shared externally by the coordinating center, there
is an additional release stage where data across centers is consolidated.
To represent this a study release group is created with a single "master"
project for managing the consolidated data.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from centers.center_group import (
    CenterError,
    CenterGroup,
    DistributionProjectMetadata,
    IngestProjectMetadata,
    ProjectMetadata,
    StudyMetadata,
)
from flywheel.models.access_permission import AccessPermission
from flywheel_adaptor.flywheel_proxy import (
    FlywheelProxy,
    GroupAdaptor,
    ProjectAdaptor,
)

from projects.study import Study, StudyVisitor
from projects.study_group import StudyGroup

log = logging.getLogger(__name__)


class StudyMapper(ABC):
    """Defines the interface for classes that map study objects to FW
    containers."""

    @abstractmethod
    def map_center_pipelines(
        self, center: CenterGroup, study_info: StudyMetadata
    ) -> None:
        """Maps the study to pipelines within a center.

        Args:
          center: the center group
          study_info: the metadata object to track center projects
        """

    @abstractmethod
    def map_study_pipelines(self) -> None:
        """Maps the study to study level groups and projects."""


class AggregationMapper(StudyMapper):
    """Defines the mapping of an aggregation study to center and study level
    pipelines.

    Creates groups at the study level if needed.
    """

    def __init__(
        self,
        *,
        study: Study,
        pipelines: List[str],
        proxy: FlywheelProxy,
        admin_access: List[AccessPermission],
    ) -> None:
        self.__fw = proxy
        self.__study = study
        self.__pipelines = pipelines
        self.__admin_access = admin_access
        self.__release_group: Optional[GroupAdaptor] = None

    def map_center_pipelines(
        self, center: CenterGroup, study_info: StudyMetadata
    ) -> None:
        """Creates accepted, ingest and retrospective projects in the group.
        Updates the study metadata.

        Args:
          center: the center group
          study_info: the study metadata
        """
        self.__add_accepted(center=center, study_info=study_info)
        if center.is_active():
            for pipeline in self.__pipelines:
                for datatype in self.__study.datatypes:
                    self.__add_ingest(
                        center=center,
                        study_info=study_info,
                        pipeline=pipeline,
                        datatype=datatype,
                    )

        self.__add_retrospective(center)

    def map_study_pipelines(self) -> None:
        """Creates study group with release project."""
        if not self.__study.is_published():
            log.info("Study %s has no release project", self.__study.name)
            return

        self.__get_release_group()
        self.__get_master_project()

    def __add_accepted(self, *, center: CenterGroup, study_info: StudyMetadata) -> None:
        """Creates an accepted project in the center group, and updates the
        study metadata.

        Args:
          center: the center group
          study_info: the study metadata
        """
        accepted_label = f"accepted{self.__study.project_suffix()}"
        accepted_project = center.add_project(accepted_label)
        study_info.add_accepted(
            ProjectMetadata(
                study_id=self.__study.study_id,
                project_id=accepted_project.id,
                project_label=accepted_label,
            )
        )

    def __add_ingest(
        self,
        *,
        center: CenterGroup,
        pipeline: str,
        datatype: str,
        study_info: StudyMetadata,
    ) -> None:
        """Adds an ingest projects for the study datatype to the center.

        Args:
          center: the center group
          study_info: the center study metadata
          pipeline: the name of the pipeline
          datatype: the name of the datatype
        """
        project_label = f"{pipeline}-{datatype.lower()}{self.__study.project_suffix()}"
        project = center.add_project(project_label)
        study_info.add_ingest(
            IngestProjectMetadata(
                study_id=self.__study.study_id,
                project_id=project.id,
                project_label=project_label,
                datatype=datatype,
            )
        )

    def __add_retrospective(self, center: CenterGroup) -> None:
        """Adds retrospective projects for the study to the center.

        Args:
          center: the center group
        """
        labels = [
            f"retrospective-{datatype.lower()}" for datatype in self.__study.datatypes
        ]
        for label in labels:
            center.add_project(label)

    def __get_release_group(self) -> Optional[GroupAdaptor]:
        """Returns the release group for this study if it is published.
        Otherwise, returns None.

        Returns:
            the release group if study is published, otherwise None
        """
        if not self.__study.is_published():
            return None

        release_id = f"release-{self.__study.study_id}"
        assert release_id
        if not self.__release_group:
            group = self.__fw.get_group(
                group_label=self.__study.name + " Release", group_id=release_id
            )
            assert group
            self.__release_group = GroupAdaptor(group=group, proxy=self.__fw)
            self.__release_group.add_permissions(self.__admin_access)
        return self.__release_group

    def __get_master_project(self) -> Optional[ProjectAdaptor]:
        """Returns the FW consolidation project for this project if it is
        published. Otherwise, returns None.

        Returns:
            the consolidation project if published, otherwise None
        """
        if not self.__study.is_published():
            return None

        release_group = self.__get_release_group()
        assert release_group, "study is published"
        project = release_group.get_project(label="master-project")
        if project is not None:
            project.add_admin_users(self.__admin_access)
        return project


class DistributionMapper(StudyMapper):
    """Defines a mapping from a distribution study to FW containers."""

    def __init__(self, study: Study, proxy: FlywheelProxy) -> None:
        self.__study = study
        self.__fw = proxy

    def map_center_pipelines(
        self, center: CenterGroup, study_info: StudyMetadata
    ) -> None:
        """Adds distribution projects for the study to the group.

        Args:
          center: the center group
          study_info: the study metadata
        """
        for datatype in self.__study.datatypes:
            self.__add_distribution(
                center=center, study_info=study_info, datatype=datatype
            )

    def map_study_pipelines(self) -> None:
        """Maps the study to study level groups and projects.

        Not implemented for distribution groups.
        """
        study_group = StudyGroup.create(study=self.__study, proxy=self.__fw)
        for datatype in self.__study.datatypes:
            self.__add_ingest(study_group=study_group, datatype=datatype)

    def __add_distribution(
        self, *, center: CenterGroup, study_info: "StudyMetadata", datatype: str
    ) -> None:
        """Adds a distribution project to this center for the study.

        Args:
        center: the center group
        study_info: the study metadata
        datatype: the pipeline data type
        """
        project_label = (
            f"distribution-{datatype.lower()}" f"{self.__study.project_suffix()}"
        )
        project = center.add_project(project_label)
        study_info.add_distribution(
            DistributionProjectMetadata(
                study_id=self.__study.study_id,
                project_id=project.id,
                project_label=project_label,
                datatype=datatype,
            )
        )

    def __add_ingest(self, *, study_group: StudyGroup, datatype: str) -> None:
        """Adds an ingest project for the datatype to the study group.

        Args:
          study_group: the group for the study
          datatype: the datatype
        """
        project_label = f"ingest-{datatype.lower()}"
        study_group.add_project(project_label)


class StudyMappingVisitor(StudyVisitor):
    def __init__(
        self, flywheel_proxy: FlywheelProxy, admin_access: List[AccessPermission]
    ) -> None:
        self.__admin_access = admin_access
        self.__fw = flywheel_proxy
        self.__study: Optional[Study] = None
        self.__mapper: Optional[StudyMapper] = None

    def visit_study(self, study: Study) -> None:
        """Creates FW containers for the study.

        Args:
          study: the study definition
        """
        if not study.centers:
            log.warning(
                "Not creating center groups for project %s: no centers given",
                study.name,
            )
            return

        self.__study = study
        if study.mode == "aggregation":
            self.__mapper = AggregationMapper(
                proxy=self.__fw,
                admin_access=self.__admin_access,
                study=study,
                pipelines=["ingest", "sandbox"],
            )
        if study.mode == "distribution":
            self.__mapper = DistributionMapper(study=study, proxy=self.__fw)

        for center_id in study.centers:
            self.visit_center(center_id)

        assert self.__mapper
        self.__mapper.map_study_pipelines()

    def visit_center(self, center_id: str) -> None:
        """Creates projects within the center for the study.

        Args:
          center_id: the ID of the center
        """
        assert self.__study, "study must be set"
        assert self.__mapper, "mapper must be set"

        group_adaptor = self.__fw.find_group(center_id)
        if not group_adaptor:
            log.warning("No group found with center ID %s", center_id)
            return

        try:
            center = CenterGroup.create_from_group_adaptor(adaptor=group_adaptor)
        except CenterError as error:
            log.warning("Unable to create center group: %s", str(error))
            return

        portal_info = center.get_project_info()
        study_info = portal_info.get(self.__study)

        self.__mapper.map_center_pipelines(center=center, study_info=study_info)

        center.update_project_info(portal_info)

    def visit_datatype(self, datatype: str) -> None:
        """Not implemented."""
