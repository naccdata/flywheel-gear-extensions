"""Tests for serialization of portal metadata managed by CenterGroup."""

import pytest
from centers.center_group import (
    CenterMetadata,
    CenterStudyMetadata,
    DashboardProjectMetadata,
    FormIngestProjectMetadata,
    IngestProjectMetadata,
    PageProjectMetadata,
    ProjectMetadata,
    REDCapFormProjectMetadata,
    REDCapProjectInput,
)
from keys.keys import DefaultValues
from pydantic import ValidationError


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def project_with_datatype():
    """Returns a ProjectMetadata object with datatype."""
    yield IngestProjectMetadata(
        study_id="test",
        pipeline_adcid=0,
        project_id="9999999999",
        project_label="ingest-blah-test",
        datatype="blah",
    )


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def form_ingest_without_redcap():
    """Returns a form ingest project without redcap info."""
    yield IngestProjectMetadata(
        study_id="alpha",
        pipeline_adcid=0,
        project_id="11111111",
        project_label="ingest-form-alpha",
        datatype="form",
    )


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def ingest_project_with_redcap():
    """Returns a form ingest project."""
    yield FormIngestProjectMetadata(
        study_id="test",
        pipeline_adcid=0,
        project_id="88888888",
        project_label="ingest-form-test",
        datatype="form",
        redcap_projects={
            "dummyv9": REDCapFormProjectMetadata(
                redcap_pid=12345, label="dummyv9", report_id=22
            )
        },
    )


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def project_without_datatype():
    """Returns a ProjectMetadata object without datatype."""
    yield ProjectMetadata(
        study_id="test", project_id="77777777", project_label="accepted-test"
    )


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def dashboard_project():
    """Returns a DashboardProjectMetadata object."""
    yield DashboardProjectMetadata(
        study_id="test",
        project_id="66666666",
        project_label="dashboard-enrollment-test",
        dashboard_name="enrollment",
    )


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def dashboard_project_primary():
    """Returns a DashboardProjectMetadata for primary study."""
    yield DashboardProjectMetadata(
        study_id="nacc",
        project_id="55555555",
        project_label="dashboard-qc-status",
        dashboard_name="qc-status",
    )


# pylint: disable=(no-self-use,too-few-public-methods)
class TestProjectMetadataSerialization:
    """Tests for serialization of ProjectMetadata."""

    # pylint: disable=(redefined-outer-name)
    def test_project_serialization(self, project_with_datatype):
        """Tests basic serialization of project."""
        project_dump = project_with_datatype.model_dump(
            by_alias=True, exclude_none=True
        )
        assert project_dump
        assert len(project_dump.keys()) == 5
        assert "project-label" in project_dump
        assert "study-id" in project_dump

        try:
            model_object = IngestProjectMetadata.model_validate(project_dump)
            assert model_object == project_with_datatype
        except ValidationError as error:
            assert False, error  # noqa: B011

    # pylint: disable=(redefined-outer-name)
    def test_project_with_datatype(self, project_with_datatype):
        """Tests serialization of project metadata where has datatype."""
        project_dump = project_with_datatype.model_dump(
            by_alias=True, exclude_none=True
        )
        assert project_dump
        assert "datatype" in project_dump
        assert project_dump["datatype"] == "blah"
        assert "redcap-url" not in project_dump
        assert "redcap-pid" not in project_dump
        assert project_dump["project-label"] == "ingest-blah-test"

    # pylint: disable=(redefined-outer-name)
    def test_ingest_with_redcap(self, ingest_project_with_redcap):
        """Tests serialization of ingest project with redcap info."""
        project_dump = ingest_project_with_redcap.model_dump(
            by_alias=True, exclude_none=True
        )
        assert project_dump
        assert "redcap-projects" in project_dump
        assert "redcap-pid" in project_dump["redcap-projects"]["dummyv9"]
        assert "label" in project_dump["redcap-projects"]["dummyv9"]
        assert project_dump["project-label"] == "ingest-form-test"

        try:
            model_object = FormIngestProjectMetadata.model_validate(project_dump)
            assert model_object == ingest_project_with_redcap
        except ValidationError as error:
            assert False, error  # noqa: B011

    # pylint: disable=(redefined-outer-name)
    def test_project_without_datatype(self, project_without_datatype):
        """Tests serialization of project metadata without datatype."""
        project_dump = project_without_datatype.model_dump(
            by_alias=True, exclude_none=True
        )
        assert "datatype" not in project_dump
        assert project_dump["project-label"] == "accepted-test"

        try:
            model_object = ProjectMetadata.model_validate(project_dump)
            assert model_object == project_without_datatype
        except ValidationError as error:
            assert False, error  # noqa: B011


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def study_object(
    project_without_datatype, project_with_datatype, ingest_project_with_redcap
):
    """Returns metadata object for study."""

    projects = {}
    projects[project_with_datatype.project_label] = project_with_datatype
    projects[ingest_project_with_redcap.project_label] = ingest_project_with_redcap
    yield CenterStudyMetadata(
        study_id="test",
        study_name="Test",
        ingest_projects=projects,
        accepted_project=project_without_datatype,
    )


