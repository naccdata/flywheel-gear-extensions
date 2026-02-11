"""Module for working with a Group representing a center.

Should be used when starting from centers already created using
`projects.CenterMappingAdaptor`.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, overload

import flywheel
from flywheel.models.group import Group
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor, ProjectAdaptor
from keys.keys import DefaultValues
from keys.types import DatatypeNameType, PipelineStageType
from pipeline.pipeline_label import PipelineLabel
from projects.template_project import TemplateProject
from pydantic import AliasGenerator, BaseModel, ConfigDict, RootModel, ValidationError
from redcap_api.redcap_repository import REDCapParametersRepository, REDCapProject
from serialization.case import kebab_case
from users.authorizations import Activity

from centers.center_adaptor import CenterAdaptor
from centers.center_info import CenterInfo

log = logging.getLogger(__name__)


class CenterGroup(CenterAdaptor):
    """Defines an adaptor for a group representing a center."""

    def __init__(
        self, *, adcid: int, active: bool, group: flywheel.Group, proxy: FlywheelProxy
    ) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__datatypes: List[str] = []
        self.__ingest_stages: List[PipelineStageType] = [
            "ingest",
            "retrospective",
            "sandbox",
            "distribution",
        ]
        self.__adcid = adcid
        self.__is_active = active
        self.__center_portal: Optional[ProjectAdaptor] = None
        self.__redcap_param_repo: Optional[REDCapParametersRepository] = None

    @classmethod
    def create_from_group(cls, *, proxy: FlywheelProxy, group: Group) -> "CenterGroup":
        """Creates a CenterGroup from either a center or an existing group.

        Args:
          group: an existing group
          proxy: the flywheel proxy object
        Returns:
          the CenterGroup for created group
        """
        project = proxy.get_project(group=group, project_label="metadata")
        if not project:
            raise CenterError(f"Unable to create center from group {group.label}")

        metadata_project = ProjectAdaptor(project=project, proxy=proxy)
        metadata_info = metadata_project.get_info()
        if "adcid" not in metadata_info:
            raise CenterError(
                f"Expected group {group.label}/metadata.info to have ADCID"
            )

        adcid = metadata_info["adcid"]
        active = metadata_info.get("active", False)

        center_group = CenterGroup(adcid=adcid, active=active, group=group, proxy=proxy)
        metadata_project.add_admin_users(center_group.get_user_access())
        center_group.add_center_portal()

        return center_group

    @classmethod
    def create_from_group_adaptor(cls, *, adaptor: GroupAdaptor) -> "CenterGroup":
        """Creates a CenterGroup from a GroupAdaptor.

        Args:
          adaptor: the group adaptor

        Returns:
          the CenterGroup for the group
        """
        # pylint: disable=protected-access
        return CenterGroup.create_from_group(proxy=adaptor.proxy(), group=adaptor.group)

    @classmethod
    def create_from_center(
        cls,
        *,
        proxy: FlywheelProxy,
        center: CenterInfo,
        tags: Optional[List[str]] = None,
    ) -> "CenterGroup":
        """Creates a CenterGroup from a center object.

        Args:
          center: CenterInfo object, the study center
          proxy: The flywheel proxy object
          tags: Tags to add, if specified
        Returns:
          the CenterGroup for the center
        """
        if center.group is None:
            raise CenterError(f"Center info is not a group: {center.name}")

        group = proxy.get_group(group_label=center.name, group_id=center.group)
        assert group, "No group for center"

        center_group = CenterGroup(
            adcid=center.adcid,
            active=center.active,  # type: ignore
            group=group,
            proxy=proxy,
        )

        # handle tags
        if tags is None:
            tags = []

        adcid_tag = f"adcid-{center.adcid}"
        if adcid_tag not in tags:
            tags.append(adcid_tag)
        center_group.add_tags(tags)

        metadata_project = center_group.get_metadata()
        assert metadata_project, "expecting metadata project"
        metadata_project.add_admin_users(center_group.get_user_access())
        metadata_project.update_info({"adcid": center.adcid, "active": center.active})

        center_group.add_center_portal()
        return center_group

    @classmethod
    def get_center_group(cls, *, adaptor: GroupAdaptor) -> "CenterGroup":
        """Returns the CenterGroup for an existing Flywheel Group.

        Args:
            adaptor: Flywheel group adaptor

        Returns:
            the CenterGroup for the center

        Raises:
            CenterError: if center metadata missing or incomplete
        """
        group = adaptor.group
        proxy = adaptor.proxy()
        meta_project = group.projects.find_first("label=metadata")
        if not meta_project:
            raise CenterError(
                f"Unable to find metadata project for group {group.label}"
            )

        meta_project = meta_project.reload()
        metadata_info = meta_project.info
        if "adcid" not in metadata_info:
            raise CenterError(
                f"Expected group {group.label}/metadata.info to have ADCID"
            )

        adcid = metadata_info["adcid"]
        active = metadata_info.get("active", False)

        center_group = CenterGroup(adcid=adcid, active=active, group=group, proxy=proxy)
        center_group.add_center_portal()

        return center_group

    @property
    def adcid(self) -> int:
        """The ADCID of this center."""
        return self.__adcid

    def is_active(self) -> bool:
        """Indicates whether the center is active."""
        return self.__is_active

    @overload
    def get_matching_projects(self, *, prefix: str) -> List[ProjectAdaptor]:
        """Returns the projects for the center with labels that match the
        prefix.

        Args:
          prefix: the prefix to match

        Returns:
          the list of matching projects for the group
        """
        ...

    @overload
    def get_matching_projects(self, *, pattern: str) -> List[ProjectAdaptor]:
        """Returns the projects for the center with labels that match the full
        pattern.

        Args:
          pattern: the pattern to match

        Returns:
          the list of matching projects for the group
        """
        ...

    def get_matching_projects(
        self, *, prefix: Optional[str] = None, pattern: Optional[str] = None
    ) -> List[ProjectAdaptor]:
        """Returns the projects for the center with labels that match whichever
        of the prefix or pattern that is set.

        Args:
          prefix: the project name prefix to match
          pattern: the project name pattern to match
        Returns:
          the list of matching projects for the group
        Raises:
          TypeError if both arguments are None
        """
        if prefix is None and pattern is None:
            raise TypeError("Pattern must not be null")

        if prefix is not None:
            if pattern is not None:
                raise TypeError("Only one pattern argument may be set")
            project_pattern = re.compile(rf"^{prefix}")

        if pattern is not None:
            project_pattern = re.compile(rf"^{pattern}$")

        return [
            ProjectAdaptor(project=project, proxy=self.proxy())
            for project in self.projects()
            if project_pattern.match(project.label)
        ]

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

        project_info = self.get_project_info()
        visitor = GatherIngestDatatypesVisitor()
        project_info.apply(visitor)
        self.__datatypes = visitor.datatypes

        return self.__datatypes

    def apply_template(self, template: TemplateProject) -> None:
        """Applies the template to projects of this center group that match.

        Args:
          template: the template project
        """
        prefix_pattern = template.get_pattern()
        if not prefix_pattern:
            return

        projects = self.get_matching_projects(prefix=prefix_pattern)
        for project in projects:
            pipeline_adcid = project.get_info().get("pipeline_adcid")
            adcid = pipeline_adcid if pipeline_adcid is not None else self.adcid

            template.copy_to(
                project,
                value_map={
                    "adrc": self.label,
                    "adcid": str(adcid),
                    "project_id": project.id,
                    "site": self.proxy().get_site(),
                },
            )

    def get_portal(self) -> ProjectAdaptor:
        """Returns the center-portal project.

        Returns:
          The center-portal project
        """
        if not self.__center_portal:
            self.__center_portal = self.get_project("center-portal")
            assert self.__center_portal, "expecting center-portal project"

        return self.__center_portal

    def add_center_portal(self) -> None:
        """Adds a center portal project to this group."""
        project = self.add_project("center-portal")
        if not project:
            log.error("Failed to create %s/center-portal", self.label)

    def add_redcap_project(self, redcap_project: "REDCapProjectInput") -> None:
        """Adds the REDCap project to the center group.

        Args:
          redcap_project: the REDCap project input
        """
        project_info = self.get_project_info()
        study_info = project_info.studies.get(redcap_project.study_id, None)
        if not study_info:
            log.warning(
                "no study info for study %s in center %s",
                redcap_project.study_id,
                self.label,
            )
            return

        ingest_project = study_info.get_ingest(redcap_project.project_label)
        if not ingest_project:
            log.warning(
                "no ingest project for study %s in center %s",
                redcap_project.study_id,
                self.label,
            )
            return

        if isinstance(ingest_project, FormIngestProjectMetadata):
            form_ingest_project = ingest_project  # get any existing redcap metadata
        else:
            form_ingest_project = FormIngestProjectMetadata.create_from_ingest(
                ingest_project
            )

        for form_project in redcap_project.projects:
            form_ingest_project.add(form_project)

        study_info.add_ingest(form_ingest_project)
        project_info.add(study_info)
        self.update_project_info(project_info)

    def get_project_info(self) -> "CenterMetadata":
        """Gets the portal info for this center.

        Returns:
          the center portal metadata object for the info of the portal project
        Raises:
            CenterError: if info in portal project is not in expected format
        """
        metadata_project = self.get_metadata()
        if not metadata_project:
            log.error("no metadata project for %s, cannot get info", self.label)
            raise CenterError(f"no metadata project for {self.label}")

        info = metadata_project.get_info()
        if not info:
            return CenterMetadata(adcid=self.adcid, active=self.__is_active, studies={})

        if "studies" not in info:
            return CenterMetadata(adcid=self.adcid, active=self.__is_active, studies={})

        try:
            return CenterMetadata.model_validate(info)
        except ValidationError as error:
            raise CenterError(
                f"Info in {self.label}/{metadata_project.label}"
                " does not match expected format"
            ) from error

    def update_project_info(self, project_info: "CenterMetadata") -> None:
        """Updates the portal info for this center.

        Args:
          portal_info: the center portal metadata object
        """
        metadata_project = self.get_metadata()
        if not metadata_project:
            log.error("no metadata project for %s, cannot update info", self.label)
            return

        metadata_project.update_info(
            project_info.model_dump(by_alias=True, exclude_none=True)
        )

    def add_project(self, label: str) -> Optional[ProjectAdaptor]:
        """Adds a project with the label to this group and returns the
        corresponding ProjectAdaptor.

        Args:
          label: the label for the project
        Returns:
          the ProjectAdaptor for the project
        """
        return self.get_project(label=label, info_update={"adcid": self.adcid})

    def get_redcap_project(self, pid: int) -> Optional[REDCapProject]:
        """Returns the REDCap project for the PID."""
        if self.__redcap_param_repo is None:
            return None

        return self.__redcap_param_repo.get_redcap_project(pid)

    def set_redcap_param_repo(self, redcap_param_repo: REDCapParametersRepository):
        self.__redcap_param_repo = redcap_param_repo


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


class AbstractCenterMetadataVisitor(ABC):
    @abstractmethod
    def visit_center(self, center: "CenterMetadata") -> None:
        pass

    @abstractmethod
    def visit_study(self, study: "CenterStudyMetadata") -> None:
        pass

    @abstractmethod
    def visit_project(self, project: "ProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_distribution_project(
        self, project: "DistributionProjectMetadata"
    ) -> None:
        pass

    @abstractmethod
    def visit_ingest_project(self, project: "IngestProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_redcap_form_project(self, project: "REDCapFormProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_form_ingest_project(self, project: "FormIngestProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_dashboard_project(self, project: "DashboardProjectMetadata") -> None:
        pass


class ProjectMetadata(BaseModel):
    """Metadata for a center project. Set datatype for ingest projects.

    Dump with by_alias and exclude_none set to True.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )

    study_id: str
    project_id: str
    project_label: str

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_project(self)


