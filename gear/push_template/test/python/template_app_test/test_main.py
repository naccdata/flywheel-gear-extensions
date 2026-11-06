"""Tests for template_app.main.run accumulate-and-fail-closed behavior.

run attempts every matching project in every center, accumulates per-
project transport failures, and raises TemplateError (which the gear
maps to a non-zero exit) when any project failed.
"""

from unittest.mock import MagicMock

import pytest

from centers.center_group import TemplateApplicationFailure
from projects.template_project import TemplateError
from template_app.main import run


def create_failure(group: str, label: str, error: str) -> TemplateApplicationFailure:
    """Factory for a TemplateApplicationFailure."""
    return TemplateApplicationFailure(group=group, label=label, error=error)


def create_center(apply_result, tags=None) -> MagicMock:
    """Factory for a mock center whose apply_template returns apply_result."""
    center = MagicMock()
    center.apply_template.return_value = apply_result
    center.get_tags.return_value = tags or []
    return center


def create_admin_group(centers) -> MagicMock:
    """Factory for a mock admin group returning the given centers."""
    admin_group = MagicMock()
    admin_group.get_centers.return_value = centers
    return admin_group


class TestRun:
    """Tests for template_app.main.run."""

    def test_no_centers_returns_without_error(self):
        """When the admin group has no centers, run returns without raising."""
        admin_group = create_admin_group(centers=[])
        template = MagicMock()

        run(admin_group=admin_group, new_only=False, template=template)

        # Nothing to apply to.
        template.copy_to.assert_not_called()

    def test_all_projects_succeed_does_not_raise(self):
        """When every center reports no failures, run does not raise."""
        centers = [create_center(apply_result=[]), create_center(apply_result=[])]
        admin_group = create_admin_group(centers=centers)

        run(admin_group=admin_group, new_only=False, template=MagicMock())

        for center in centers:
            center.apply_template.assert_called_once()

    def test_failures_raise_template_error_listing_projects(self):
        """Accumulated failures across centers raise a TemplateError that names
        each failed project."""
        centers = [
            create_center(
                apply_result=[create_failure("center-a", "accepted", "timeout a")]
            ),
            create_center(
                apply_result=[create_failure("center-b", "accepted-ncrad", "timeout b")]
            ),
        ]
        admin_group = create_admin_group(centers=centers)

        with pytest.raises(TemplateError) as exc_info:
            run(admin_group=admin_group, new_only=False, template=MagicMock())

        message = str(exc_info.value)
        assert "2 project(s)" in message
        assert "center-a/accepted" in message
        assert "center-b/accepted-ncrad" in message
        # Both centers were attempted before failing (fail closed at the end).
        for center in centers:
            center.apply_template.assert_called_once()

    def test_attempts_all_centers_before_raising(self):
        """A failure in the first center does not short-circuit later
        centers."""
        failing = create_center(
            apply_result=[create_failure("center-a", "accepted", "timeout")]
        )
        succeeding = create_center(apply_result=[])
        admin_group = create_admin_group(centers=[failing, succeeding])

        with pytest.raises(TemplateError):
            run(admin_group=admin_group, new_only=False, template=MagicMock())

        failing.apply_template.assert_called_once()
        succeeding.apply_template.assert_called_once()

    def test_new_only_skips_untagged_centers(self):
        """With new_only, centers without the 'new-center' tag are skipped."""
        tagged = create_center(apply_result=[], tags=["new-center"])
        untagged = create_center(apply_result=[], tags=["adcid-1"])
        admin_group = create_admin_group(centers=[tagged, untagged])

        run(admin_group=admin_group, new_only=True, template=MagicMock())

        tagged.apply_template.assert_called_once()
        untagged.apply_template.assert_not_called()
