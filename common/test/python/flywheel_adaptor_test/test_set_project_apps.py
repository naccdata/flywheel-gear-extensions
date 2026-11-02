"""Tests for FlywheelProxy.set_project_apps skipping unchanged settings."""

from unittest.mock import Mock

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from fw_utils import AttrDict

TEMPLATE_APPS = [AttrDict({"_id": "viewer-1", "name": "OHIF"})]


def build_proxy(current_settings) -> tuple[FlywheelProxy, Mock]:
    """Builds a non-dry-run proxy whose fw-client returns current_settings."""
    fw_client = Mock()
    fw_client.get.return_value = current_settings
    proxy = FlywheelProxy(client=Mock(), fw_client=fw_client, dry_run=False)
    return proxy, fw_client


def build_project() -> Mock:
    project = Mock()
    project.id = "project-id"
    project.label = "accepted"
    return project


class TestSetProjectApps:
    """Tests for FlywheelProxy.set_project_apps."""

    def test_unchanged_apps_skip_put(self):
        """No PUT when the project already has the template's apps."""
        proxy, fw_client = build_proxy(
            {"viewer_apps": [{"_id": "viewer-1", "name": "OHIF"}], "other": 1}
        )

        proxy.set_project_apps(project=build_project(), apps=TEMPLATE_APPS)

        fw_client.put.assert_not_called()

    def test_changed_apps_put_full_settings(self):
        """Different apps are written back with the rest of the settings."""
        proxy, fw_client = build_proxy({"viewer_apps": [], "other": 1})

        proxy.set_project_apps(project=build_project(), apps=TEMPLATE_APPS)

        fw_client.put.assert_called_once_with(
            url="/api/projects/project-id/settings",
            json={"viewer_apps": TEMPLATE_APPS, "other": 1},
        )

    def test_missing_viewer_apps_key_puts(self):
        """Settings without a viewer_apps key are treated as changed."""
        proxy, fw_client = build_proxy({"other": 1})

        proxy.set_project_apps(project=build_project(), apps=TEMPLATE_APPS)

        fw_client.put.assert_called_once()