class DashboardProjectMetadata(ProjectMetadata):
    """Metadata for a dashboard project of a center."""

    dashboard_name: str

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_project(self)


class DistributionProjectMetadata(ProjectMetadata):
    """Metadata for a distribution project of a center."""

    datatype: str

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_distribution_project(self)


class IngestProjectMetadata(ProjectMetadata):
    """Metadata for an ingest project of a center."""

    pipeline_adcid: int
    datatype: str

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_ingest_project(self)


class REDCapFormProjectMetadata(BaseModel):
    """Metadata for a REDCap form project."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    redcap_pid: int
    label: str
    report_id: Optional[int] = None

    def is_enrollment(self) -> bool:
        return self.label.upper() == DefaultValues.ENROLLMENT_MODULE

    def get_submission_activity(self) -> Activity:
        datatype: DatatypeNameType = "enrollment" if self.is_enrollment() else "form"

        return Activity(datatype=datatype, action="submit-audit")

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_redcap_form_project(self)


class FormIngestProjectMetadata(IngestProjectMetadata):
    """Metadata for a form ingest project.

    This class represents the metadata for a form ingest project within
    a center. It inherits from the IngestProjectMetadata class and adds
    additional attributes specific to form ingest projects.
    """

    redcap_projects: Dict[str, REDCapFormProjectMetadata] = {}

    @classmethod
    def create_from_ingest(
        cls, ingest: IngestProjectMetadata
    ) -> "FormIngestProjectMetadata":
        """Creates a FormIngestProjectMetadata from an IngestProjectMetadata.

        Args:
            ingest: the ingest project metadata
        Returns:
            the FormIngestProjectMetadata for the ingest project
        """
        return FormIngestProjectMetadata(
            study_id=ingest.study_id,
            pipeline_adcid=ingest.pipeline_adcid,
            project_id=ingest.project_id,
            project_label=ingest.project_label,
            datatype=ingest.datatype,
        )

    def add(self, redcap_project: REDCapFormProjectMetadata) -> None:
        """Adds the REDCap project to the form ingest project metadata.

        Args:
            redcap_project: the REDCap project metadata
        """
        self.redcap_projects[redcap_project.label] = redcap_project

    def get(self, module_name: str) -> Optional[REDCapFormProjectMetadata]:
        """Gets the REDCap project metadata for the module name.

        Args:
            module_name: the module name
        Returns:
            the REDCap project metadata for the module name
        """
        return self.redcap_projects.get(module_name, None)

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_form_ingest_project(self)


class CenterStudyMetadata(BaseModel):
    """Metadata for study details within a participating center."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    study_id: str
    study_name: str
    ingest_projects: Dict[str, (IngestProjectMetadata | FormIngestProjectMetadata)] = {}
    accepted_project: Optional[ProjectMetadata] = None
    dashboard_projects: Optional[Dict[str, DashboardProjectMetadata]] = {}
    distribution_projects: Dict[str, DistributionProjectMetadata] = {}

    def add_accepted(self, project: ProjectMetadata) -> None:
        """Adds the accepted project to the study metadata.

        Args:
            project: the accepted project metadata
        """
        self.accepted_project = project

    def add_dashboard(self, project: DashboardProjectMetadata) -> None:
        """Adds the dashboard project to the study metadata.

        Args:
            project: the dashboard project metadata
        """
        self.dashboard_projects = (
            self.dashboard_projects if self.dashboard_projects is not None else {}
        )
        self.dashboard_projects[project.project_label] = project

    def add_ingest(self, project: IngestProjectMetadata) -> None:
        """Adds the ingest project to the study metadata.

        Args:
            project: the ingest project metadata
        """
        self.ingest_projects[project.project_label] = project

    def get_ingest(
        self, project_label: str
    ) -> Optional[IngestProjectMetadata | FormIngestProjectMetadata]:
        """Gets the ingest project metadata for the project label.

        Args:
            project_label: the project label
        Returns:
            the ingest project metadata for the project label
        """
        return self.ingest_projects.get(project_label, None)

    def add_distribution(self, project: DistributionProjectMetadata) -> None:
        """Adds the distribution project to the study metadata.

        Args:
          project: the distribution project metadata.
        """
        self.distribution_projects[project.project_label] = project

    def get_dashboard(self, project_label: str) -> Optional[DashboardProjectMetadata]:
        if self.dashboard_projects is None:
            return None

        return self.dashboard_projects.get(project_label, None)

    def get_distribution(
        self, project_label: str
    ) -> Optional[DistributionProjectMetadata]:
        """Gets the distribution project metadata for the project label.

        Args:
          project_label: the project label

        Returns:
          the distribution project metadata for the project label
        """
        return self.distribution_projects.get(project_label, None)

    def apply(self, visitor: "AbstractCenterMetadataVisitor") -> None:
        visitor.visit_study(self)


