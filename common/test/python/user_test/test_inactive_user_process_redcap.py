"""Unit tests for the REDCap disable step in InactiveUserProcess.

Tests the REDCap role removal flow through the public visit() method,
verifying auth email resolution, center iteration, dry-run mode,
event collection, step independence, and four-step ordering.

Requirements: 2.1, 2.2, 2.3, 2.4, 3.2, 3.4, 3.5, 3.6, 3.7,
              4.2, 4.3, 4.4, 7.1, 7.2, 7.3

Preservation Properties: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from unittest.mock import Mock

import pytest
from centers.center_group import (
    CenterMetadata,
    CenterStudyMetadata,
    FormIngestProjectMetadata,
    REDCapFormProjectMetadata,
)
from centers.center_info import CenterInfo, CenterMapInfo
from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy
from redcap_api.redcap_connection import REDCapConnectionError
from redcap_api.redcap_project import REDCapProject
from users.event_models import (
    EventCategory,
    EventType,
    UserEventCollector,
)
from users.user_entry import PersonName, UserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_processes import InactiveUserProcess
from users.user_registry import RegistryPerson, UserRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_entry(
    email: str = "user@example.com",
    auth_email: str | None = None,
) -> UserEntry:
    """Build an inactive UserEntry for testing."""
    return UserEntry(
        name=PersonName(first_name="Test", last_name="User"),
        email=email,
        auth_email=auth_email,
        active=False,
        approved=True,
    )


def _build_mock_env(dry_run: bool = False) -> Mock:
    """Build a mock UserProcessEnvironment with sensible defaults.

    The admin_group mock is configured with an empty center map by
    default.
    """
    mock_env = Mock(spec=UserProcessEnvironment)
    mock_env.proxy = Mock(spec=FlywheelProxy)
    mock_env.proxy.find_user_by_email.return_value = []
    mock_env.proxy.dry_run = dry_run
    mock_env.user_registry = Mock(spec=UserRegistry)
    mock_env.user_registry.get.return_value = []
    mock_env.admin_group = Mock(spec=NACCGroup)
    mock_env.admin_group.get_center_map.return_value = CenterMapInfo(centers={})
    mock_env.admin_group.get_center.return_value = None
    return mock_env


def _build_registry_person(
    auth_email: str = "auth@university.edu",
) -> Mock:
    """Build a mock RegistryPerson with an email_address."""
    person = Mock(spec=RegistryPerson)
    email_addr = Mock()
    email_addr.mail = auth_email
    person.email_address = email_addr
    person.registry_id.return_value = None
    person.is_suspended.return_value = False
    return person


def _build_mock_redcap(
    title: str = "Test Project",
    member_usernames: list[str] | None = None,
) -> Mock:
    """Build a mock REDCapProject with a title.

    Args:
        title: The project title.
        member_usernames: Usernames to include in the role assignment
            export.  When ``None`` (the default) the export returns a
            mapping for every common test email so that existing tests
            that do not care about membership continue to work.
    """
    mock_redcap = Mock(spec=REDCapProject)
    mock_redcap.title = title
    if member_usernames is None:
        # Default: include common test emails so pre-existing tests
        # that don't set export_user_role_assignments still pass the
        # membership check.
        member_usernames = [
            "user@example.com",
            "entry-auth@uni.edu",
            "comanage-auth@uni.edu",
            "dir@example.com",
            "specific@example.com",
            "looked-up@uni.edu",
            "auth@university.edu",
            "should-not-use@uni.edu",
        ]
    mock_redcap.export_user_role_assignments.return_value = [
        {"username": u, "unique_role_name": "U-default"} for u in member_usernames
    ]
    return mock_redcap


def _build_center_metadata_with_redcap(
    pids: list[int] | None = None,
) -> CenterMetadata:
    """Build a CenterMetadata with form ingest projects containing REDCap
    PIDs."""
    if pids is None:
        pids = [100]
    redcap_projects = {
        f"module-{pid}": REDCapFormProjectMetadata(
            redcap_pid=pid,
            label=f"module-{pid}",
        )
        for pid in pids
    }
    form_ingest = FormIngestProjectMetadata(
        study_id="study-1",
        project_id="proj-1",
        project_label="ingest-form",
        pipeline_adcid=1,
        datatype="form",
        redcap_projects=redcap_projects,
    )
    study = CenterStudyMetadata(
        study_id="study-1",
        study_name="Test Study",
        ingest_projects={"ingest-form": form_ingest},
    )
    return CenterMetadata(adcid=1, active=True, studies={"study-1": study})


def _build_center_metadata_no_form_ingest() -> CenterMetadata:
    """Build a CenterMetadata with no form ingest projects."""
    return CenterMetadata(adcid=2, active=True, studies={})


def _setup_center_map_with_centers(
    mock_env: Mock,
    center_configs: list[dict],
) -> dict[int, Mock]:
    """Set up multiple centers in the environment.

    Each config dict should have: adcid, metadata, redcap_project
    (optional). Returns a dict mapping adcid -> mock_center_group.
    """
    center_groups: dict[int, Mock] = {}
    center_map = CenterMapInfo(centers={})
    mock_env.admin_group.get_center_map.return_value = center_map
    mock_env.admin_group.get_center.side_effect = None
    mock_env.admin_group.get_center.return_value = None

    mapping: dict[int, Mock] = {}
    for cfg in center_configs:
        adcid = cfg["adcid"]
        metadata = cfg["metadata"]
        redcap_proj = cfg.get("redcap_project")

        center_info = CenterInfo(
            adcid=adcid, name=f"center-{adcid}", group=f"grp-{adcid}"
        )
        center_map.add(adcid, center_info)

        mock_cg = Mock()
        mock_cg.get_project_info.return_value = metadata
        mock_cg.get_redcap_project.return_value = redcap_proj
        mapping[adcid] = mock_cg
        center_groups[adcid] = mock_cg

    mock_env.admin_group.get_center.side_effect = lambda a: mapping.get(a)
    return center_groups


# ===========================================================================
# Auth email resolution tests
# Validates: Requirements 2.1, 2.2, 2.3, 2.4
# ===========================================================================


class TestAuthEmailResolution:
    """Test REDCap username resolution priority."""

    def test_entry_auth_email_used_directly(self) -> None:
        """When entry has auth_email, it is used as the REDCap username and the
        COmanage auth_email extraction is skipped.

        Validates: Requirement 2.4
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        # Set up a registry person that should NOT be used for auth_email
        person = _build_registry_person(auth_email="should-not-use@uni.edu")
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(auth_email="entry-auth@uni.edu")

        process.visit(entry)

        # delete_user should be called with the entry's auth_email
        mock_redcap.delete_user.assert_called_once_with(username="entry-auth@uni.edu")

    def test_comanage_auth_email_used_when_entry_has_none(self) -> None:
        """When entry has no auth_email but COmanage lookup returns one, the
        COmanage auth_email is used.

        Validates: Requirements 2.1, 2.2
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        person = _build_registry_person(auth_email="comanage-auth@uni.edu")
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        mock_redcap.delete_user.assert_called_once_with(
            username="comanage-auth@uni.edu"
        )

    def test_directory_email_fallback_when_no_registry_match(self) -> None:
        """When no registry person is found and entry has no auth_email, the
        directory email is used as fallback.

        Validates: Requirement 2.3
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        mock_env.user_registry.get.return_value = []

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email="dir@example.com")

        process.visit(entry)

        mock_redcap.delete_user.assert_called_once_with(username="dir@example.com")


