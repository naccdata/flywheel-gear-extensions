import pytest
from pydantic import ValidationError
from users.authorizations import Activity, DashboardResource, DatatypeResource, Resource


class TestResource:
    """Test Resource base class and subclasses."""

    def test_datatype_resource_from_string(self):
        """Test DatatypeResource can be created from prefixed string."""
        resource = DatatypeResource.model_validate("datatype-form")
        assert resource.datatype == "form"
        assert resource.name == "form"
        assert str(resource) == "datatype-form"

    def test_datatype_resource_from_dict(self):
        """Test DatatypeResource can be created from dict."""
        resource = DatatypeResource.model_validate({"datatype": "enrollment"})
        assert resource.datatype == "enrollment"
        assert resource.name == "enrollment"

    def test_datatype_resource_hyphenated(self):
        """Test DatatypeResource handles hyphenated datatype names."""
        resource = DatatypeResource.model_validate("datatype-scan-analysis")
        assert resource.datatype == "scan-analysis"
        assert resource.name == "scan-analysis"

    def test_datatype_resource_invalid(self):
        """Test DatatypeResource rejects invalid datatype."""
        with pytest.raises(ValidationError) as info:
            DatatypeResource.model_validate("datatype-invalid-type")
        assert len(info.value.errors()) == 1
        assert "datatype" in str(info.value)

    def test_dashboard_resource_from_string(self):
        """Test DashboardResource can be created from prefixed string."""
        resource = DashboardResource.model_validate("dashboard-reports")
        assert resource.dashboard == "reports"
        assert resource.name == "reports"
        assert str(resource) == "dashboard-reports"

    def test_dashboard_resource_from_dict(self):
        """Test DashboardResource can be created from dict."""
        resource = DashboardResource.model_validate({"dashboard": "webinars"})
        assert resource.dashboard == "webinars"
        assert resource.name == "webinars"

    def test_dashboard_resource_hyphenated(self):
        """Test DashboardResource handles hyphenated dashboard names."""
        resource = DashboardResource.model_validate("dashboard-user-reports")
        assert resource.dashboard == "user-reports"
        assert resource.name == "user-reports"

    def test_resource_base_class_routing(self):
        """Test Resource.model_validate routes to correct subclass."""
        # Should create DatatypeResource
        resource1 = Resource.model_validate("datatype-form")
        assert isinstance(resource1, DatatypeResource)
        assert resource1.datatype == "form"

        # Should create DashboardResource
        resource2 = Resource.model_validate("dashboard-reports")
        assert isinstance(resource2, DashboardResource)
        assert resource2.dashboard == "reports"

    def test_resource_base_class_invalid(self):
        """Test Resource.model_validate fails on invalid string."""
        with pytest.raises(ValueError) as info:
            Resource.model_validate("invalid-resource-string")
        assert "Could not parse resource" in str(info.value)

    def test_resource_equality(self):
        """Test Resource instances can be compared for equality."""
        res1 = DatatypeResource(datatype="form")
        res2 = DatatypeResource(datatype="form")
        res3 = DatatypeResource(datatype="enrollment")
        res4 = DashboardResource(dashboard="reports")

        assert res1 == res2
        assert res1 != res3
        assert res1 != res4

    def test_resource_hashable(self):
        """Test Resource instances are hashable (for use as dict keys)."""
        res1 = DatatypeResource(datatype="form")
        res2 = DatatypeResource(datatype="form")
        res3 = DashboardResource(dashboard="reports")

        # Should be able to use as dict keys
        resource_dict = {res1: "value1", res3: "value2"}
        assert resource_dict[res2] == "value1"  # res2 equals res1
        assert len(resource_dict) == 2


