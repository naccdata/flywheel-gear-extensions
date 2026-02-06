"""Tests for authorization module."""

import pytest
import yaml
from centers.center_group import REDCapFormProjectMetadata
from flywheel.models.role_output import RoleOutput
from keys.keys import DefaultValues
from pydantic import ValidationError
from users.authorizations import (
    Activity,
    AuthMap,
    StudyAuthorizations,
)
from users.user_entry import ActiveUserEntry


@pytest.fixture
def empty_auth():
    """Empty authorizations."""
    yield StudyAuthorizations(study_id="dummy")


@pytest.fixture
def role_map():
    yield {
        "read-only": RoleOutput(label="read-only"),
        "upload": RoleOutput(label="upload"),
        "audit": RoleOutput(label="audit"),
    }


@pytest.fixture
def auth_map_alpha(role_map):
    """AuthMap object."""
    auth_map = AuthMap.model_validate(
        {
            "accepted": {
                "submit-audit-form": ["read-only"],
                "view-form": ["read-only"],
                "submit-audit-dicom": ["read-only"],
            },
            "ingest-form": {
                "view-form": ["read-only"],
                "submit-audit-form": ["upload", "audit"],
            },
            "ingest-enrollment": {
                "view-enrollment": ["read-only"],
                "submit-audit-enrollment": ["upload"],
            },
            "sandbox-form": {"submit-audit-form": ["upload"]},
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
        "  submit-audit-form: [read-only]\n"
        "  view-form: [read-only]\n"
        "  submit-audit-dicom: [read-only]\n"
        "ingest-form:\n"
        "  view-form: [read-only]\n"
        "  submit-audit-form:\n"
        "    - upload\n"
        "    - audit\n"
        "ingest-enrollment:\n"
        "  view-enrollment: [read-only]\n"
        "  submit-audit-enrollment: [upload]\n"
        "sandbox-form:\n"
        "  submit-audit-form: [upload]\n"
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
        auth_map = AuthMap.model_validate(
            {}, context={"role_map": {"read-only": RoleOutput("read-only")}}
        )
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
        assert [role.label for role in role_list] == ["upload", "audit"]
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

    def test_hyphenated(self):
        try:
            activity = Activity.model_validate("view-scan-analysis")
        except ValidationError as error:
            raise AssertionError(error) from error
        assert activity.action == "view"
        assert activity.datatype == "scan-analysis"


class TestAuthorization:
    def test_contains(self):
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add(datatype="form", action="submit-audit")

        assert "submit-audit-form" in authorization
        assert "view-form" not in authorization

        activity = Activity(datatype="form", action="submit-audit")
        assert activity in authorization
        activity = Activity(datatype="form", action="view")
        assert activity not in authorization
        activity = Activity(datatype="apoe", action="view")
        assert activity not in authorization

    def test_validation(self):
        auth = {
            "activities": {
                "enrollment": "submit-audit-enrollment",
                "form": "submit-audit-form",
                "scan-analysis": "view-scan-analysis",
            },
            "study_id": "adrc",
        }
        try:
            study_auth = StudyAuthorizations.model_validate(auth)
        except ValidationError as error:
            raise AssertionError(error) from error

        assert study_auth is not None

    def test_str(self):
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add(datatype="form", action="submit-audit")

        assert str(authorization) == "study_id='dummy' activities=[submit-audit-form]"


class TestUserAuthorizations:
    def test_user_case(self):
        user_yaml = (
            "active: true\n"
            "adcid: 0\n"
            "approved: true\n"
            "auth_email: blah@blah.org\n"
            "authorizations:\n"
            "- activities:\n"
            "    enrollment: submit-audit-enrollment\n"
            "    form: submit-audit-form\n"
            "  study_id: adrc\n"
            "email: blah@blah.org\n"
            "name:\n"
            "  first_name: Blah\n"
            "  last_name: Blah\n"
            "org_name: Blah"
        )
        user_object = yaml.safe_load(user_yaml)
        assert user_object
        user_entry = ActiveUserEntry.model_validate(user_object)
        authorizations = {auth.study_id: auth for auth in user_entry.authorizations}
        adrc_authorization = authorizations.get("adrc")
        assert adrc_authorization
        assert "submit-audit-enrollment" in adrc_authorization
        assert "submit-audit-form" in adrc_authorization
        assert (
            Activity(datatype="enrollment", action="submit-audit") in adrc_authorization
        )
        assert Activity(datatype="form", action="submit-audit") in adrc_authorization

        redcap_metadata = REDCapFormProjectMetadata(
            redcap_pid=0, label=DefaultValues.ENROLLMENT_MODULE
        )
        submission_activity = redcap_metadata.get_submission_activity()
        assert (
            Activity(datatype="enrollment", action="submit-audit")
            == submission_activity
        )
        assert submission_activity in adrc_authorization

        redcap_metadata = REDCapFormProjectMetadata(redcap_pid=0, label="blah")
        submission_activity = redcap_metadata.get_submission_activity()
        assert Activity(datatype="form", action="submit-audit") == submission_activity
        assert submission_activity in adrc_authorization
