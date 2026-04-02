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
    DashboardResource,
    DatatypeResource,
    Resource,
    StudyAuthorizations,
)
from users.user_entry import CenterUserEntry


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
                "submit-audit-datatype-form": ["read-only"],
                "view-datatype-form": ["read-only"],
                "submit-audit-datatype-dicom": ["read-only"],
            },
            "ingest-form": {
                "view-datatype-form": ["read-only"],
                "submit-audit-datatype-form": ["upload", "audit"],
            },
            "ingest-enrollment": {
                "view-datatype-enrollment": ["read-only"],
                "submit-audit-datatype-enrollment": ["upload"],
            },
            "sandbox-form": {"submit-audit-datatype-form": ["upload"]},
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
        "  submit-audit-datatype-form: [read-only]\n"
        "  view-datatype-form: [read-only]\n"
        "  submit-audit-datatype-dicom: [read-only]\n"
        "ingest-form:\n"
        "  view-datatype-form: [read-only]\n"
        "  submit-audit-datatype-form:\n"
        "    - upload\n"
        "    - audit\n"
        "ingest-enrollment:\n"
        "  view-datatype-enrollment: [read-only]\n"
        "  submit-audit-datatype-enrollment: [upload]\n"
        "sandbox-form:\n"
        "  submit-audit-datatype-form: [upload]\n"
    )


@pytest.fixture
def alpha_authorizations():
    """Authorizations object."""
    authorizations = StudyAuthorizations(study_id="dummy")
    authorizations.add_datatype(datatype="form", action="submit-audit")
    authorizations.add_datatype(datatype="enrollment", action="submit-audit")
    yield authorizations


@pytest.fixture
def beta_authorizations():
    """Authorizations object."""
    authorizations = StudyAuthorizations(study_id="dummy")
    authorizations.add_datatype(datatype="dicom", action="submit-audit")
    authorizations.add_datatype(datatype="form", action="view")
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

    def test_activity_as_dict_key(self, role_map: dict[str, RoleOutput]):
        """Test that Activity objects work as dictionary keys in AuthMap."""
        # Create AuthMap with Activity objects as keys
        auth_map = AuthMap.model_validate(
            {
                "test-project": {
                    "submit-audit-datatype-form": ["upload"],
                    "view-datatype-form": ["read-only"],
                }
            },
            context={"role_map": role_map},
        )

        # Create new Activity instances with same values
        activity1 = Activity(
            resource=DatatypeResource(datatype="form"), action="submit-audit"
        )
        activity2 = Activity(resource=DatatypeResource(datatype="form"), action="view")

        # Should be able to look up roles using new Activity instances
        project_auth = auth_map.project_authorizations["test-project"]
        assert activity1 in project_auth
        assert activity2 in project_auth
        assert project_auth[activity1][0].label == "upload"
        assert project_auth[activity2][0].label == "read-only"

    def test_authmap_with_dashboard_activities(self, role_map: dict[str, RoleOutput]):
        """Test AuthMap with dashboard activities."""
        auth_map = AuthMap.model_validate(
            {
                "dashboard-reports": {
                    "view-dashboard-reports": ["read-only"],
                },
                "ingest-form": {
                    "submit-audit-datatype-form": ["upload"],
                },
            },
            context={"role_map": role_map},
        )

        # Create authorizations with dashboard activity
        dashboard_auth = StudyAuthorizations(study_id="test")
        dashboard_resource = DashboardResource(dashboard="reports")
        dashboard_activity = Activity(resource=dashboard_resource, action="view")
        dashboard_auth.activities[dashboard_resource] = dashboard_activity

        # Should get read-only role for dashboard
        roles = auth_map.get(
            project_label="dashboard-reports", authorizations=dashboard_auth
        )
        assert len(roles) == 1
        assert roles[0].label == "read-only"

    def test_authmap_mixed_resource_types(self, role_map: dict[str, RoleOutput]):
        """Test AuthMap with mixed datatype and dashboard activities."""
        auth_map = AuthMap.model_validate(
            {
                "mixed-project": {
                    "submit-audit-datatype-form": ["upload"],
                    "view-dashboard-reports": ["read-only"],
                }
            },
            context={"role_map": role_map},
        )

        # Create authorizations with both types
        mixed_auth = StudyAuthorizations(study_id="test")
        mixed_auth.add_datatype(datatype="form", action="submit-audit")

        dashboard_resource = DashboardResource(dashboard="reports")
        dashboard_activity = Activity(resource=dashboard_resource, action="view")
        mixed_auth.activities[dashboard_resource] = dashboard_activity

        # Should get both roles
        roles = auth_map.get(project_label="mixed-project", authorizations=mixed_auth)
        role_labels = sorted([role.label for role in roles])
        assert role_labels == ["read-only", "upload"]

    def test_authmap_activity_equality(self, role_map: dict[str, RoleOutput]):
        """Test that Activity equality works correctly in AuthMap lookups."""
        auth_map = AuthMap.model_validate(
            {"test-project": {"submit-audit-datatype-form": ["upload"]}},
            context={"role_map": role_map},
        )

        # Create authorization with activity
        auth = StudyAuthorizations(study_id="test")
        auth.add_datatype(datatype="form", action="submit-audit")

        # Get roles - should match even though Activity instances are different
        roles = auth_map.get(project_label="test-project", authorizations=auth)
        assert len(roles) == 1
        assert roles[0].label == "upload"

    def test_authmap_with_hyphenated_datatype(self, role_map: dict[str, RoleOutput]):
        """Test AuthMap with hyphenated datatype names."""
        auth_map = AuthMap.model_validate(
            {
                "ingest-scan": {
                    "view-datatype-scan-analysis": ["read-only"],
                    "submit-audit-datatype-scan-analysis": ["upload"],
                }
            },
            context={"role_map": role_map},
        )

        # Create authorization with hyphenated datatype
        auth = StudyAuthorizations(study_id="test")
        auth.add_datatype(datatype="scan-analysis", action="view")

        roles = auth_map.get(project_label="ingest-scan", authorizations=auth)
        assert len(roles) == 1
        assert roles[0].label == "read-only"

    def test_authmap_project_label_suffix_handling(
        self, role_map: dict[str, RoleOutput]
    ):
        """Test AuthMap handles project labels with study suffixes."""
        # AuthMap without study suffix
        auth_map = AuthMap.model_validate(
            {"ingest-form": {"submit-audit-datatype-form": ["upload"]}},
            context={"role_map": role_map},
        )

        auth = StudyAuthorizations(study_id="test")
        auth.add_datatype(datatype="form", action="submit-audit")

        # Should match "ingest-form-dvcid" by removing suffix
        roles = auth_map.get(project_label="ingest-form-dvcid", authorizations=auth)
        assert len(roles) == 1
        assert roles[0].label == "upload"