class CenterMetadata(BaseModel):
    """Metadata to be stored in center metadata project."""

    adcid: int
    active: bool
    studies: Dict[str, CenterStudyMetadata]

    def add(self, study: CenterStudyMetadata) -> None:
        """Adds study metadata to the studies.

        Args:
            study: The StudyMetadata object to be added.

        Returns:
            None
        """
        self.studies[study.study_id] = study

    def get(self, study_id: str) -> Optional[CenterStudyMetadata]:
        """Gets the study metadata for the study id.

        Args:
            study_id: the study id
        Returns:
            the study metadata for the study
        """
        return self.studies.get(study_id)

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_center(self)


class REDCapProjectInput(BaseModel):
    """Metadata for REDCap project details."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    center_id: str
    study_id: str
    project_label: str
    projects: List[REDCapFormProjectMetadata]


class StudyREDCapProjectsList(RootModel):
    """List of REDCap ingest projects metadata for a given study."""

    root: List[REDCapProjectInput]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> REDCapProjectInput:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, entry: REDCapProjectInput) -> None:
        """Appends the redcap project metadata to the list."""
        self.root.append(entry)


class REDCapModule(BaseModel):
    """Information required to create a REDCap project for a module.

    label: module name (uds, ftld, etc.)
    title: REDCap project title (this will be prefixed with center name)
    template[Optional]: XML template filename prefix (if different from label)
    """

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )
    label: str
    title: str
    template: Optional[str] = None


class REDCapProjectMapping(BaseModel):
    """List of REDCap projects associated with a Flywheel project."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )
    project_label: str
    modules: List[REDCapModule]


