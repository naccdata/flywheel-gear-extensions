"""Unit tests for the REDCap disable step in InactiveUserProcess.

Tests the REDCap role removal flow through the public visit() method,
verifying auth email resolution, center iteration, dry-run mode,
event collection, step independence, and four-step ordering.

Requirements: 2.1, 2.2, 2.3, 2.4, 3.2, 3.4, 3.5, 3.6, 3.7,
              4.2, 4.3, 4.4, 7.1, 7.2, 7.3
"""

from unittest.mock import Mock

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


def _build_mock_redcap(title: str = "Test Project") -> Mock:
    """Build a mock REDCapProject with a title."""
    mock_redcap = Mock(spec=REDCapProject)
    mock_redcap.title = title
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

        # unassign_user_role should be called with the entry's auth_email
        mock_redcap.assign_user_role.assert_called_once_with("entry-auth@uni.edu", "")

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

        mock_redcap.assign_user_role.assert_called_once_with(
            "comanage-auth@uni.edu", ""
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

        mock_redcap.assign_user_role.assert_called_once_with("dir@example.com", "")


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
        mock_redcap_100.assign_user_role.side_effect = REDCapConnectionError(
            "connection failed"
        )
        mock_redcap_200 = _build_mock_redcap(title="Project 200")
        mock_redcap_200.assign_user_role.return_value = 1

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
        mock_redcap_100.assign_user_role.assert_called_once()
        mock_redcap_200.assign_user_role.assert_called_once()

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
        mock_redcap.assign_user_role.assert_called_once()


# ===========================================================================
# Dry-run mode tests
# Validates: Requirement 3.7
# ===========================================================================


class TestDryRunMode:
    """Test dry-run mode behavior."""

    def test_dry_run_does_not_call_unassign(self) -> None:
        """In dry-run mode, unassign_user_role is not called.

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

        # assign_user_role should NOT be called
        mock_redcap.assign_user_role.assert_not_called()

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
        mock_redcap.assign_user_role.side_effect = REDCapConnectionError("timeout")
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
        mock_redcap.assign_user_role.assert_called_once()

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
        mock_redcap.assign_user_role.assert_called_once_with("looked-up@uni.edu", "")

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
        original_assign = mock_redcap.assign_user_role

        def track_assign(*args, **kwargs):
            call_order.append("redcap_unassign")
            return original_assign.return_value

        mock_redcap.assign_user_role.side_effect = track_assign

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
