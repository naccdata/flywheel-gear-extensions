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
    PageProjectMetadata,
    ProjectMetadata,
)
from flywheel.models.access_permission import AccessPermission
from flywheel_adaptor.flywheel_proxy import (
    FlywheelProxy,
    GroupAdaptor,
    ProjectAdaptor,
)
from keys.types import DatatypeNameType
from projects.hierarchy_seeder import ResourceHierarchySeeder
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

    @abstractmethod
    def map_center_pipelines(
        self, center: CenterGroup, study_info: CenterStudyMetadata, pipeline_adcid: int
    ) -> None:
        """Maps the study to pipelines within a center.

        Note: Dashboards and pages are handled by the StudyMappingVisitor to avoid
        duplication in mixed-mode studies. Subclasses should implement mode-specific
        project creation.

        Args:
          center: the center group
          study_info: the metadata object to track center projects
          pipeline_adcid: the ADCID for ingest pipelines
        """

    @abstractmethod
    def map_study_pipelines(self) -> None:
        """Maps the study to study level groups and projects."""

    def _project_label(self, label: str) -> str:
        """Creates a project label with the study suffix.

        Args:
            label: the base label for the project
        Returns:
            the project label with study suffix
        """
        return f"{label}{self.study.project_suffix()}"

    def accepted_label(self) -> str:
        return self._project_label("accepted")

    def dashboard_label(self, dashboard_name: str) -> str:
        return self._project_label(f"dashboard-{dashboard_name}")

    def page_label(self, page_name: str) -> str:
        """Creates the label for a page project.

        Args:
            page_name: the name of the page
        Returns:
            the project label for the page
        """
        return self._project_label(f"page-{page_name}")

    def pipeline_label(self, pipeline: str, datatype: DatatypeNameType) -> str:
        return self._project_label(f"{pipeline}-{datatype.lower()}")

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

    def __add_page(
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        page_name: str,
    ) -> None:
        """Adds a page project to the center group.

        Args:
            center: the center group
            study_info: the metadata object to track center projects
            page_name: the name of the page
        """

        def update_page(project: ProjectAdaptor) -> None:
            study_info.add_page(
                PageProjectMetadata(
                    study_id=self.study.study_id,
                    project_id=project.id,
                    project_label=project.label,
                    page_name=page_name,
                )
            )

        self.add_pipeline(
            center=center,
            pipeline_label=self.page_label(page_name),
            update_study=update_page,
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
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        pipeline_adcid: int,
        datatypes: Optional[List[str]] = None,
    ) -> None:
        """Creates accepted, ingest and retrospective projects in the group.
        Updates the study metadata.

        Args:
          center: the center group
          study_info: the study metadata
          pipeline_adcid: the ADCID for ingest pipelines
          datatypes: list of datatype names to process (defaults to all
            aggregation datatypes)
        """
        # Use provided datatypes or default to all aggregation datatypes
        if datatypes is None:
            datatypes = [
                config.name
                for config in self.study.get_datatype_configs()
                if config.mode == "aggregation"
            ]

        self.__add_accepted(center=center, study_info=study_info)
        if center.is_active():
            for pipeline in self.__pipelines:
                for datatype_str in datatypes:
                    # Cast to DatatypeNameType for type safety
                    datatype: DatatypeNameType = datatype_str  # type: ignore[assignment]
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

        for datatype_str_retro in datatypes:
            # Cast to DatatypeNameType for type safety
            datatype_retro: DatatypeNameType = datatype_str_retro  # type: ignore[assignment]
            self.__add_retrospective(
                center=center,
                datatype=datatype_retro,
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
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        pipeline_adcid: int,
        datatypes: Optional[List[str]] = None,
    ) -> None:
        """Adds distribution projects for the study to the group.

        Args:
          center: the center group
          study_info: the study metadata
          pipeline_adcid: the ADCID for ingest pipelines
          datatypes: list of datatype names to process (defaults to all
            distribution datatypes)
        """
        # Use provided datatypes or default to all distribution datatypes
        if datatypes is None:
            datatypes = [
                config.name
                for config in self.study.get_datatype_configs()
                if config.mode == "distribution"
            ]

        for datatype_str in datatypes:
            # Cast to DatatypeNameType for type safety
            datatype: DatatypeNameType = datatype_str  # type: ignore[assignment]
            self.__add_distribution(
                center=center, study_info=study_info, datatype=datatype
            )

    def map_study_pipelines(self, datatypes: Optional[List[str]] = None) -> None:
        """Maps the study to study level groups and projects.

        Args:
          datatypes: list of datatype names to process (defaults to all
            distribution datatypes)
        """
        # Use provided datatypes or default to all distribution datatypes
        if datatypes is None:
            datatypes = [
                config.name
                for config in self.study.get_datatype_configs()
                if config.mode == "distribution"
            ]

        study_group = StudyGroup.create(study=self.study, proxy=self.proxy)
        for datatype in datatypes:
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
        self,
        flywheel_proxy: FlywheelProxy,
        admin_permissions: List[AccessPermission],
        hierarchy_seeder: Optional[ResourceHierarchySeeder] = None,
    ) -> None:
        """Initialize the StudyMappingVisitor.

        Args:
            flywheel_proxy: The proxy for the Flywheel instance.
            admin_permissions: The admin access permissions.
            hierarchy_seeder: Optional ResourceHierarchySeeder instance for
                seeding resource parent relationships in the Authorization
                Service. When None, hierarchy seeding is skipped.
        """
        self.__admin_permissions = admin_permissions
        self.__fw = flywheel_proxy
        self.__hierarchy_seeder = hierarchy_seeder
        self.__study: Optional[StudyModel] = None
        self.__aggregation_mapper: Optional[AggregationMapper] = None
        self.__distribution_mapper: Optional[DistributionMapper] = None
        self.__aggregation_datatypes: List[str] = []
        self.__distribution_datatypes: List[str] = []

    def __should_skip_aggregation(self, center_model: StudyCenterModel) -> bool:
        """Check if aggregation should be skipped for this center.

        Aggregation is skipped for co-enrolled centers in affiliated studies.

        Args:
            center_model: the center study model

        Returns:
            True if aggregation should be skipped.
        """
        assert self.__study, "study must be set"
        return (
            self.__study.study_type == "affiliated"
            and center_model.enrollment_pattern == "co-enrollment"
        )

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

        # Group datatypes by mode for mixed-mode support
        aggregation_datatypes = study.get_datatypes_by_mode("aggregation")
        distribution_datatypes = study.get_datatypes_by_mode("distribution")

        # Create mappers based on which modes are present
        aggregation_mapper: Optional[AggregationMapper] = None
        distribution_mapper: Optional[DistributionMapper] = None

        if aggregation_datatypes:
            aggregation_mapper = AggregationMapper(
                proxy=self.__fw,
                admin_access=self.__admin_permissions,
                study=study,
                pipelines=["ingest", "sandbox"],
            )

        if distribution_datatypes:
            distribution_mapper = DistributionMapper(study=study, proxy=self.__fw)

        # Store mappers for use in visit_center
        self.__aggregation_mapper = aggregation_mapper
        self.__distribution_mapper = distribution_mapper
        self.__aggregation_datatypes = aggregation_datatypes
        self.__distribution_datatypes = distribution_datatypes

        for center in study.centers:
            self.visit_center(center)

        # Seed hierarchy for study-scoped and community-scoped resources
        if self.__hierarchy_seeder is not None:
            self.__seed_study_dashboards_and_pages(study)

            community_pages = study.get_pages_by_level("community")
            for page_name in community_pages:
                page_label = self.__project_label(f"page-{page_name}")
                self.__hierarchy_seeder.seed_community_page(
                    resource_id=page_label,
                )

        # Map study-level pipelines for each mapper
        if aggregation_mapper:
            aggregation_mapper.map_study_pipelines()
        if distribution_mapper:
            distribution_mapper.map_study_pipelines(datatypes=distribution_datatypes)

    def visit_center(self, center_model: StudyCenterModel) -> None:
        """Creates projects within the center for the study.

        Args:
          center: the center study model
        """
        assert self.__study, "study must be set"

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

        # Handle dashboards and pages (common to both mappers)
        self.__handle_dashboards_and_pages(center=center, study_info=study_info)

        # Skip aggregation for co-enrolled affiliated studies
        if self.__aggregation_mapper and not self.__should_skip_aggregation(
            center_model
        ):
            self.__aggregation_mapper.map_center_pipelines(
                center=center,
                study_info=study_info,
                pipeline_adcid=pipeline_adcid,
                datatypes=self.__aggregation_datatypes,
            )

        # Call distribution mapper if we have distribution datatypes
        if self.__distribution_mapper:
            self.__distribution_mapper.map_center_pipelines(
                center=center,
                study_info=study_info,
                pipeline_adcid=pipeline_adcid,
                datatypes=self.__distribution_datatypes,
            )

        # Seed hierarchy for center-scoped data pipelines
        if self.__hierarchy_seeder is not None:
            self.__seed_center_pipelines(center_model=center_model)

        center.update_project_info(portal_info)

    def __seed_center_pipelines(self, center_model: StudyCenterModel) -> None:
        """Seed hierarchy for center-scoped data pipelines.

        Calls seed_center_pipeline for each pipeline project label that was
        created by the aggregation and distribution mappers.

        Args:
            center_model: the center study model with center_id
        """
        assert self.__study, "study must be set"
        assert self.__hierarchy_seeder is not None

        study_id = self.__study.study_id
        center_id = center_model.center_id

        # Seed aggregation pipelines (accepted + ingest/sandbox per datatype)
        # Only if aggregation mapper ran (not skipped for co-enrolled affiliated)
        if self.__aggregation_mapper and not self.__should_skip_aggregation(
            center_model
        ):
            # accepted project
            accepted_label = self.__project_label("accepted")
            self.__hierarchy_seeder.seed_center_pipeline(
                resource_id=accepted_label,
                study_id=study_id,
                center_id=center_id,
            )

            # ingest and sandbox pipelines for each aggregation datatype
            for pipeline in ["ingest", "sandbox"]:
                for datatype in self.__aggregation_datatypes:
                    pipeline_label = self.__project_label(
                        f"{pipeline}-{datatype.lower()}"
                    )
                    self.__hierarchy_seeder.seed_center_pipeline(
                        resource_id=pipeline_label,
                        study_id=study_id,
                        center_id=center_id,
                    )

            # retrospective pipelines (if study has legacy)
            if self.__study.has_legacy():
                for datatype in self.__aggregation_datatypes:
                    retro_label = self.__project_label(
                        f"retrospective-{datatype.lower()}"
                    )
                    self.__hierarchy_seeder.seed_center_pipeline(
                        resource_id=retro_label,
                        study_id=study_id,
                        center_id=center_id,
                    )

        # Seed distribution pipelines
        if self.__distribution_mapper:
            for datatype in self.__distribution_datatypes:
                dist_label = self.__project_label(f"distribution-{datatype.lower()}")
                self.__hierarchy_seeder.seed_center_pipeline(
                    resource_id=dist_label,
                    study_id=study_id,
                    center_id=center_id,
                )

    def __seed_study_dashboards_and_pages(self, study: StudyModel) -> None:
        """Seed hierarchy for study-scoped dashboards and pages.

        Calls seed_study_dashboard for each study-level dashboard and
        seed_study_page for each study-level page.

        Args:
            study: the study model
        """
        assert self.__hierarchy_seeder is not None

        study_id = study.study_id

        # Seed study-level dashboards
        study_dashboards = study.get_dashboards_by_level("study")
        for dashboard_name in study_dashboards:
            dashboard_label = self.__project_label(f"dashboard-{dashboard_name}")
            self.__hierarchy_seeder.seed_study_dashboard(
                resource_id=dashboard_label,
                study_id=study_id,
            )

        # Seed study-level pages
        study_pages = study.get_pages_by_level("study")
        for page_name in study_pages:
            page_label = self.__project_label(f"page-{page_name}")
            self.__hierarchy_seeder.seed_study_page(
                resource_id=page_label,
                study_id=study_id,
            )

    def __handle_dashboards_and_pages(
        self, center: CenterGroup, study_info: CenterStudyMetadata
    ) -> None:
        """Handle dashboard and page creation for the study.

        This method creates dashboards and pages at the appropriate level.
        Currently only center-level dashboards are implemented.
        Study-level dashboards are handled by separate logic (not in this method).

        Args:
            center: the center group
            study_info: the study metadata
        """
        assert self.__study, "study must be set"

        if not center.is_active():
            return

        # Handle dashboards by level
        # Note: Only center-level dashboards are created here.
        # Study-level dashboards are handled elsewhere in the system.
        if self.__study.dashboards:
            center_dashboards = self.__study.get_dashboards_by_level("center")

            # Create center-level dashboards
            for dashboard_name in center_dashboards:
                self.__add_dashboard(
                    center=center, study_info=study_info, dashboard_name=dashboard_name
                )
                if self.__hierarchy_seeder is not None:
                    dashboard_label = self.__project_label(
                        f"dashboard-{dashboard_name}"
                    )
                    self.__hierarchy_seeder.seed_center_dashboard(
                        resource_id=dashboard_label,
                        study_id=self.__study.study_id,
                        center_id=center.id,
                    )

        # Handle pages by level
        # Note: Only center-level pages are created here.
        # Study-level pages are handled elsewhere in the system.
        if self.__study.pages:
            center_pages = self.__study.get_pages_by_level("center")

            # Create center-level pages
            for page_name in center_pages:
                self.__add_page(
                    center=center, study_info=study_info, page_name=page_name
                )
                if self.__hierarchy_seeder is not None:
                    page_label = self.__project_label(f"page-{page_name}")
                    self.__hierarchy_seeder.seed_center_page(
                        resource_id=page_label,
                        study_id=self.__study.study_id,
                        center_id=center.id,
                    )

    def __add_dashboard(
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        dashboard_name: str,
    ) -> None:
        """Adds a dashboard project to the center group.

        Args:
            center: the center group
            study_info: the study metadata
            dashboard_name: the name of the dashboard
        """
        assert self.__study, "study must be set"

        def update_dashboard(project: ProjectAdaptor) -> None:
            assert self.__study, "study must be set"
            study_info.add_dashboard(
                DashboardProjectMetadata(
                    study_id=self.__study.study_id,
                    project_id=project.id,
                    project_label=project.label,
                    dashboard_name=dashboard_name,
                )
            )

        dashboard_label = self.__project_label(f"dashboard-{dashboard_name}")
        self.__add_pipeline(
            center=center,
            pipeline_label=dashboard_label,
            update_study=update_dashboard,
        )

    def __add_page(
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        page_name: str,
    ) -> None:
        """Adds a page project to the center group.

        Args:
            center: the center group
            study_info: the study metadata
            page_name: the name of the page
        """
        assert self.__study, "study must be set"

        def update_page(project: ProjectAdaptor) -> None:
            assert self.__study, "study must be set"
            study_info.add_page(
                PageProjectMetadata(
                    study_id=self.__study.study_id,
                    project_id=project.id,
                    project_label=project.label,
                    page_name=page_name,
                )
            )

        page_label = self.__project_label(f"page-{page_name}")
        self.__add_pipeline(
            center=center,
            pipeline_label=page_label,
            update_study=update_page,
        )

    def __add_pipeline(
        self,
        center: CenterGroup,
        pipeline_label: str,
        update_study: Callable[[ProjectAdaptor], None],
    ) -> None:
        """Adds a pipeline project with the label to the group.

        Calls the update function if the project is successfully created.
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

    def __project_label(self, label: str) -> str:
        """Creates a project label with the study suffix.

        Args:
            label: the base label for the project
        Returns:
            the project label with study suffix
        """
        assert self.__study, "study must be set"
        if self.__study.is_primary():
            return label
        return f"{label}-{self.__study.study_id}"

    def visit_datatype(self, datatype: str) -> None:
        """Not implemented."""