class TestStudyMetadataSerialization:
    """Tests for serialization of StudyMetadata."""

    # pylint: disable=(redefined-outer-name)
    def test_study_serialization(self, study_object):
        """Test serialization of study info."""
        study_dump = study_object.model_dump(by_alias=True, exclude_none=True)
        assert study_dump
        assert "study-id" in study_dump
        assert "study-name" in study_dump
        assert "ingest-projects" in study_dump
        assert "accepted-project" in study_dump
        assert len(study_dump.keys()) == 7

        try:
            model_object = CenterStudyMetadata.model_validate(study_dump)
            assert model_object == study_object
        except ValidationError as error:
            assert False, error  # noqa: B011


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def portal_metadata(study_object):
    """Creates portal info object."""
    studies = {}
    studies[study_object.study_id] = study_object
    yield CenterMetadata(adcid=0, active=True, studies=studies)


class TestCenterPortalMetadataSerialization:
    """Tests serialization of center portal metadata."""

    def test_portal_metadata(self, portal_metadata):
        """Test serialization of portal info."""
        portal_dump = portal_metadata.model_dump(by_alias=True, exclude_none=True)
        assert portal_dump
        assert len(portal_dump.keys()) == 3
        assert "studies" in portal_dump

        try:
            model_object = CenterMetadata.model_validate(portal_dump)
            assert model_object == portal_metadata
        except ValidationError as error:
            assert False, error  # noqa: B011


class TestREDCapUpdate:
    """Tests for updating REDCap project info."""

    def test_redcap_info_update(self, portal_metadata):
        """Tests for updating redcap project info."""
        assert portal_metadata, "expect non-null info object"

        input_object = REDCapProjectInput(
            center_id="dummy",
            study_id="test",
            project_label="ingest-form-test",
            projects=[
                REDCapFormProjectMetadata(
                    redcap_pid=12345,
                    label=DefaultValues.ENROLLMENT_MODULE,
                    report_id=22,
                )
            ],
        )
        study_info = portal_metadata.studies.get(input_object.study_id)
        ingest_project = study_info.get_ingest(input_object.project_label)
        assert ingest_project, "expect non-null ingest project"

        ingest_project = FormIngestProjectMetadata.create_from_ingest(ingest_project)
        assert ingest_project, "expect non-null ingest after conversion"

        for input_project in input_object.projects:
            ingest_project.add(input_project)
        assert ingest_project, "expect non-null ingest project after update"
        assert ingest_project.redcap_projects, (
            "expect non-null redcap projects after update"
        )
        assert ingest_project.redcap_projects.get(DefaultValues.ENROLLMENT_MODULE), (
            "expect non-null redcap project after update"
        )

        study_info.add_ingest(ingest_project)
        portal_metadata.add(study_info)

        assert (
            portal_metadata.studies["test"]
            .ingest_projects["ingest-form-test"]
            .redcap_projects[DefaultValues.ENROLLMENT_MODULE]
        ), "expect non-null redcap project after update"