class TestAuthorization:
    def test_contains(self):
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add_datatype(datatype="form", action="submit-audit")

        assert "submit-audit-datatype-form" in authorization
        assert "view-datatype-form" not in authorization

        activity = Activity(
            resource=DatatypeResource(datatype="form"), action="submit-audit"
        )
        assert activity in authorization
        activity = Activity(resource=DatatypeResource(datatype="form"), action="view")
        assert activity not in authorization
        activity = Activity(resource=DatatypeResource(datatype="apoe"), action="view")
        assert activity not in authorization

    def test_contains_with_string(self):
        """Test __contains__ with string activity representation."""
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add_datatype(datatype="form", action="submit-audit")
        authorization.add_datatype(datatype="enrollment", action="view")

        # Test string format
        assert "submit-audit-datatype-form" in authorization
        assert "view-datatype-enrollment" in authorization
        assert "view-datatype-form" not in authorization
        assert "submit-audit-datatype-enrollment" not in authorization

    def test_contains_with_resource_as_key(self):
        """Test that Resource objects work as dictionary keys in activities."""
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add_datatype(datatype="form", action="submit-audit")

        # Create a new Resource instance with same value
        form_resource = DatatypeResource(datatype="form")
        activity = Activity(resource=form_resource, action="submit-audit")

        # Should find it because Resource is frozen and hashable
        assert activity in authorization

    def test_add_multiple_datatypes(self):
        """Test adding multiple datatype activities."""
        authorization = StudyAuthorizations(study_id="adrc")
        authorization.add_datatype(datatype="form", action="submit-audit")
        authorization.add_datatype(datatype="enrollment", action="submit-audit")
        authorization.add_datatype(datatype="scan-analysis", action="view")

        assert len(authorization.activities) == 3
        assert "submit-audit-datatype-form" in authorization
        assert "submit-audit-datatype-enrollment" in authorization
        assert "view-datatype-scan-analysis" in authorization

    def test_add_overwrites_existing(self):
        """Test that adding same datatype overwrites previous activity."""
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add_datatype(datatype="form", action="submit-audit")
        authorization.add_datatype(datatype="form", action="view")

        # Should only have one activity for form
        assert len(authorization.activities) == 1
        assert "view-datatype-form" in authorization
        assert "submit-audit-datatype-form" not in authorization

    def test_validation(self):
        auth = {
            "activities": {
                "datatype-enrollment": "submit-audit-datatype-enrollment",
                "datatype-form": "submit-audit-datatype-form",
                "datatype-scan-analysis": "view-datatype-scan-analysis",
            },
            "study_id": "adrc",
        }
        try:
            study_auth = StudyAuthorizations.model_validate(auth)
        except ValidationError as error:
            raise AssertionError(error) from error

        assert study_auth is not None
        assert len(study_auth.activities) == 3

    def test_validation_with_dashboard_activities(self):
        """Test validation with both datatype and dashboard activities."""
        auth = {
            "activities": {
                "datatype-form": "submit-audit-datatype-form",
                "dashboard-reports": "view-dashboard-reports",
            },
            "study_id": "adrc",
        }
        try:
            study_auth = StudyAuthorizations.model_validate(auth)
        except ValidationError as error:
            raise AssertionError(error) from error

        assert study_auth is not None
        assert len(study_auth.activities) == 2

        # Check that both types of resources are present
        has_datatype = False
        has_dashboard = False
        for resource in study_auth.activities:
            if isinstance(resource, DatatypeResource):
                has_datatype = True
            elif isinstance(resource, DashboardResource):
                has_dashboard = True

        assert has_datatype
        assert has_dashboard

    def test_str(self):
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add_datatype(datatype="form", action="submit-audit")

        assert (
            str(authorization)
            == "study_id='dummy' activities=[submit-audit-datatype-form]"
        )

    def test_str_multiple_activities(self):
        """Test string representation with multiple activities."""
        authorization = StudyAuthorizations(study_id="adrc")
        authorization.add_datatype(datatype="form", action="submit-audit")
        authorization.add_datatype(datatype="enrollment", action="view")

        result = str(authorization)
        assert "study_id='adrc'" in result
        assert "submit-audit-datatype-form" in result
        assert "view-datatype-enrollment" in result

    def test_contains_invalid_string(self):
        """Test __contains__ with invalid string format."""
        authorization = StudyAuthorizations(study_id="dummy")
        authorization.add_datatype(datatype="form", action="submit-audit")

        # Invalid strings should return False, not raise exception
        assert "invalid-string" not in authorization
        assert "not-a-valid-activity" not in authorization

    def test_resource_equality_in_activities_dict(self):
        """Test that Resource equality works correctly as dict keys."""
        authorization = StudyAuthorizations(study_id="dummy")

        # Add activity with one resource instance
        resource1 = DatatypeResource(datatype="form")
        activity1 = Activity(resource=resource1, action="submit-audit")
        authorization.activities[resource1] = activity1

        # Create another resource instance with same value
        resource2 = DatatypeResource(datatype="form")

        # Should be able to retrieve using the second instance
        assert resource2 in authorization.activities
        assert authorization.activities[resource2] == activity1

    def test_mixed_resource_types_in_activities(self):
        """Test activities dict can hold different resource types."""
        authorization = StudyAuthorizations(study_id="dummy")

        # Add datatype activity
        datatype_resource = DatatypeResource(datatype="form")
        datatype_activity = Activity(resource=datatype_resource, action="submit-audit")
        authorization.activities[datatype_resource] = datatype_activity

        # Add dashboard activity
        dashboard_resource = DashboardResource(dashboard="reports")
        dashboard_activity = Activity(resource=dashboard_resource, action="view")
        authorization.activities[dashboard_resource] = dashboard_activity

        assert len(authorization.activities) == 2
        assert datatype_activity in authorization
        assert dashboard_activity in authorization


