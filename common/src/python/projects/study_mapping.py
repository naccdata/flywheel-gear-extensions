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
from typing import Callable, List, Optional

from centers.center_group import (
    CenterError,
    CenterGroup,
    CenterStudyMetadata,
    DashboardProjectMetadata,
    DistributionProjectMetadata,
    IngestProjectMetadata,
    ProjectMetadata,
)
from flywheel.models.access_permission import AccessPermission
from flywheel_adaptor.flywheel_proxy import (
    FlywheelProxy,
    GroupAdaptor,
    ProjectAdaptor,
)
from keys.types import DatatypeNameType

from projects.study import StudyCenterModel, StudyModel, StudyVisitor
from projects.study_group import StudyGroup

log = logging.getLogger(__name__)


class StudyMapper(ABC):
    """Defines the interface for classes that map study objects to FW
    containers."""

    def __init__(self, *, study: StudyModel, proxy: FlywheelProxy) -> None:
        self.__study = study
        self.__proxy = proxy

    @property
    def study(self):
        return self.__study

    @property
    def proxy(self):
        return self.__proxy

    def map_center_pipelines(
        self, center: CenterGroup, study_info: CenterStudyMetadata, pipeline_adcid: int
    ) -> None:
        """Maps the study to pipelines within a center.

        Args:
          center: the center group
          study_info: the metadata object to track center projects
        """
        if (
            center.is_active()
            and self.study.dashboards is not None
            and self.study.dashboards
        ):
            for dashboard_name in self.study.dashboards:
                self.__add_dashboard(
                    center=center, study_info=study_info, dashboard_name=dashboard_name
                )

    @abstractmethod
    def map_study_pipelines(self) -> None:
        """Maps the study to study level groups and projects."""

    def accepted_label(self) -> str:
        return f"accepted{self.study.project_suffix()}"

    def dashboard_label(self, dashboard_name: str) -> str:
        return f"dashboard-{dashboard_name}{self.study.project_suffix()}"

    def pipeline_label(self, pipeline: str, datatype: DatatypeNameType) -> str:
        return f"{pipeline}-{datatype.lower()}{self.study.project_suffix()}"

    def __add_dashboard(
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        dashboard_name: str,
    ) -> None:
        """Adds a dashboard project to the center group."""

        def update_dashboard(project: ProjectAdaptor) -> None:
            study_info.add_dashboard(
                DashboardProjectMetadata(
                    study_id=self.study.study_id,
                    project_id=project.id,
                    project_label=project.label,
                    dashboard_name=dashboard_name,
                )
            )

        self.add_pipeline(
            center=center,
            pipeline_label=self.dashboard_label(dashboard_name),
            update_study=update_dashboard,
        )

    def add_pipeline(
        self,
        center: CenterGroup,
        pipeline_label: str,
        update_study: Callable[[ProjectAdaptor], None],
    ) -> None:
        """Adds a pipeline project with the label the group. Calls the update
        function if the project is successfully created.

        Logs an error if the project could not be created.

        Args:
          center: the center group
          pipeline_label: the label for the project
          update_study: function called post-creation
        """
        project = center.add_project(pipeline_label)
        if not project:
            log.error("Failed to create pipeline %s/%s", center.id, pipeline_label)
            return

        update_study(project)


