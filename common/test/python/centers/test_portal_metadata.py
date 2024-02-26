"""Tests for serialization of portal metadata managed by CenterGroup."""

import pytest
from centers.center_group import (CenterPortalMetadata,
                                  FormIngestProjectMetadata,
                                  IngestProjectMetadata, ProjectMetadata,
                                  StudyMetadata)
from pydantic import ValidationError


@pytest.fixture
def site():
    """Returns a site."""
    yield "https://blah.blah"


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def project_with_datatype(site):
    """Returns a ProjectMetadata object with datatype."""
    yield IngestProjectMetadata.create(site=site,
                                       study_id="test",
                                       project_id="9999999999",
                                       project_label="ingest-blah-test",
                                       datatype="blah")


@pytest.fixture
def redcap_site():
    """Returns a redcap site."""
    yield "https://redcap.blah"


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def ingest_project_with_redcap(site, redcap_site):
    """Returns a form ingest project."""
    yield FormIngestProjectMetadata.create(site=site,
                                           study_id="test",
                                           project_id="88888888",
                                           project_label="ingest-form-test",
                                           datatype="form",
                                           redcap_project_id=999,
                                           redcap_site=redcap_site)


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def project_without_datatype(site):
    """Returns a ProjectMetadata object without datatype."""
    yield ProjectMetadata.create(site=site,
                                 study_id="test",
                                 project_id="77777777",
                                 project_label="accepted-test")


# pylint: disable=(no-self-use,too-few-public-methods)
class TestProjectMetadataSerialization:
    """Tests for serialization of ProjectMetadata."""

    # pylint: disable=(redefined-outer-name)
    def test_project_serialization(self, project_with_datatype, site):
        """Tests basic serialization of project."""
        project_dump = project_with_datatype.model_dump(by_alias=True,
                                                        exclude_none=True)
        assert project_dump
        assert len(project_dump.keys()) == 5
        assert 'project-url' in project_dump
        assert project_dump['project-url'] == (
            f"{site}"
            "/#/projects/"
            f"{project_with_datatype.project_id}"
            "/information")
        assert 'study-id' in project_dump

        try:
            model_object = IngestProjectMetadata.model_validate(project_dump)
            assert model_object == project_with_datatype
        except ValidationError as error:
            assert False, error

    # pylint: disable=(redefined-outer-name)
    def test_project_with_datatype(self, project_with_datatype):
        """Tests serialization of project metadata where has datatype."""
        project_dump = project_with_datatype.model_dump(by_alias=True,
                                                        exclude_none=True)
        assert project_dump
        assert 'datatype' in project_dump
        assert project_dump['datatype'] == 'blah'
        assert 'redcap-url' not in project_dump
        assert 'redcap-pid' not in project_dump
        assert project_dump['project-label'] == "ingest-blah-test"

    # pylint: disable=(redefined-outer-name)
    def test_ingest_with_redcap(self, ingest_project_with_redcap, redcap_site):
        """Tests serialization of ingest project with redcap info."""
        project_dump = ingest_project_with_redcap.model_dump(by_alias=True,
                                                             exclude_none=True)
        assert project_dump
        assert 'redcap-url' in project_dump
        assert 'redcap-project-id' in project_dump
        assert project_dump['redcap-url'] == (
            f"{redcap_site}"
            "/index.php?pid="
            f"{ingest_project_with_redcap.redcap_project_id}")
        assert project_dump['project-label'] == "ingest-form-test"

        try:
            model_object = FormIngestProjectMetadata.model_validate(
                project_dump)
            assert model_object == ingest_project_with_redcap
        except ValidationError as error:
            assert False, error

    # pylint: disable=(redefined-outer-name)
    def test_project_without_datatype(self, project_without_datatype, site):
        """Tests serialization of project metadata without datatype."""
        project_dump = project_without_datatype.model_dump(by_alias=True,
                                                           exclude_none=True)
        assert 'datatype' not in project_dump
        assert project_dump['project-url'] == (
            f"{site}"
            "/#/projects/"
            f"{project_without_datatype.project_id}"
            "/information")
        assert project_dump['project-label'] == "accepted-test"

        try:
            model_object = ProjectMetadata.model_validate(project_dump)
            assert model_object == project_without_datatype
        except ValidationError as error:
            assert False, error


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def study_object(project_without_datatype, project_with_datatype,
                 ingest_project_with_redcap):
    """Returns metadata object for study."""

    projects = {}
    projects[project_with_datatype.project_label] = project_with_datatype
    projects[
        ingest_project_with_redcap.project_label] = ingest_project_with_redcap
    yield StudyMetadata(study_id='test',
                        study_name='Test',
                        ingest_projects=projects,
                        accepted_project=project_without_datatype)


class TestStudyMetadataSerialization:
    """Tests for serialization of StudyMetadata."""

    # pylint: disable=(redefined-outer-name)
    def test_study_serialization(self, study_object):
        """Test serialization of study info."""
        study_dump = study_object.model_dump(by_alias=True, exclude_none=True)
        assert study_dump
        assert 'study-id' in study_dump
        assert 'study-name' in study_dump
        assert 'ingest-projects' in study_dump
        assert 'accepted-project' in study_dump
        assert len(study_dump.keys()) == 4

        try:
            model_object = StudyMetadata.model_validate(study_dump)
            assert model_object == study_object
        except ValidationError as error:
            assert False, error


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def portal_metadata(study_object):
    """Creates portal info object."""
    studies = {}
    studies[study_object.study_id] = study_object
    yield CenterPortalMetadata(studies=studies)


class TestCenterPortalMetadataSerialization:
    """Tests serialization of center portal metadata."""

    def test_portal_metadata(self, portal_metadata):
        """Test serialization of portal info."""
        portal_dump = portal_metadata.model_dump(by_alias=True,
                                                 exclude_none=True)
        assert portal_dump
        assert len(portal_dump.keys()) == 1
        assert 'studies' in portal_dump

        try:
            model_object = CenterPortalMetadata.model_validate(portal_dump)
            assert model_object == portal_metadata
        except ValidationError as error:
            assert False, error
