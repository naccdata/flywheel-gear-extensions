"""Visitor that collects REDCap project PIDs from center metadata."""

from centers.center_group import (
    AbstractCenterMetadataVisitor,
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


class REDCapDisableVisitor(AbstractCenterMetadataVisitor):
    """Visitor that collects REDCap project PIDs from center metadata.

    Walks the center metadata tree to find all REDCap projects
    associated with form ingest projects. Collected PIDs can be used to
    look up REDCapProject instances for role unassignment.
    """

    def __init__(self) -> None:
        self.__pids: list[int] = []

    @property
    def redcap_pids(self) -> list[int]:
        """Returns the list of REDCap project PIDs found."""
        return self.__pids

    def visit_center(self, center: CenterMetadata) -> None:
        """Iterate over studies in the center metadata."""
        for study in center.studies.values():
            study.apply(self)

    def visit_study(self, study: CenterStudyMetadata) -> None:
        """Iterate over ingest projects in the study."""
        for project in study.ingest_projects.values():
            project.apply(self)

    def visit_form_ingest_project(self, project: FormIngestProjectMetadata) -> None:
        """Collect redcap_pid from each REDCapFormProjectMetadata."""
        for redcap_project in project.redcap_projects.values():
            self.__pids.append(redcap_project.redcap_pid)

    def visit_project(self, project: ProjectMetadata) -> None:
        """No-op for generic projects."""

    def visit_ingest_project(self, project: IngestProjectMetadata) -> None:
        """No-op for non-form ingest projects."""

    def visit_redcap_form_project(self, project: REDCapFormProjectMetadata) -> None:
        """No-op — PIDs are collected in visit_form_ingest_project."""

    def visit_distribution_project(self, project: DistributionProjectMetadata) -> None:
        """No-op for distribution projects."""

    def visit_dashboard_project(self, project: DashboardProjectMetadata) -> None:
        """No-op for dashboard projects."""

    def visit_page_project(self, project: PageProjectMetadata) -> None:
        """No-op for page projects."""