class TestUserAuthorizations:
    def test_user_case(self):
        user_yaml = (
            "active: true\n"
            "adcid: 0\n"
            "approved: true\n"
            "auth_email: blah@blah.org\n"
            "authorizations:\n"
            "  activities: {}\n"
            "study_authorizations:\n"
            "- activities:\n"
            "    datatype-enrollment: submit-audit-datatype-enrollment\n"
            "    datatype-form: submit-audit-datatype-form\n"
            "  study_id: adrc\n"
            "email: blah@blah.org\n"
            "name:\n"
            "  first_name: Blah\n"
            "  last_name: Blah\n"
            "org_name: Blah"
        )
        user_object = yaml.safe_load(user_yaml)
        assert user_object
        user_entry = CenterUserEntry.model_validate(user_object)
        authorizations = {
            auth.study_id: auth for auth in user_entry.study_authorizations
        }
        adrc_authorization = authorizations.get("adrc")
        assert adrc_authorization
        assert "submit-audit-datatype-enrollment" in adrc_authorization
        assert "submit-audit-datatype-form" in adrc_authorization
        assert (
            Activity(
                resource=DatatypeResource(datatype="enrollment"),
                action="submit-audit",
            )
            in adrc_authorization
        )
        assert (
            Activity(resource=DatatypeResource(datatype="form"), action="submit-audit")
            in adrc_authorization
        )

        redcap_metadata = REDCapFormProjectMetadata(
            redcap_pid=0, label=DefaultValues.ENROLLMENT_MODULE
        )
        submission_activity = redcap_metadata.get_submission_activity()
        assert (
            Activity(
                resource=DatatypeResource(datatype="enrollment"),
                action="submit-audit",
            )
            == submission_activity
        )
        assert submission_activity in adrc_authorization

        redcap_metadata = REDCapFormProjectMetadata(redcap_pid=0, label="blah")
        submission_activity = redcap_metadata.get_submission_activity()
        assert (
            Activity(resource=DatatypeResource(datatype="form"), action="submit-audit")
            == submission_activity
        )
        assert submission_activity in adrc_authorization