class AggregationMapper(StudyMapper):
    """Defines the mapping of an aggregation study to center and study level
    pipelines.

    Creates groups at the study level if needed.
    """

    def __init__(
        self,
        *,
        study: StudyModel,
        pipelines: List[str],
        proxy: FlywheelProxy,
        admin_access: List[AccessPermission],
    ) -> None:
        super().__init__(study=study, proxy=proxy)
        self.__pipelines = pipelines
        self.__admin_access = admin_access
        self.__release_group: Optional[GroupAdaptor] = None

    def map_center_pipelines(
        self, center: CenterGroup, study_info: CenterStudyMetadata, pipeline_adcid: int
    ) -> None:
        """Creates accepted, ingest and retrospective projects in the group.
        Updates the study metadata.

        Args:
          center: the center group
          study_info: the study metadata
          pipeline_adcid: the ADCID for ingest pipelines
        """

        super().map_center_pipelines(
            center=center, study_info=study_info, pipeline_adcid=pipeline_adcid
        )
        self.__add_accepted(center=center, study_info=study_info)
        if center.is_active():
            for pipeline in self.__pipelines:
                for datatype in self.study.datatypes:
                    self.__add_ingest(
                        center=center,
                        study_info=study_info,
                        pipeline=pipeline,
                        datatype=datatype,
                        pipeline_adcid=pipeline_adcid,
                    )

        if not self.study.has_legacy():
            log.warning(
                "Will not create retrospective projects for study %s", self.study.name
            )
            return

        for datatype in self.study.datatypes:
            self.__add_retrospective(
                center=center,
                datatype=datatype,
                study_info=study_info,
                pipeline_adcid=pipeline_adcid,
            )

    def map_study_pipelines(self) -> None:
        """Creates study group with release project."""
        if not self.study.is_published():
            log.info("Study %s has no release project", self.study.name)
            return

        self.__get_release_group()
        self.__get_master_project()

    def __add_accepted(
        self, *, center: CenterGroup, study_info: CenterStudyMetadata
    ) -> None:
        """Creates an accepted project in the center group, and updates the
        study metadata.

        Args:
          center: the center group
          study_info: the study metadata
        """

        def update_accepted(accepted_project: ProjectAdaptor) -> None:
            study_info.add_accepted(
                ProjectMetadata(
                    study_id=self.study.study_id,
                    project_id=accepted_project.id,
                    project_label=accepted_project.label,
                )
            )

        self.add_pipeline(
            center=center,
            pipeline_label=self.accepted_label(),
            update_study=update_accepted,
        )

    def __add_ingest(
        self,
        *,
        center: CenterGroup,
        pipeline: str,
        datatype: DatatypeNameType,
        study_info: CenterStudyMetadata,
        pipeline_adcid: int,
    ) -> None:
        """Adds an ingest projects for the study datatype to the center.

        Args:
          center: the center group
          study_info: the center study metadata
          pipeline: the name of the pipeline
          datatype: the name of the datatype
          pipeline_adcid: ADCID for the pipeline
        """
        pipeline_label = self.pipeline_label(pipeline, datatype)

        def update_ingest(project: ProjectAdaptor) -> None:
            study_info.add_ingest(
                IngestProjectMetadata(
                    study_id=self.study.study_id,
                    pipeline_adcid=pipeline_adcid,
                    project_id=project.id,
                    project_label=project.label,
                    datatype=datatype,
                )
            )
            project.update_info({"pipeline_adcid": pipeline_adcid})

        self.add_pipeline(
            center=center,
            pipeline_label=pipeline_label,
            update_study=update_ingest,
        )

    def __add_retrospective(
        self,
        center: CenterGroup,
        datatype: DatatypeNameType,
        study_info: CenterStudyMetadata,
        pipeline_adcid: int,
    ) -> None:
        """Adds retrospective projects for the study to the center.

        Args:
          center: the center group
          datatype: the name of the datatype
          study_info: the center study metadata
          pipeline_adcid: ADCID for the pipeline
        """

        def update_retrospective(project: ProjectAdaptor):
            if datatype == "form":
                study_info.add_ingest(
                    IngestProjectMetadata(
                        study_id=self.study.study_id,
                        pipeline_adcid=pipeline_adcid,
                        project_id=project.id,
                        project_label=project.label,
                        datatype=datatype,
                    )
                )
            project.update_info({"pipeline_adcid": pipeline_adcid})

        self.add_pipeline(
            center=center,
            pipeline_label=self.pipeline_label(
                pipeline="retrospective", datatype=datatype
            ),
            update_study=update_retrospective,
        )

    def __get_release_group(self) -> Optional[GroupAdaptor]:
        """Returns the release group for this study if it is published.
        Otherwise, returns None.

        Returns:
            the release group if study is published, otherwise None
        """
        if not self.study.is_published():
            return None

        release_id = f"release-{self.study.study_id}"
        assert release_id
        if not self.__release_group:
            group = self.proxy.get_group(
                group_label=self.study.name + " Release", group_id=release_id
            )
            assert group
            self.__release_group = GroupAdaptor(group=group, proxy=self.proxy)
            self.__release_group.add_permissions(self.__admin_access)
        return self.__release_group

    def __get_master_project(self) -> Optional[ProjectAdaptor]:
        """Returns the FW consolidation project for this project if it is
        published. Otherwise, returns None.

        Returns:
            the consolidation project if published, otherwise None
        """
        if not self.study.is_published():
            return None

        release_group = self.__get_release_group()
        assert release_group, "study is published"
        project = release_group.get_project(label="master-project")
        if project is not None:
            project.add_admin_users(self.__admin_access)
        return project