class TestDashboardProjectMetadataSerialization:
    """Tests for serialization of DashboardProjectMetadata."""

    def test_dashboard_project_serialization(self, dashboard_project):
        """Tests basic serialization of dashboard project."""
        project_dump = dashboard_project.model_dump(by_alias=True, exclude_none=True)
        assert project_dump
        assert "project-label" in project_dump
        assert "study-id" in project_dump
        assert "dashboard-name" in project_dump
        assert project_dump["dashboard-name"] == "enrollment"
        assert project_dump["project-label"] == "dashboard-enrollment-test"

        try:
            model_object = DashboardProjectMetadata.model_validate(project_dump)
            assert model_object == dashboard_project
        except ValidationError as error:
            assert False, error  # noqa: B011

    def test_dashboard_project_primary_study(self, dashboard_project_primary):
        """Tests serialization of dashboard project for primary study."""
        project_dump = dashboard_project_primary.model_dump(
            by_alias=True, exclude_none=True
        )
        assert project_dump
        assert project_dump["dashboard-name"] == "qc-status"
        assert project_dump["project-label"] == "dashboard-qc-status"


class TestDashboardMetadataOperations:
    """Tests for dashboard project metadata operations."""

    def test_add_dashboard_to_study(self, dashboard_project):
        """Test adding dashboard project to study metadata."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        study.add_dashboard(dashboard_project)
        assert study.dashboard_projects is not None
        assert dashboard_project.project_label in study.dashboard_projects
        retrieved = study.get_dashboard(dashboard_project.project_label)
        assert retrieved == dashboard_project

    def test_get_nonexistent_dashboard(self):
        """Test getting dashboard that doesn't exist."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        result = study.get_dashboard("nonexistent-dashboard")
        assert result is None

    def test_dashboard_projects_none_by_default(self):
        """Test that dashboard_projects can be None."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        # Should handle None gracefully
        result = study.get_dashboard("any-label")
        assert result is None

    def test_study_serialization_with_dashboards(self, dashboard_project):
        """Test serialization of study info with dashboard projects."""
        dashboard_projects = {}
        dashboard_projects[dashboard_project.project_label] = dashboard_project

        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
            dashboard_projects=dashboard_projects,
        )

        study_dump = study.model_dump(by_alias=True, exclude_none=True)
        assert study_dump
        assert "dashboard-projects" in study_dump
        assert len(study_dump["dashboard-projects"]) == 1

        try:
            model_object = CenterStudyMetadata.model_validate(study_dump)
            assert model_object == study
        except ValidationError as error:
            assert False, error  # noqa: B011

    def test_backward_compatibility_without_dashboards(self, study_object):
        """Test that old metadata without dashboard_projects still loads."""
        # Simulate old metadata
        study_dump = study_object.model_dump(by_alias=True, exclude_none=True)
        # Remove dashboard_projects if it exists
        study_dump.pop("dashboard-projects", None)

        try:
            model_object = CenterStudyMetadata.model_validate(study_dump)
            assert (
                model_object.dashboard_projects is None
                or model_object.dashboard_projects == {}
            )
        except ValidationError as error:
            assert False, error  # noqa: B011



# pylint: disable=(redefined-outer-name)
@pytest.fixture
def page_project():
    """Returns a PageProjectMetadata object."""
    yield PageProjectMetadata(
        study_id="test",
        project_id="44444444",
        project_label="page-enrollment-test",
        page_name="enrollment",
    )


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def page_project_primary():
    """Returns a PageProjectMetadata for primary study."""
    yield PageProjectMetadata(
        study_id="nacc",
        project_id="33333333",
        project_label="page-data-entry",
        page_name="data-entry",
    )


class TestPageProjectMetadataSerialization:
    """Tests for serialization of PageProjectMetadata."""

    def test_page_project_serialization(self, page_project):
        """Tests basic serialization of page project."""
        project_dump = page_project.model_dump(by_alias=True, exclude_none=True)
        assert project_dump
        assert "project-label" in project_dump
        assert "study-id" in project_dump
        assert "page-name" in project_dump
        assert project_dump["page-name"] == "enrollment"
        assert project_dump["project-label"] == "page-enrollment-test"

        try:
            model_object = PageProjectMetadata.model_validate(project_dump)
            assert model_object == page_project
        except ValidationError as error:
            assert False, error  # noqa: B011

    def test_page_project_primary_study(self, page_project_primary):
        """Tests serialization of page project for primary study."""
        project_dump = page_project_primary.model_dump(
            by_alias=True, exclude_none=True
        )
        assert project_dump
        assert project_dump["page-name"] == "data-entry"
        assert project_dump["project-label"] == "page-data-entry"

    def test_page_project_has_all_required_fields(self, page_project):
        """Tests that PageProjectMetadata has all required fields."""
        assert page_project.study_id
        assert page_project.project_id
        assert page_project.project_label
        assert page_project.page_name
        assert isinstance(page_project.study_id, str)
        assert isinstance(page_project.project_id, str)
        assert isinstance(page_project.project_label, str)
        assert isinstance(page_project.page_name, str)


class TestPageProjectVisitorPattern:
    """Tests for PageProjectMetadata visitor pattern."""

    def test_page_project_apply_calls_visitor(self, page_project):
        """Tests that apply() calls visit_page_project on the visitor."""
        from unittest.mock import Mock

        visitor = Mock()
        page_project.apply(visitor)
        visitor.visit_page_project.assert_called_once_with(page_project)


class TestPageMetadataOperations:
    """Tests for page project metadata operations."""

    def test_add_page_to_study(self, page_project):
        """Test adding page project to study metadata."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        study.add_page(page_project)
        assert study.page_projects is not None
        assert page_project.project_label in study.page_projects
        retrieved = study.get_page(page_project.project_label)
        assert retrieved == page_project

    def test_get_nonexistent_page(self):
        """Test getting page that doesn't exist."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        result = study.get_page("nonexistent-page")
        assert result is None

    def test_page_projects_none_by_default(self):
        """Test that page_projects can be None."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        # Should handle None gracefully
        result = study.get_page("any-label")
        assert result is None

    def test_study_serialization_with_pages(self, page_project):
        """Test serialization of study info with page projects."""
        page_projects = {}
        page_projects[page_project.project_label] = page_project

        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
            page_projects=page_projects,
        )

        study_dump = study.model_dump(by_alias=True, exclude_none=True)
        assert study_dump
        assert "page-projects" in study_dump
        assert len(study_dump["page-projects"]) == 1

        try:
            model_object = CenterStudyMetadata.model_validate(study_dump)
            assert model_object == study
        except ValidationError as error:
            assert False, error  # noqa: B011

    def test_backward_compatibility_without_pages(self, study_object):
        """Test that old metadata without page_projects still loads."""
        # Simulate old metadata
        study_dump = study_object.model_dump(by_alias=True, exclude_none=True)
        # Remove page_projects if it exists
        study_dump.pop("page-projects", None)

        try:
            model_object = CenterStudyMetadata.model_validate(study_dump)
            assert (
                model_object.page_projects is None or model_object.page_projects == {}
            )
        except ValidationError as error:
            assert False, error  # noqa: B011

    def test_add_multiple_pages_to_study(self, page_project, page_project_primary):
        """Test adding multiple page projects to study metadata."""
        study = CenterStudyMetadata(
            study_id="test",
            study_name="Test",
        )
        study.add_page(page_project)
        study.add_page(page_project_primary)

        assert study.page_projects is not None
        assert len(study.page_projects) == 2
        assert page_project.project_label in study.page_projects
        assert page_project_primary.project_label in study.page_projects