class StudyREDCapMetadata(BaseModel):
    """REDCap project info associated with a study."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )
    study_id: str
    centers: List[str]
    projects: List[REDCapProjectMapping]


class GatherIngestDatatypesVisitor(AbstractCenterMetadataVisitor):
    """Scrapes the ingest projects of the center metadata for datatypes."""

    def __init__(self) -> None:
        self.__datatypes: List[DatatypeNameType] = []

    @property
    def datatypes(self):
        return self.__datatypes

    def visit_center(self, center: CenterMetadata) -> None:
        for study in center.studies.values():
            study.apply(self)

    def visit_study(self, study: CenterStudyMetadata) -> None:
        for project in study.ingest_projects.values():
            project.apply(self)

    def visit_project(self, project: ProjectMetadata) -> None:
        try:
            label = PipelineLabel.model_validate(project.project_label)
        except TypeError:
            return
        except ValidationError:
            return

        if label.datatype is None:
            return

        self.__datatypes.append(label.datatype)

    def visit_ingest_project(self, project: IngestProjectMetadata) -> None:
        self.visit_project(project)

    def visit_form_ingest_project(self, project: FormIngestProjectMetadata) -> None:
        self.visit_project(project)

    def visit_redcap_form_project(self, project: REDCapFormProjectMetadata) -> None:
        pass

    def visit_distribution_project(self, project: DistributionProjectMetadata) -> None:
        pass

    def visit_dashboard_project(self, project: DashboardProjectMetadata) -> None:
        pass