class StudyMappingError(Exception):
    """Exception class for errors during study mapping."""


class DistributionMapper(StudyMapper):
    """Defines a mapping from a distribution study to FW containers."""

    def __init__(self, study: StudyModel, proxy: FlywheelProxy) -> None:
        super().__init__(study=study, proxy=proxy)

    def map_center_pipelines(
        self, center: CenterGroup, study_info: CenterStudyMetadata, pipeline_adcid: int
    ) -> None:
        """Adds distribution projects for the study to the group.

        Args:
          center: the center group
          study_info: the study metadata
        """
        super().map_center_pipelines(
            center=center, study_info=study_info, pipeline_adcid=pipeline_adcid
        )

        for datatype in self.study.datatypes:
            self.__add_distribution(
                center=center, study_info=study_info, datatype=datatype
            )

    def map_study_pipelines(self) -> None:
        """Maps the study to study level groups and projects.

        Not implemented for distribution groups.
        """
        study_group = StudyGroup.create(study=self.study, proxy=self.proxy)
        for datatype in self.study.datatypes:
            self.__add_ingest(study_group=study_group, datatype=datatype)

    def __add_distribution(
        self,
        *,
        center: CenterGroup,
        study_info: "CenterStudyMetadata",
        datatype: DatatypeNameType,
    ) -> None:
        """Adds a distribution project to this center for the study.

        Args:
        center: the center group
        study_info: the study metadata
        datatype: the pipeline data type
        """

        def update_distribution(project: ProjectAdaptor) -> None:
            study_info.add_distribution(
                DistributionProjectMetadata(
                    study_id=self.study.study_id,
                    project_id=project.id,
                    project_label=project.label,
                    datatype=datatype,
                )
            )

        self.add_pipeline(
            center=center,
            pipeline_label=self.pipeline_label(
                pipeline="distribution", datatype=datatype
            ),
            update_study=update_distribution,
        )

    def __add_ingest(self, *, study_group: StudyGroup, datatype: str) -> None:
        """Adds an ingest project for the datatype to the study group.

        Args:
          study_group: the group for the study
          datatype: the datatype
        """
        project_label = f"ingest-{datatype.lower()}"
        project = study_group.add_project(project_label)
        if not project:
            log.error("Failed to create project %s/%s", study_group.id, project_label)


class StudyMappingVisitor(StudyVisitor):
    def __init__(
        self, flywheel_proxy: FlywheelProxy, admin_permissions: List[AccessPermission]
    ) -> None:
        self.__admin_permissions = admin_permissions
        self.__fw = flywheel_proxy
        self.__study: Optional[StudyModel] = None
        self.__mapper: Optional[StudyMapper] = None

    def visit_study(self, study: StudyModel) -> None:
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
                admin_access=self.__admin_permissions,
                study=study,
                pipelines=["ingest", "sandbox"],
            )
        if study.mode == "distribution":
            self.__mapper = DistributionMapper(study=study, proxy=self.__fw)

        for center in study.centers:
            self.visit_center(center)

        assert self.__mapper
        self.__mapper.map_study_pipelines()

    def visit_center(self, center_model: StudyCenterModel) -> None:
        """Creates projects within the center for the study.

        Args:
          center: the center study model
        """
        assert self.__study, "study must be set"
        assert self.__mapper, "mapper must be set"

        if (
            self.__study.mode == "aggregation"
            and self.__study.study_type == "affiliated"
            and center_model.enrollment_pattern == "co-enrollment"
        ):
            return

        group_adaptor = self.__fw.find_group(center_model.center_id)
        if not group_adaptor:
            log.warning("No group found with center ID %s", center_model.center_id)
            return

        try:
            center = CenterGroup.create_from_group_adaptor(adaptor=group_adaptor)
        except CenterError as error:
            log.warning("Unable to create center group: %s", str(error))
            return

        pipeline_adcid = (
            center_model.pipeline_adcid
            if center_model.pipeline_adcid is not None
            else center.adcid
        )

        portal_info = center.get_project_info()
        study_info = portal_info.get(self.__study.study_id)
        if study_info is None:
            study_info = CenterStudyMetadata(
                study_id=self.__study.study_id, study_name=self.__study.name
            )
            portal_info.add(study_info)

        self.__mapper.map_center_pipelines(
            center=center, study_info=study_info, pipeline_adcid=pipeline_adcid
        )

        center.update_project_info(portal_info)

    def visit_datatype(self, datatype: str) -> None:
        """Not implemented."""
