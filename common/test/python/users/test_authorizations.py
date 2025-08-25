"""Tests for authorization module."""

import pytest
import yaml
from pydantic import ValidationError
from users.authorizations import AuthMap, StudyAuthorizations, convert_to_activities


@pytest.fixture
def empty_auth():
    """Empty authorizations."""
    yield StudyAuthorizations(study_id="dummy", activities=[])


@pytest.fixture
def auth_map_alpha():
    """AuthMap object."""
    auth_map = AuthMap(
        project_authorizations={
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
        }
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
    yield StudyAuthorizations(
        study_id="dummy",
        activities=convert_to_activities(
            activity_prefix="submit-audit", datatypes=["form", "enrollment"]
        ),
    )


@pytest.fixture
def beta_authorizations():
    """Authorizations object."""
    activities = convert_to_activities(
        activity_prefix="submit-audit", datatypes=["dicom"]
    )
    activities.append("view-form")
    yield StudyAuthorizations(
        study_id="dummy",
        activities=activities,
    )


class TestAuthMap:
    """Tests for AuthMap."""

    def test_empty_map(self, empty_auth: StudyAuthorizations):
        """Test empty map."""
        auth_map = AuthMap(project_authorizations={})
        assert auth_map.get(project_label="dummy", authorizations=empty_auth) == set()

    def test_authmap(
        self,
        alpha_authorizations: StudyAuthorizations,
        beta_authorizations: StudyAuthorizations,
        auth_map_alpha: AuthMap,
    ):
        """Test authmap."""
        assert auth_map_alpha.get(
            project_label="accepted", authorizations=alpha_authorizations
        ) == {"read-only"}
        assert auth_map_alpha.get(
            project_label="ingest-form", authorizations=alpha_authorizations
        ) == {"upload"}
        assert (
            auth_map_alpha.get(
                project_label="ingest-dicom", authorizations=alpha_authorizations
            )
            == set()
        )
        assert auth_map_alpha.get(
            project_label="sandbox-form", authorizations=alpha_authorizations
        ) == {"upload"}

        assert auth_map_alpha.get(
            project_label="accepted", authorizations=beta_authorizations
        ) == {"read-only"}
        assert auth_map_alpha.get(
            project_label="ingest-form", authorizations=beta_authorizations
        ) == {"read-only"}
        assert (
            auth_map_alpha.get(
                project_label="ingest-dicom", authorizations=beta_authorizations
            )
            == set()
        )
        assert (
            auth_map_alpha.get(
                project_label="sandbox-form", authorizations=beta_authorizations
            )
            == set()
        )

    def test_yaml(self, auth_map_alpha: AuthMap, auth_map_alpha_yaml: str):
        """Test YAML conversion."""
        yaml_object = yaml.safe_load(auth_map_alpha_yaml)
        load_map = AuthMap(project_authorizations=yaml_object)
        assert load_map == auth_map_alpha

        yaml_list = yaml.safe_load("---\n- blah\n- blah\n")
        with pytest.raises(ValidationError):  # type: ignore
            AuthMap(project_authorizations=yaml_list)