class TestActivitiesDictMethods:
    """Test dictionary-like methods of Activities class."""

    def test_getitem(self):
        """Test __getitem__ method for accessing activities by resource."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")
        activity = Activity(resource=resource, action="submit-audit")
        authorization.activities[resource] = activity

        # Should be able to access using bracket notation
        retrieved = authorization.activities[resource]
        assert retrieved == activity

    def test_getitem_key_error(self):
        """Test __getitem__ raises KeyError for missing resource."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")

        with pytest.raises(KeyError):
            _ = authorization.activities[resource]

    def test_setitem(self):
        """Test __setitem__ method for setting activities."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")
        activity = Activity(resource=resource, action="submit-audit")

        # Should be able to set using bracket notation
        authorization.activities[resource] = activity
        assert authorization.activities[resource] == activity

    def test_delitem(self):
        """Test __delitem__ method for deleting activities."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")
        activity = Activity(resource=resource, action="submit-audit")
        authorization.activities[resource] = activity

        # Should be able to delete using del
        del authorization.activities[resource]
        assert resource not in authorization.activities
        assert len(authorization.activities) == 0

    def test_delitem_key_error(self):
        """Test __delitem__ raises KeyError for missing resource."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")

        with pytest.raises(KeyError):
            del authorization.activities[resource]

    def test_len(self):
        """Test __len__ method returns correct count."""
        authorization = StudyAuthorizations(study_id="test")
        assert len(authorization.activities) == 0

        authorization.add_datatype(datatype="form", action="submit-audit")
        assert len(authorization.activities) == 1

        authorization.add_datatype(datatype="enrollment", action="view")
        assert len(authorization.activities) == 2

    def test_iter(self):
        """Test __iter__ method for iterating over resource keys."""
        authorization = StudyAuthorizations(study_id="test")
        resource1 = DatatypeResource(datatype="form")
        resource2 = DatatypeResource(datatype="enrollment")
        activity1 = Activity(resource=resource1, action="submit-audit")
        activity2 = Activity(resource=resource2, action="view")

        authorization.activities[resource1] = activity1
        authorization.activities[resource2] = activity2

        # Should be able to iterate over resources
        resources = list(authorization.activities)
        assert len(resources) == 2
        assert resource1 in resources
        assert resource2 in resources

    def test_keys(self):
        """Test keys() method returns resource keys."""
        authorization = StudyAuthorizations(study_id="test")
        resource1 = DatatypeResource(datatype="form")
        resource2 = DatatypeResource(datatype="enrollment")
        activity1 = Activity(resource=resource1, action="submit-audit")
        activity2 = Activity(resource=resource2, action="view")

        authorization.activities[resource1] = activity1
        authorization.activities[resource2] = activity2

        keys = authorization.activities.keys()
        assert resource1 in keys
        assert resource2 in keys
        assert len(list(keys)) == 2

    def test_values(self):
        """Test values() method returns activity values."""
        authorization = StudyAuthorizations(study_id="test")
        resource1 = DatatypeResource(datatype="form")
        resource2 = DatatypeResource(datatype="enrollment")
        activity1 = Activity(resource=resource1, action="submit-audit")
        activity2 = Activity(resource=resource2, action="view")

        authorization.activities[resource1] = activity1
        authorization.activities[resource2] = activity2

        values = authorization.activities.values()
        assert activity1 in values
        assert activity2 in values
        assert len(list(values)) == 2

    def test_items(self):
        """Test items() method returns (resource, activity) pairs."""
        authorization = StudyAuthorizations(study_id="test")
        resource1 = DatatypeResource(datatype="form")
        resource2 = DatatypeResource(datatype="enrollment")
        activity1 = Activity(resource=resource1, action="submit-audit")
        activity2 = Activity(resource=resource2, action="view")

        authorization.activities[resource1] = activity1
        authorization.activities[resource2] = activity2

        items = list(authorization.activities.items())
        assert len(items) == 2
        assert (resource1, activity1) in items
        assert (resource2, activity2) in items

    def test_get_with_existing_key(self):
        """Test get() method with existing key."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")
        activity = Activity(resource=resource, action="submit-audit")
        authorization.activities[resource] = activity

        retrieved = authorization.activities.get(resource)
        assert retrieved == activity

    def test_get_with_missing_key(self):
        """Test get() method with missing key returns None."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")

        retrieved = authorization.activities.get(resource)
        assert retrieved is None

    def test_get_with_default(self):
        """Test get() method with missing key returns default value."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")
        default_activity = Activity(
            resource=DatatypeResource(datatype="enrollment"), action="view"
        )

        retrieved = authorization.activities.get(resource, default_activity)
        assert retrieved == default_activity

    def test_contains_with_resource_key(self):
        """Test __contains__ with Resource key (dict-like behavior)."""
        authorization = StudyAuthorizations(study_id="test")
        resource = DatatypeResource(datatype="form")
        activity = Activity(resource=resource, action="submit-audit")
        authorization.activities[resource] = activity

        # Should support checking if resource key exists
        assert resource in authorization.activities

        missing_resource = DatatypeResource(datatype="enrollment")
        assert missing_resource not in authorization.activities

    def test_dict_like_usage_pattern(self):
        """Test using Activities like a regular dict."""
        authorization = StudyAuthorizations(study_id="test")

        # Add items using dict-like syntax
        form_resource = DatatypeResource(datatype="form")
        form_activity = Activity(resource=form_resource, action="submit-audit")
        authorization.activities[form_resource] = form_activity

        enrollment_resource = DatatypeResource(datatype="enrollment")
        enrollment_activity = Activity(resource=enrollment_resource, action="view")
        authorization.activities[enrollment_resource] = enrollment_activity

        # Check length
        assert len(authorization.activities) == 2

        # Iterate over keys
        for resource in authorization.activities:
            assert isinstance(resource, Resource)

        # Iterate over items
        for resource, activity in authorization.activities.items():
            assert isinstance(resource, Resource)
            assert isinstance(activity, Activity)

        # Check membership
        assert form_resource in authorization.activities
        assert enrollment_resource in authorization.activities

        # Get values
        assert authorization.activities[form_resource] == form_activity
        assert authorization.activities.get(enrollment_resource) == enrollment_activity

        # Delete item
        del authorization.activities[form_resource]
        assert form_resource not in authorization.activities
        assert len(authorization.activities) == 1

    def test_mixed_resource_types_dict_access(self):
        """Test dict-like access with mixed resource types."""
        authorization = StudyAuthorizations(study_id="test")

        # Add datatype resource
        datatype_resource = DatatypeResource(datatype="form")
        datatype_activity = Activity(resource=datatype_resource, action="submit-audit")
        authorization.activities[datatype_resource] = datatype_activity

        # Add dashboard resource
        dashboard_resource = DashboardResource(dashboard="reports")
        dashboard_activity = Activity(resource=dashboard_resource, action="view")
        authorization.activities[dashboard_resource] = dashboard_activity

        # Should be able to access both types
        assert authorization.activities[datatype_resource] == datatype_activity
        assert authorization.activities[dashboard_resource] == dashboard_activity

        # Should be able to iterate over both
        resources = list(authorization.activities.keys())
        assert len(resources) == 2
        assert datatype_resource in resources
        assert dashboard_resource in resources
