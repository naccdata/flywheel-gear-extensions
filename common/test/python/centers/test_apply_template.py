"""Tests for CenterGroup.apply_template failure handling.

Covers the accumulate-and-fail-closed behavior: transport/timeout
failures for individual projects are recorded and the remaining projects
are still attempted, while any other (unexpected) error aborts
immediately.
"""

from typing import Optional
from unittest.mock import MagicMock

import pytest
from centers.center_group import CenterGroup, TemplateApplicationFailure
from fw_client.errors import TransportError


def make_transport_error(message: str) -> TransportError:
    """Builds a TransportError with a request attached, as httpx does when the
    error is raised during an actual request.

    fw-client patches HTTPError.__str__ to reference ``.request``, so an
    error without a request raises when stringified; attaching one
    models reality.
    """
    error = TransportError(message)
    error.request = MagicMock()  # type: ignore[assignment]
    error.request.method = "PUT"
    error.request.url = "https://example.flywheel.io/api/projects/x/settings"
    return error


def create_mock_project(
    project_id: str = "proj-id",
    label: str = "accepted",
    group: str = "test-center",
    pipeline_adcid=None,
) -> MagicMock:
    """Factory for a mock ProjectAdaptor used as a template destination."""
    project = MagicMock()
    project.id = project_id
    project.label = label
    project.group = group
    project.get_info.return_value = (
        {} if pipeline_adcid is None else {"pipeline_adcid": pipeline_adcid}
    )
    return project


def create_center_group(projects, adcid: int = 42) -> CenterGroup:
    """Creates a CenterGroup with collaborators stubbed for apply_template.

    The constructor only assigns attributes (no network), so a mock
    group and proxy are sufficient. get_matching_projects is stubbed to
    return the given projects, and the proxy's site lookup is stubbed.
    """
    group = MagicMock()
    group.label = "test-center"

    proxy = MagicMock()
    proxy.get_site.return_value = "https://example.flywheel.io"

    center = CenterGroup(adcid=adcid, active=True, group=group, proxy=proxy)
    # Stub the matching-projects lookup; apply_template only needs its result.
    center.get_matching_projects = MagicMock(return_value=projects)  # type: ignore
    return center


def create_template(pattern: Optional[str] = "^accepted") -> MagicMock:
    """Factory for a mock TemplateProject with a matching pattern."""
    template = MagicMock()
    template.get_pattern.return_value = pattern
    return template


class TestApplyTemplate:
    """Tests for CenterGroup.apply_template."""

    def test_no_pattern_returns_no_failures(self):
        """A template with no pattern applies to nothing and never fails."""
        template = create_template(pattern=None)
        center = create_center_group(projects=[])

        failures = center.apply_template(template)

        assert failures == []
        template.copy_to.assert_not_called()

    def test_all_projects_succeed(self):
        """When every project succeeds, no failures are returned."""
        projects = [
            create_mock_project(label="accepted"),
            create_mock_project(label="accepted-ncrad"),
        ]
        center = create_center_group(projects=projects)
        template = create_template()

        failures = center.apply_template(template)

        assert failures == []
        assert template.copy_to.call_count == 2

    def test_transport_error_is_recorded_and_remaining_attempted(self):
        """A transport error on one project is recorded while the rest are
        still attempted."""
        first = create_mock_project(label="accepted")
        second = create_mock_project(label="accepted-ncrad")
        third = create_mock_project(label="accepted-leads")
        center = create_center_group(projects=[first, second, third])
        template = create_template()

        # Second project times out; first and third succeed.
        template.copy_to.side_effect = [
            None,
            make_transport_error("read timed out"),
            None,
        ]

        failures = center.apply_template(template)

        # Every project was attempted despite the middle failure.
        assert template.copy_to.call_count == 3
        assert len(failures) == 1
        failure = failures[0]
        assert isinstance(failure, TemplateApplicationFailure)
        assert failure.label == "accepted-ncrad"
        assert failure.group == "test-center"
        assert "read timed out" in failure.error

    def test_multiple_transport_errors_all_recorded(self):
        """Multiple transport failures are all accumulated."""
        projects = [
            create_mock_project(label="accepted"),
            create_mock_project(label="accepted-ncrad"),
        ]
        center = create_center_group(projects=projects)
        template = create_template()
        template.copy_to.side_effect = [
            make_transport_error("timeout one"),
            make_transport_error("timeout two"),
        ]

        failures = center.apply_template(template)

        assert len(failures) == 2
        assert {failure.label for failure in failures} == {
            "accepted",
            "accepted-ncrad",
        }

    def test_non_transport_error_aborts_immediately(self):
        """A non-transport error aborts without attempting later projects."""
        first = create_mock_project(label="accepted")
        second = create_mock_project(label="accepted-ncrad")
        center = create_center_group(projects=[first, second])
        template = create_template()
        template.copy_to.side_effect = [RuntimeError("unexpected bug"), None]

        with pytest.raises(RuntimeError, match="unexpected bug"):
            center.apply_template(template)

        # Aborted on the first project; the second was never attempted.
        assert template.copy_to.call_count == 1