# ===========================================================================
# Center iteration tests
# Validates: Requirements 3.2, 3.4, 3.5, 7.1, 7.2, 7.3
# ===========================================================================


class TestCenterIteration:
    """Test iteration over centers and REDCap projects."""

    def test_skips_center_with_no_form_ingest_projects(self) -> None:
        """Centers with no form ingest projects are skipped without error.

        Validates: Requirement 3.2
        """
        mock_env = _build_mock_env()
        metadata_no_forms = _build_center_metadata_no_form_ingest()
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata_no_forms}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # No events should be collected for REDCap
        redcap_events = [
            e
            for e in collector.get_events()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_events) == 0

    def test_skips_project_with_unavailable_credentials(self) -> None:
        """Projects with unavailable REDCap credentials are skipped with an
        error event.

        Validates: Requirement 3.4
        """
        mock_env = _build_mock_env()
        metadata = _build_center_metadata_with_redcap([100])
        # get_redcap_project returns None -> credentials unavailable
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": None}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        errors = collector.get_errors()
        redcap_errors = [
            e for e in errors if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_errors) == 1
        assert "unavailable" in redcap_errors[0].message.lower()

    def test_continues_after_unassignment_failure(self) -> None:
        """Processing continues to the next project after a failure.

        Validates: Requirements 3.5, 7.1
        """
        mock_env = _build_mock_env()
        metadata = _build_center_metadata_with_redcap([100, 200])

        mock_redcap_100 = _build_mock_redcap(title="Project 100")
        mock_redcap_100.delete_user.side_effect = REDCapConnectionError(
            "connection failed"
        )
        mock_redcap_200 = _build_mock_redcap(title="Project 200")
        mock_redcap_200.delete_user.return_value = 1

        center_groups = _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata}],
        )
        # Return different REDCap projects for different PIDs
        center_groups[1].get_redcap_project.side_effect = (
            lambda pid: mock_redcap_100 if pid == 100 else mock_redcap_200
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # Both projects should have been attempted
        mock_redcap_100.delete_user.assert_called_once()
        mock_redcap_200.delete_user.assert_called_once()

        # One error, one success
        redcap_events = [
            e
            for e in collector.get_events()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        errors = [e for e in redcap_events if e.event_type == EventType.ERROR.value]
        successes = [
            e for e in redcap_events if e.event_type == EventType.SUCCESS.value
        ]
        assert len(errors) == 1
        assert len(successes) == 1

    def test_continues_after_center_retrieval_failure(self) -> None:
        """Processing continues when a center group cannot be retrieved.

        Validates: Requirement 7.2
        """
        mock_env = _build_mock_env()
        metadata_good = _build_center_metadata_with_redcap([200])
        mock_redcap = _build_mock_redcap()

        center_map = CenterMapInfo(centers={})
        mock_env.admin_group.get_center_map.return_value = center_map

        # Center 1 cannot be retrieved, center 2 works
        center_map.add(1, CenterInfo(adcid=1, name="c1", group="g1"))
        center_map.add(2, CenterInfo(adcid=2, name="c2", group="g2"))

        mock_cg_2 = Mock()
        mock_cg_2.get_project_info.return_value = metadata_good
        mock_cg_2.get_redcap_project.return_value = mock_redcap

        mock_env.admin_group.get_center.side_effect = (
            lambda a: None if a == 1 else mock_cg_2
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # Center 2's project should still be processed
        mock_redcap.delete_user.assert_called_once()


# ===========================================================================
# Dry-run mode tests
# Validates: Requirement 3.7
# ===========================================================================


class TestDryRunMode:
    """Test dry-run mode behavior."""

    def test_dry_run_does_not_call_unassign(self) -> None:
        """In dry-run mode, delete_user is not called.

        Validates: Requirement 3.7
        """
        mock_env = _build_mock_env(dry_run=True)
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # delete_user should NOT be called
        mock_redcap.delete_user.assert_not_called()

    def test_dry_run_collects_success_event(self) -> None:
        """In dry-run mode, a success event is still collected.

        Validates: Requirement 3.7
        """
        mock_env = _build_mock_env(dry_run=True)
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        successes = collector.get_successes()
        redcap_successes = [
            e
            for e in successes
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 1
        assert "dry run" in redcap_successes[0].message.lower()


# ===========================================================================
# Event collection tests
# Validates: Requirements 4.2, 4.3, 4.4
# ===========================================================================


class TestEventCollection:
    """Test event collection for REDCap disable actions."""

    def test_success_event_has_correct_category_and_pid(self) -> None:
        """Success events have REDCAP_USER_DISABLED category with title and
        PID.

        Validates: Requirement 4.2
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap(title="UDS Forms")
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        successes = collector.get_successes()
        redcap_successes = [
            e
            for e in successes
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 1
        event = redcap_successes[0]
        assert "100" in event.message
        assert "UDS Forms" in event.message

    def test_error_event_has_correct_category_and_details(self) -> None:
        """Error events have REDCAP_USER_DISABLED category with error details.

        Validates: Requirement 4.3
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap(title="UDS Forms")
        mock_redcap.delete_user.side_effect = REDCapConnectionError("timeout")
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        errors = collector.get_errors()
        redcap_errors = [
            e for e in errors if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_errors) == 1
        event = redcap_errors[0]
        assert "100" in event.message
        assert "UDS Forms" in event.message

    def test_event_user_context_contains_email_and_name(self) -> None:
        """Events include user email and name in the UserContext.

        Validates: Requirement 4.4
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email="specific@example.com")

        process.visit(entry)

        successes = collector.get_successes()
        redcap_successes = [
            e
            for e in successes
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 1
        ctx = redcap_successes[0].user_context
        assert ctx.email == "specific@example.com"
        assert "Test" in ctx.name
        assert "User" in ctx.name


# ===========================================================================
# Step independence tests
# Validates: Requirement 3.6
# ===========================================================================


class TestStepIndependence:
    """Test that steps are independent of each other."""

    def test_redcap_step_runs_even_if_flywheel_disable_fails(self) -> None:
        """REDCap step runs even when Flywheel disable raises a FlywheelError.

        Validates: Requirement 3.6
        """
        mock_env = _build_mock_env()
        mock_env.proxy.find_user_by_email.side_effect = FlywheelError(
            "Flywheel failure"
        )

        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # REDCap unassignment was still attempted
        mock_redcap.delete_user.assert_called_once()

    def test_comanage_suspend_runs_even_if_redcap_step_fails(self) -> None:
        """COmanage suspend runs even when the REDCap step raises.

        Validates: Requirement 3.6
        """
        mock_env = _build_mock_env()

        # Set up a registry person for COmanage suspend
        person = _build_registry_person()
        person.registry_id.return_value = "NACC-001"
        mock_env.user_registry.get.return_value = [person]

        # Make the admin_group.get_center_map raise to simulate REDCap step failure
        mock_env.admin_group.get_center_map.side_effect = REDCapConnectionError(
            "REDCap step failure"
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # COmanage suspend was still attempted
        mock_env.user_registry.suspend.assert_called_once_with("NACC-001")


# ===========================================================================
# Four-step ordering tests
# Validates: Requirements 7.3
# ===========================================================================


class TestFourStepOrdering:
    """Test that the four steps execute in the correct order."""

    def test_comanage_lookup_happens_before_redcap_step(self) -> None:
        """COmanage lookup (Step 2) provides auth_email to REDCap step (Step
        3).

        Validates: Requirement 7.3
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        # COmanage lookup returns a person with auth_email
        person = _build_registry_person(auth_email="looked-up@uni.edu")
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()  # no auth_email on entry

        process.visit(entry)

        # The REDCap step should use the auth_email from COmanage lookup
        mock_redcap.delete_user.assert_called_once_with(username="looked-up@uni.edu")

    def test_comanage_suspend_happens_after_redcap_step(self) -> None:
        """COmanage suspend (Step 4) happens after REDCap step (Step 3).

        Validates: Requirement 7.3
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap()
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        person = _build_registry_person()
        person.registry_id.return_value = "NACC-001"
        mock_env.user_registry.get.return_value = [person]

        call_order: list[str] = []
        original_delete = mock_redcap.delete_user

        def track_assign(*args, **kwargs):
            call_order.append("redcap_unassign")
            return original_delete.return_value

        mock_redcap.delete_user.side_effect = track_assign

        original_suspend = mock_env.user_registry.suspend

        def track_suspend(*args, **kwargs):
            call_order.append("comanage_suspend")
            return original_suspend.return_value

        mock_env.user_registry.suspend.side_effect = track_suspend

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        assert "redcap_unassign" in call_order
        assert "comanage_suspend" in call_order
        assert call_order.index("redcap_unassign") < call_order.index(
            "comanage_suspend"
        )


# ===========================================================================
# Bug condition exploration tests
# Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2
# ===========================================================================


class TestBugConditionExploration:
    """Tests for the membership-guard behavior: delete_user should only be
    called for projects where the user actually has a role assignment.

    These tests encode the EXPECTED (correct) behavior and should PASS
    against the fixed implementation.
    """

    def test_non_member_user_should_not_be_unassigned(self) -> None:
        """When a user has no role assignment in a REDCap project, delete_user
        should NOT be called for that project.

        Validates: Requirements 1.1, 2.1
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap(title="Test Project PID 100")
        # Mock export_user_role_assignments to return OTHER users only
        mock_redcap.export_user_role_assignments.return_value = [
            {"username": "other@uni.edu", "unique_role_name": "U-role1"},
        ]
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email="user@example.com")

        process.visit(entry)

        # Expected: delete_user should NOT be called because user
        # has no role assignment in this project.
        mock_redcap.delete_user.assert_not_called()

    def test_non_member_user_should_not_emit_success_event(self) -> None:
        """When a user has no role assignment in a REDCap project, no success
        event with REDCAP_USER_DISABLED should be emitted.

        Validates: Requirements 1.2, 2.2
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap(title="Test Project PID 100")
        mock_redcap.export_user_role_assignments.return_value = [
            {"username": "other@uni.edu", "unique_role_name": "U-role1"},
        ]
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email="user@example.com")

        process.visit(entry)

        # Expected: no success event for REDCAP_USER_DISABLED
        # Bug: on unfixed code a success event IS emitted
        redcap_successes = [
            e
            for e in collector.get_successes()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 0, (
            f"Expected no REDCAP_USER_DISABLED success events for non-member user, "
            f"but got {len(redcap_successes)}: "
            f"{[e.message for e in redcap_successes]}"
        )

    def test_mixed_membership_only_unassigns_member_projects(self) -> None:
        """When a user is a member of PID 100 but NOT PID 200 or PID 300,
        delete_user should be called exactly once (for PID 100 only).

        Validates: Requirements 1.3, 2.1, 2.2
        """
        mock_env = _build_mock_env()

        # PID 100: user IS a member
        mock_redcap_100 = _build_mock_redcap(title="Project 100")
        mock_redcap_100.export_user_role_assignments.return_value = [
            {"username": "user@example.com", "unique_role_name": "U-role1"},
            {"username": "other@uni.edu", "unique_role_name": "U-role2"},
        ]

        # PID 200: user is NOT a member
        mock_redcap_200 = _build_mock_redcap(title="Project 200")
        mock_redcap_200.export_user_role_assignments.return_value = [
            {"username": "someone@uni.edu", "unique_role_name": "U-role1"},
        ]

        # PID 300: user is NOT a member
        mock_redcap_300 = _build_mock_redcap(title="Project 300")
        mock_redcap_300.export_user_role_assignments.return_value = []

        metadata = _build_center_metadata_with_redcap([100, 200, 300])

        def get_redcap_project(pid: int) -> Mock:
            return {100: mock_redcap_100, 200: mock_redcap_200, 300: mock_redcap_300}[
                pid
            ]

        center_groups = _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata}],
        )
        center_groups[1].get_redcap_project.side_effect = get_redcap_project

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email="user@example.com")

        process.visit(entry)

        # Expected: delete_user called exactly once (PID 100 only)
        mock_redcap_100.delete_user.assert_called_once_with(username="user@example.com")
        mock_redcap_200.delete_user.assert_not_called()
        mock_redcap_300.delete_user.assert_not_called()

        # Expected: exactly 1 success event (for PID 100 only)
        redcap_successes = [
            e
            for e in collector.get_successes()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 1, (
            f"Expected 1 REDCAP_USER_DISABLED success event (PID 100 only), "
            f"but got {len(redcap_successes)}: "
            f"{[e.message for e in redcap_successes]}"
        )


# ===========================================================================
# Preservation property tests
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
# ===========================================================================

# Parameterized username/mapping combinations for property-based style tests
_MEMBER_USER_CASES = [
    pytest.param(
        "alice@uni.edu",
        [
            {"username": "alice@uni.edu", "unique_role_name": "U-role1"},
            {"username": "bob@uni.edu", "unique_role_name": "U-role2"},
        ],
        id="alice-with-two-users",
    ),
    pytest.param(
        "bob@example.com",
        [
            {"username": "bob@example.com", "unique_role_name": "U-admin"},
        ],
        id="bob-sole-member",
    ),
    pytest.param(
        "carol@university.edu",
        [
            {"username": "other@uni.edu", "unique_role_name": "U-role1"},
            {"username": "carol@university.edu", "unique_role_name": "U-role2"},
            {"username": "dave@uni.edu", "unique_role_name": "U-role3"},
        ],
        id="carol-among-three",
    ),
    pytest.param(
        "user@example.com",
        [
            {"username": "user@example.com", "unique_role_name": ""},
        ],
        id="user-with-empty-role-name",
    ),
]


class TestPreservationProperties:
    """Preservation property tests: verify that existing behaviors for member
    users, dry-run mode, error handling, and credential unavailability remain
    unchanged.

    These tests are written against the UNFIXED code and are expected to
    PASS, establishing a baseline of behaviors that must be preserved
    after the fix is applied.

    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
    """

    # -----------------------------------------------------------------------
    # Property 2a: Member user unassignment — delete_user is called
    # and a success event with REDCAP_USER_DISABLED is emitted
    # Validates: Requirements 3.1
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("username,role_mappings", _MEMBER_USER_CASES)
    def test_member_user_is_unassigned_and_success_event_emitted(
        self,
        username: str,
        role_mappings: list,
    ) -> None:
        """When a user IS a member of a REDCap project, delete_user is called
        with the username and a success event with REDCAP_USER_DISABLED
        category is emitted.

        **Validates: Requirements 3.1**
        """
        mock_env = _build_mock_env()
        mock_redcap = _build_mock_redcap(title="Preservation Project")
        mock_redcap.export_user_role_assignments.return_value = role_mappings
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email=username)

        process.visit(entry)

        # delete_user must be called with the username
        mock_redcap.delete_user.assert_called_once_with(username=username)

        # A success event with REDCAP_USER_DISABLED must be emitted
        redcap_successes = [
            e
            for e in collector.get_successes()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 1
        assert "100" in redcap_successes[0].message
        assert "Preservation Project" in redcap_successes[0].message

    # -----------------------------------------------------------------------
    # Property 2b: Dry-run mode — delete_user is NOT called but a
    # dry-run success event IS emitted
    # Validates: Requirements 3.3
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("username,role_mappings", _MEMBER_USER_CASES)
    def test_dry_run_member_user_not_called_but_event_emitted(
        self,
        username: str,
        role_mappings: list,
    ) -> None:
        """In dry-run mode with a member user, delete_user is NOT called but a
        dry-run success event with REDCAP_USER_DISABLED IS emitted.

        **Validates: Requirements 3.3**
        """
        mock_env = _build_mock_env(dry_run=True)
        mock_redcap = _build_mock_redcap(title="DryRun Project")
        mock_redcap.export_user_role_assignments.return_value = role_mappings
        metadata = _build_center_metadata_with_redcap([100])
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": mock_redcap}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email=username)

        process.visit(entry)

        # delete_user must NOT be called in dry-run mode
        mock_redcap.delete_user.assert_not_called()

        # A dry-run success event must be emitted
        redcap_successes = [
            e
            for e in collector.get_successes()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_successes) == 1
        assert "dry run" in redcap_successes[0].message.lower()

    # -----------------------------------------------------------------------
    # Property 2c: Error handling — REDCapConnectionError from
    # delete_user emits an error event and processing continues
    # Validates: Requirements 3.4
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("username,role_mappings", _MEMBER_USER_CASES)
    def test_connection_error_emits_error_event_and_continues(
        self,
        username: str,
        role_mappings: list,
    ) -> None:
        """When delete_user raises REDCapConnectionError for a member user, an
        error event with REDCAP_USER_DISABLED category is emitted and
        processing continues to the next project.

        **Validates: Requirements 3.4**
        """
        mock_env = _build_mock_env()

        # First project: delete_user raises REDCapConnectionError
        mock_redcap_100 = _build_mock_redcap(title="Error Project")
        mock_redcap_100.export_user_role_assignments.return_value = role_mappings
        mock_redcap_100.delete_user.side_effect = REDCapConnectionError(
            "connection timeout"
        )

        # Second project: succeeds normally
        mock_redcap_200 = _build_mock_redcap(title="OK Project")
        mock_redcap_200.export_user_role_assignments.return_value = [
            {"username": username, "unique_role_name": "U-role1"},
        ]
        mock_redcap_200.delete_user.return_value = 1

        metadata = _build_center_metadata_with_redcap([100, 200])
        center_groups = _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata}],
        )
        center_groups[1].get_redcap_project.side_effect = (
            lambda pid: mock_redcap_100 if pid == 100 else mock_redcap_200
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email=username)

        process.visit(entry)

        # Both projects should have been attempted
        mock_redcap_100.delete_user.assert_called_once()
        mock_redcap_200.delete_user.assert_called_once()

        # One error event for the failed project
        redcap_events = [
            e
            for e in collector.get_events()
            if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        errors = [e for e in redcap_events if e.event_type == EventType.ERROR.value]
        successes = [
            e for e in redcap_events if e.event_type == EventType.SUCCESS.value
        ]
        assert len(errors) == 1
        assert "Error Project" in errors[0].message
        assert len(successes) == 1
        assert "OK Project" in successes[0].message

    # -----------------------------------------------------------------------
    # Property 2d: Credential unavailability — project is skipped with
    # an error event when get_redcap_project returns None
    # Validates: Requirements 3.2
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "username",
        [
            pytest.param("alice@uni.edu", id="alice"),
            pytest.param("bob@example.com", id="bob"),
            pytest.param("user@example.com", id="default-user"),
        ],
    )
    def test_unavailable_credentials_skips_with_error_event(
        self,
        username: str,
    ) -> None:
        """When get_redcap_project returns None (credentials unavailable), the
        project is skipped and an error event with REDCAP_USER_DISABLED
        category is emitted.

        **Validates: Requirements 3.2**
        """
        mock_env = _build_mock_env()
        metadata = _build_center_metadata_with_redcap([100])
        # get_redcap_project returns None -> credentials unavailable
        _setup_center_map_with_centers(
            mock_env,
            [{"adcid": 1, "metadata": metadata, "redcap_project": None}],
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email=username)

        process.visit(entry)

        errors = collector.get_errors()
        redcap_errors = [
            e for e in errors if e.category == EventCategory.REDCAP_USER_DISABLED.value
        ]
        assert len(redcap_errors) == 1
        assert "unavailable" in redcap_errors[0].message.lower()

    # -----------------------------------------------------------------------
    # Property 2e: Center iteration continues after failure
    # Validates: Requirements 3.5
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "username",
        [
            pytest.param("alice@uni.edu", id="alice"),
            pytest.param("user@example.com", id="default-user"),
        ],
    )
    def test_processing_continues_after_center_retrieval_failure(
        self,
        username: str,
    ) -> None:
        """When a center group cannot be retrieved, processing continues to
        remaining centers.

        **Validates: Requirements 3.5**
        """
        mock_env = _build_mock_env()
        metadata_good = _build_center_metadata_with_redcap([200])
        mock_redcap = _build_mock_redcap(title="Good Project")
        mock_redcap.export_user_role_assignments.return_value = [
            {"username": username, "unique_role_name": "U-role1"},
        ]

        center_map = CenterMapInfo(centers={})
        mock_env.admin_group.get_center_map.return_value = center_map

        # Center 1 cannot be retrieved, center 2 works
        center_map.add(1, CenterInfo(adcid=1, name="c1", group="g1"))
        center_map.add(2, CenterInfo(adcid=2, name="c2", group="g2"))

        mock_cg_2 = Mock()
        mock_cg_2.get_project_info.return_value = metadata_good
        mock_cg_2.get_redcap_project.return_value = mock_redcap

        mock_env.admin_group.get_center.side_effect = (
            lambda a: None if a == 1 else mock_cg_2
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry(email=username)

        process.visit(entry)

        # Center 2's project should still be processed
        mock_redcap.delete_user.assert_called_once()
