"""Tests for serialization of portal metadata managed by CenterGroup."""

import pytest
from centers.center_group import (
    CenterProjectMetadata,
    FormIngestProjectMetadata,
    IngestProjectMetadata,
    ProjectMetadata,
    REDCapFormProjectMetadata,
    REDCapProjectInput,
    StudyMetadata,
)
from keys.keys import DefaultValues
from pydantic import ValidationError


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def project_with_datatype():
    """Returns a ProjectMetadata object with datatype."""
    yield IngestProjectMetadata(study_id="test",
                                project_id="9999999999",
                                project_label="ingest-blah-test",
                                datatype="blah")


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def form_ingest_without_redcap():
    """Returns a form ingest project without redcap info."""
    yield IngestProjectMetadata(study_id="alpha",
                                project_id="11111111",
                                project_label="ingest-form-alpha",
                                datatype="form")


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def ingest_project_with_redcap():
    """Returns a form ingest project."""
    yield FormIngestProjectMetadata(study_id="test",
                                    project_id="88888888",
                                    project_label="ingest-form-test",
                                    datatype="form",
                                    redcap_projects={
                                        "dummyv9":
                                        REDCapFormProjectMetadata(
                                            redcap_pid=12345,
                                            label="dummyv9",
                                            report_id=22)
                                    })


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def project_without_datatype():
    """Returns a ProjectMetadata object without datatype."""
    yield ProjectMetadata(study_id="test",
                          project_id="77777777",
                          project_label="accepted-test")


# pylint: disable=(no-self-use,too-few-public-methods)
class TestProjectMetadataSerialization:
    """Tests for serialization of ProjectMetadata."""

    # pylint: disable=(redefined-outer-name)
    def test_project_serialization(self, project_with_datatype):
        """Tests basic serialization of project."""
        project_dump = project_with_datatype.model_dump(by_alias=True,
                                                        exclude_none=True)
        assert project_dump
        assert len(project_dump.keys()) == 4
        assert 'project-label' in project_dump
        assert 'study-id' in project_dump

        try:
            model_object = IngestProjectMetadata.model_validate(project_dump)
            assert model_object == project_with_datatype
        except ValidationError as error:
            assert False, error  # noqa: B011

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
    def test_ingest_with_redcap(self, ingest_project_with_redcap):
        """Tests serialization of ingest project with redcap info."""
        project_dump = ingest_project_with_redcap.model_dump(by_alias=True,
                                                             exclude_none=True)
        assert project_dump
        assert 'redcap-projects' in project_dump
        assert 'redcap-pid' in project_dump['redcap-projects']['dummyv9']
        assert 'label' in project_dump['redcap-projects']['dummyv9']
        assert project_dump['project-label'] == "ingest-form-test"

        try:
            model_object = FormIngestProjectMetadata.model_validate(
                project_dump)
            assert model_object == ingest_project_with_redcap
        except ValidationError as error:
            assert False, error  # noqa: B011

    # pylint: disable=(redefined-outer-name)
    def test_project_without_datatype(self, project_without_datatype):
        """Tests serialization of project metadata without datatype."""
        project_dump = project_without_datatype.model_dump(by_alias=True,
                                                           exclude_none=True)
        assert 'datatype' not in project_dump
        assert project_dump['project-label'] == "accepted-test"

        try:
            model_object = ProjectMetadata.model_validate(project_dump)
            assert model_object == project_without_datatype
        except ValidationError as error:
            assert False, error  # noqa: B011


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
        assert len(study_dump.keys()) == 5

        try:
            model_object = StudyMetadata.model_validate(study_dump)
            assert model_object == study_object
        except ValidationError as error:
            assert False, error  # noqa: B011


# pylint: disable=(redefined-outer-name)
@pytest.fixture
def portal_metadata(study_object):
    """Creates portal info object."""
    studies = {}
    studies[study_object.study_id] = study_object
    yield CenterProjectMetadata(studies=studies)


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
            model_object = CenterProjectMetadata.model_validate(portal_dump)
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
                    report_id=22)
            ])
        study_info = portal_metadata.studies.get(input_object.study_id)
        ingest_project = study_info.get_ingest(input_object.project_label)
        assert ingest_project, "expect non-null ingest project"

        ingest_project = FormIngestProjectMetadata.create_from_ingest(
            ingest_project)
        assert ingest_project, "expect non-null ingest after conversion"

        for input_project in input_object.projects:
            ingest_project.add(input_project)
        assert ingest_project, "expect non-null ingest project after update"
        assert ingest_project.redcap_projects, (
            "expect non-null redcap projects after update")
        assert ingest_project.redcap_projects.get(
            DefaultValues.ENROLLMENT_MODULE), \
            "expect non-null redcap project after update"

        study_info.add_ingest(ingest_project)
        portal_metadata.add(study_info)

        assert portal_metadata.studies["test"].ingest_projects[
            "ingest-form-test"].redcap_projects[
                DefaultValues.ENROLLMENT_MODULE], \
            "expect non-null redcap project after update"
