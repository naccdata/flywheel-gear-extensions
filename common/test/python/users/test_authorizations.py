"""Tests for authorization module."""

import pytest
import yaml
from flywheel.models.role_output import RoleOutput
from pydantic import ValidationError
from users.authorizations import (
    Activity,
    AuthMap,
    PipelineLabel,
    StudyAuthorizations,
)


@pytest.fixture
def empty_auth():
    """Empty authorizations."""
    yield StudyAuthorizations(study_id="dummy")


@pytest.fixture
def role_map():
    yield {
        "read-only": RoleOutput(label="read-only"),
        "upload": RoleOutput(label="upload"),
    }


@pytest.fixture
def auth_map_alpha(role_map):
    """AuthMap object."""
    auth_map = AuthMap.model_validate(
        {
            "accepted": {
                "submit-audit-form": "read-only",
                "view-form": "read-only",
                "submit-audit-dicom": "read-only",
            },
            "ingest-form": {
                "view-form": "read-only",
                "submit-audit-form": "upload",
            },
            "ingest-enrollment": {
                "view-enrollment": "read-only",
                "submit-audit-enrollment": "upload",
            },
            "sandbox-form": {"submit-audit-form": "upload"},
        },
        context={"role_map": role_map},
    )
    yield auth_map


@pytest.fixture
def auth_map_alpha_yaml():
    """AuthMap object in YAML format."""
    yield (
        "---\n"
        "accepted:\n"
        "  submit-audit-form: read-only\n"
        "  view-form: read-only\n"
        "  submit-audit-dicom: read-only\n"
        "ingest-form:\n"
        "  view-form: read-only\n"
        "  submit-audit-form: upload\n"
        "ingest-enrollment:\n"
        "  view-enrollment: read-only\n"
        "  submit-audit-enrollment: upload\n"
        "sandbox-form:\n"
        "  submit-audit-form: upload\n"
    )


@pytest.fixture
def alpha_authorizations():
    """Authorizations object."""
    authorizations = StudyAuthorizations(study_id="dummy")
    authorizations.add(datatype="form", action="submit-audit")
    authorizations.add(datatype="enrollment", action="submit-audit")
    yield authorizations


@pytest.fixture
def beta_authorizations():
    """Authorizations object."""
    authorizations = StudyAuthorizations(study_id="dummy")
    authorizations.add(datatype="dicom", action="submit-audit")
    authorizations.add(datatype="form", action="view")
    yield authorizations


class TestAuthMap:
    """Tests for AuthMap."""

    def test_empty_map(self, empty_auth: StudyAuthorizations):
        """Test empty map."""
        auth_map = AuthMap.model_validate({}, context={"role_map": {}})
        assert auth_map.get(project_label="dummy", authorizations=empty_auth) == []

    def test_authmap(
        self,
        alpha_authorizations: StudyAuthorizations,
        beta_authorizations: StudyAuthorizations,
        auth_map_alpha: AuthMap,
    ):
        """Test authmap."""
        role_list = auth_map_alpha.get(
            project_label="accepted", authorizations=alpha_authorizations
        )
        assert [role.label for role in role_list] == ["read-only"]
        role_list = auth_map_alpha.get(
            project_label="ingest-form", authorizations=alpha_authorizations
        )
        assert [role.label for role in role_list] == ["upload"]
        assert (
            auth_map_alpha.get(
                project_label="ingest-dicom", authorizations=alpha_authorizations
            )
            == []
        )
        role_list = auth_map_alpha.get(
            project_label="sandbox-form", authorizations=alpha_authorizations
        )
        assert [role.label for role in role_list] == ["upload"]

        role_list = auth_map_alpha.get(
            project_label="accepted", authorizations=beta_authorizations
        )
        assert [role.label for role in role_list] == ["read-only"]
        role_list = auth_map_alpha.get(
            project_label="ingest-form", authorizations=beta_authorizations
        )
        assert [role.label for role in role_list] == ["read-only"]
        assert (
            auth_map_alpha.get(
                project_label="ingest-dicom", authorizations=beta_authorizations
            )
            == []
        )
        assert (
            auth_map_alpha.get(
                project_label="sandbox-form", authorizations=beta_authorizations
            )
            == []
        )

    def test_yaml(
        self,
        auth_map_alpha: AuthMap,
        auth_map_alpha_yaml: str,
        role_map: dict[str, RoleOutput],
    ):
        """Test YAML conversion."""
        yaml_object = yaml.safe_load(auth_map_alpha_yaml)
        load_map = AuthMap.model_validate(yaml_object, context={"role_map": role_map})
        assert load_map == auth_map_alpha

        yaml_list = yaml.safe_load("---\n- blah\n- blah\n")
        with pytest.raises(TypeError):  # type: ignore
            AuthMap.model_validate(yaml_list, context={"role_map": role_map})


class TestActivity:
    def test_serialization(self):
        activity = Activity(datatype="form", action="submit-audit")

        activity_name = activity.model_dump()
        assert activity_name == "submit-audit-form"

        try:
            activity_load = Activity.model_validate(activity_name)
            assert activity_load == activity
        except ValidationError as error:
            raise AssertionError(error) from error

        activity = Activity(datatype="form", action="view")

        activity_name = activity.model_dump()
        assert activity_name == "view-form"

        try:
            activity_load = Activity.model_validate(activity_name)
            assert activity_load == activity
        except ValidationError as error:
            raise AssertionError(error) from error

    def test_invalid(self):
        with pytest.raises(ValidationError) as info:
            Activity.model_validate({"datatype": "junk", "action": "view"})
        assert len(info.value.errors()) == 1
        error = info.value.errors()[0]
        assert error["loc"][0] == "datatype"

        with pytest.raises(ValidationError) as info:
            Activity.model_validate({"datatype": "form", "action": "junk"})
        assert len(info.value.errors()) == 1
        error = info.value.errors()[0]
        assert error["loc"][0] == "action"


class TestAuthorization:
    def test_contains(self):
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add(datatype="form", action="submit-audit")

        assert "submit-audit-form" in authorization
        assert "view-form" not in authorization


class TestPipelineLabel:
    def test_valid(self):
        label_object = PipelineLabel(
            pipeline="distribution", datatype="genetic-availability", study_id="dummy"
        )
        label_string = label_object.model_dump()
        assert label_string == "distribution-genetic-availability-dummy"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(
            pipeline="distribution", datatype="genetic-availability"
        )
        label_string = label_object.model_dump()
        assert label_string == "distribution-genetic-availability"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(
            pipeline="distribution", datatype="form", study_id="dummy"
        )
        label_string = label_object.model_dump()
        assert label_string == "distribution-form-dummy"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(pipeline="distribution", datatype="form")
        label_string = label_object.model_dump()
        assert label_string == "distribution-form"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(pipeline="accepted", study_id="dummy")
        label_string = label_object.model_dump()
        assert label_string == "accepted-dummy"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load

        label_object = PipelineLabel(pipeline="accepted")
        label_string = label_object.model_dump()
        assert label_string == "accepted"
        label_load = PipelineLabel.model_validate(label_string)
        assert label_object == label_load