class TestActivity:
    def test_serialization(self):
        activity = Activity(
            resource=DatatypeResource(datatype="form"), action="submit-audit"
        )

        activity_name = activity.model_dump()
        assert activity_name == "submit-audit-datatype-form"

        try:
            activity_load = Activity.model_validate(activity_name)
            assert activity_load == activity
        except ValidationError as error:
            raise AssertionError(error) from error

        activity = Activity(resource=DatatypeResource(datatype="form"), action="view")

        activity_name = activity.model_dump()
        assert activity_name == "view-datatype-form"

        try:
            activity_load = Activity.model_validate(activity_name)
            assert activity_load == activity
        except ValidationError as error:
            raise AssertionError(error) from error

    def test_dashboard_activity_serialization(self):
        """Test Activity with DashboardResource serialization."""
        activity = Activity(
            resource=DashboardResource(dashboard="reports"), action="view"
        )

        activity_name = activity.model_dump()
        assert activity_name == "view-dashboard-reports"

        try:
            activity_load = Activity.model_validate(activity_name)
            assert activity_load == activity
        except ValidationError as error:
            raise AssertionError(error) from error

    def test_activity_from_dict(self):
        """Test Activity can be created from dict with nested resource dict."""
        # When passing a dict, need to specify which resource type
        activity = Activity.model_validate(
            {
                "action": "submit-audit",
                "resource": {
                    "datatype": "form"
                },  # Will be validated as DatatypeResource
            }
        )
        assert activity.action == "submit-audit"
        assert isinstance(activity.resource, DatatypeResource)
        assert activity.resource.datatype == "form"

        # Or use the string format for resource
        activity2 = Activity.model_validate(
            {"action": "view", "resource": "datatype-enrollment"}
        )
        assert activity2.action == "view"
        assert isinstance(activity2.resource, DatatypeResource)
        assert activity2.resource.datatype == "enrollment"

    def test_invalid(self):
        with pytest.raises(ValidationError) as info:
            Activity.model_validate({"resource": "junk", "action": "view"})
        assert len(info.value.errors()) == 1
        error = info.value.errors()[0]
        assert error["loc"][0] == "resource"

        with pytest.raises(ValidationError) as info:
            Activity.model_validate(
                {"resource": DatatypeResource(datatype="form"), "action": "junk"}
            )
        assert len(info.value.errors()) == 1
        error = info.value.errors()[0]
        assert error["loc"][0] == "action"

    def test_invalid_string_no_action(self):
        """Test Activity validation fails when no valid action in string."""
        # When no valid action is found, the loop completes without breaking,
        # leaving resource_string empty, so "No resource found" error is raised
        with pytest.raises(ValueError) as info:
            Activity.model_validate("invalid-action-datatype-form")
        # The actual error will be "No resource found" because action parsing
        # consumed all tokens without finding a valid action
        assert "No resource found" in str(info.value) or "No valid action found" in str(
            info.value
        )

    def test_invalid_string_no_resource(self):
        """Test Activity validation fails when no resource in string."""
        with pytest.raises(ValueError) as info:
            Activity.model_validate("view")
        assert "No resource found" in str(info.value)

    def test_invalid_string_bad_resource(self):
        """Test Activity validation fails when resource can't be parsed."""
        with pytest.raises(ValueError) as info:
            Activity.model_validate("view-unknown-prefix-value")
        assert "Could not parse resource" in str(info.value)

    def test_hyphenated(self):
        try:
            activity = Activity.model_validate("view-datatype-scan-analysis")
        except ValidationError as error:
            raise AssertionError(error) from error
        assert activity.action == "view"
        assert activity.resource.name == "scan-analysis"

    def test_hyphenated_action(self):
        """Test Activity handles hyphenated action names."""
        activity = Activity.model_validate("submit-audit-datatype-form")
        assert activity.action == "submit-audit"
        assert isinstance(activity.resource, DatatypeResource)
        assert activity.resource.datatype == "form"

    def test_hyphenated_dashboard(self):
        """Test Activity handles hyphenated dashboard names."""
        activity = Activity.model_validate("view-dashboard-user-reports")
        assert activity.action == "view"
        assert isinstance(activity.resource, DashboardResource)
        assert activity.resource.dashboard == "user-reports"

    def test_activity_equality(self):
        """Test Activity instances can be compared for equality."""
        act1 = Activity(resource=DatatypeResource(datatype="form"), action="view")
        act2 = Activity(resource=DatatypeResource(datatype="form"), action="view")
        act3 = Activity(
            resource=DatatypeResource(datatype="form"), action="submit-audit"
        )
        act4 = Activity(resource=DatatypeResource(datatype="enrollment"), action="view")
        act5 = Activity(resource=DashboardResource(dashboard="reports"), action="view")

        assert act1 == act2
        assert act1 != act3  # Different action
        assert act1 != act4  # Different resource
        assert act1 != act5  # Different resource type

    def test_activity_hashable(self):
        """Test Activity instances are hashable (for use as dict keys)."""
        act1 = Activity(resource=DatatypeResource(datatype="form"), action="view")
        act2 = Activity(resource=DatatypeResource(datatype="form"), action="view")
        act3 = Activity(resource=DashboardResource(dashboard="reports"), action="view")

        # Should be able to use as dict keys
        activity_dict = {act1: "value1", act3: "value2"}
        assert activity_dict[act2] == "value1"  # act2 equals act1
        assert len(activity_dict) == 2

    def test_activity_str_representation(self):
        """Test Activity string representation."""
        activity = Activity(
            resource=DatatypeResource(datatype="form"), action="submit-audit"
        )
        assert str(activity) == "submit-audit-datatype-form"

        activity = Activity(
            resource=DashboardResource(dashboard="reports"), action="view"
        )
        assert str(activity) == "view-dashboard-reports"
