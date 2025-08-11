"""Tests for authorization module."""

import pytest
import yaml
from pydantic import ValidationError
from users.authorizations import AuthMap, Authorizations


@pytest.fixture
def empty_auth():
    """Empty authorizations."""
    yield Authorizations(
        study_id="dummy",
        submit=[],
        audit_data=False,
        approve_data=False,
        view_reports=False,
    )


@pytest.fixture
def auth_map_alpha():
    """AuthMap object."""
    auth_map = AuthMap(
        project_authorizations={
            "accepted": {
                "approve-data": "read-only",
                "audit-data": "read-only",
                "view-reports": "read-only",
                "submit-form": "read-only",
                "submit-dicom": "read-only",
            },
            "ingest-form": {
                "approve-data": "read-only",
                "audit-data": "read-only",
                "view-reports": "read-only",
                "submit-form": "upload",
            },
            "ingest-enrollment": {
                "approve-data": "read-only",
                "audit-data": "read-only",
                "view-reports": "read-only",
                "submit-enrollment": "upload",
            },
            "sandbox-form": {"submit-form": "upload"},
        }
    )
    yield auth_map


@pytest.fixture
def auth_map_alpha_yaml():
    """AuthMap object in YAML format."""
    yield (
        "---\n"
        "accepted:\n"
        "  approve-data: read-only\n"
        "  audit-data: read-only\n"
        "  view-reports: read-only\n"
        "  submit-form: read-only\n"
        "  submit-dicom: read-only\n"
        "ingest-enrollment:\n"
        "  approve-data: read-only\n"
        "  audit-data: read-only\n"
        "  view-reports: read-only\n"
        "  submit-enrollment: upload\n"
        "ingest-form:\n"
        "  approve-data: read-only\n"
        "  audit-data: read-only\n"
        "  view-reports: read-only\n"
        "  submit-form: upload\n"
        "sandbox-form:\n"
        "  submit-form: upload\n"
    )


@pytest.fixture
def alpha_authorizations():
    """Authorizations object."""
    yield Authorizations(
        study_id="dummy",
        submit=["form", "enrollment"],
        audit_data=True,
        approve_data=True,
        view_reports=True,
    )


@pytest.fixture
def beta_authorizations():
    """Authorizations object."""
    yield Authorizations(
        study_id="dummy",
        submit=["dicom"],
        audit_data=False,
        approve_data=True,
        view_reports=False,
    )


class TestAuthorizations:
    """Tests for Authorizations activities."""

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_activities(self):
        """Test get_activities."""
        authorizations = Authorizations(
            study_id="dummy",
            submit=["form", "dicom"],
            audit_data=True,
            approve_data=True,
            view_reports=True,
        )
        assert set(authorizations.get_activities()) == {
            "audit-data",
            "approve-data",
            "submit-form",
            "submit-dicom",
            "view-reports",
        }

        authorizations = Authorizations(
            study_id="dummy",
            submit=["form"],
            audit_data=True,
            approve_data=True,
            view_reports=False,
        )
        assert set(authorizations.get_activities()) == {
            "audit-data",
            "approve-data",
            "submit-form",
        }

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_create_from_record(self):
        """Test create_from_record."""
        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=["a", "b", "c", "d", "e"]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=["form", "enrollment", "dicom"],
            audit_data=True,
            approve_data=True,
            view_reports=True,
        )

        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=["a", "b", "c", "d"]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=["form", "enrollment", "dicom"],
            audit_data=True,
            approve_data=True,
            view_reports=False,
        )

        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=["a", "b", "c"]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=["form", "enrollment", "dicom"],
            audit_data=True,
            approve_data=False,
            view_reports=False,
        )

        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=["a", "b"]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=["form", "enrollment", "dicom"],
            audit_data=False,
            approve_data=False,
            view_reports=False,
        )

        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=["a"]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=["form", "enrollment"],
            audit_data=False,
            approve_data=False,
            view_reports=False,
        )

        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=[]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=[],
            audit_data=False,
            approve_data=False,
            view_reports=False,
        )

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_create_from_record_invalid(self):
        """Test create_from_record with invalid input."""
        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=["a", "b", "x"]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=["form", "enrollment", "dicom"],
            audit_data=False,
            approve_data=False,
            view_reports=False,
        )

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_create_from_record_empty(self):
        """Test create_from_record with empty input."""
        authorizations = Authorizations.create_from_record(
            study_id="dummy", activities=[]
        )
        assert authorizations == Authorizations(
            study_id="dummy",
            submit=[],
            audit_data=False,
            approve_data=False,
            view_reports=False,
        )


class TestAuthMap:
    """Tests for AuthMap."""

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_empty_map(self, empty_auth: Authorizations):
        """Test empty map."""
        auth_map = AuthMap(project_authorizations={})
        assert auth_map.get(project_label="dummy", authorizations=empty_auth) == set()

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_authmap(
        self,
        alpha_authorizations: Authorizations,
        beta_authorizations: Authorizations,
        auth_map_alpha: AuthMap,
    ):
        """Test authmap."""
        assert auth_map_alpha.get(
            project_label="accepted", authorizations=alpha_authorizations
        ) == {"read-only"}
        assert auth_map_alpha.get(
            project_label="ingest-form", authorizations=alpha_authorizations
        ) == {"read-only", "upload"}
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

    # pylint: disable=(redefined-outer-name,no-self-use)
    def test_yaml(self, auth_map_alpha: AuthMap, auth_map_alpha_yaml: str):
        """Test YAML conversion."""
        yaml_object = yaml.safe_load(auth_map_alpha_yaml)
        load_map = AuthMap(project_authorizations=yaml_object)
        assert load_map == auth_map_alpha

        yaml_list = yaml.safe_load("---\n- blah\n- blah\n")
        with pytest.raises(ValidationError):  # type: ignore
            AuthMap(project_authorizations=yaml_list)
