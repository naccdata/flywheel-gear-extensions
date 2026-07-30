"""Property-based tests for NACCID validation, batch resolution, and config.

Properties tested:
  1. NACCID validation separates valid from invalid (Req 1.1)
  3. Error attribution completeness (Req 1.3, 5.1)
  5. Non-positive config parameters rejected (Req 3.3, 3.4)
"""

from unittest.mock import Mock, patch

import pytest
from gather_form_data_app.main import run
from gather_form_data_app.run import GatherFormDataVisitor
from gear_execution.gear_execution import GearExecutionError
from hypothesis import given, settings
from hypothesis import strategies as st
from outputs.error_writer import ListErrorWriter

from .conftest import (
    create_gather_config,
    create_mock_project,
    create_mock_proxy,
    create_mock_subject,
    make_csv_content,
)

# --- Strategies ---

valid_naccid_strategy = st.from_regex(r"NACC\d{6}", fullmatch=True)
test_naccid_strategy = st.from_regex(r"TEST\d{6}", fullmatch=True)
naccid_strategy = st.one_of(valid_naccid_strategy, test_naccid_strategy)

# Strings that do NOT match the NACCID pattern
invalid_naccid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=15,
).filter(
    lambda s: not (
        (s.startswith("NACC") or s.startswith("TEST"))
        and len(s) == 10
        and s[4:].isdigit()
    )
)


# --- Property 1: NACCID validation separates valid from invalid ---


@settings(max_examples=100, deadline=None)
@given(
    valid_ids=st.lists(naccid_strategy, min_size=0, max_size=10),
    invalid_ids=st.lists(invalid_naccid_strategy, min_size=0, max_size=10),
)
def test_validation_separates_valid_from_invalid(valid_ids, invalid_ids):
    """For any mix of valid and invalid NACCIDs, the batch resolution phase
    collects exactly those matching the NACCID pattern into the valid set, and
    produces exactly one error per non-matching string.

    Validates: Requirement 1.1
    """
    # Combine valid and invalid, preserving order
    all_ids = valid_ids + invalid_ids
    if not all_ids:
        return  # skip empty case

    csv_content = make_csv_content(all_ids)

    # Mock proxy: no projects found (so all valid NACCIDs become unresolved)
    proxy = create_mock_proxy(projects=[])

    error_writer = ListErrorWriter(container_id="test-id", fw_path="/test/path")

    run(
        request_file=csv_content,
        proxy=proxy,
        config=create_gather_config(),
        error_writer=error_writer,
    )

    errors = error_writer.errors()
    # Count malformed-file errors (from invalid NACCIDs)
    malformed_errors = [e for e in errors if e.error_code == "malformed-file"]

    # Each invalid NACCID should produce exactly one malformed-file error
    assert len(malformed_errors) == len(invalid_ids)


# --- Property 3: Error attribution completeness ---


@settings(max_examples=100, deadline=None)
@given(
    resolved_ids=st.lists(naccid_strategy, min_size=1, max_size=5, unique=True),
    unresolved_ids=st.lists(naccid_strategy, min_size=1, max_size=5, unique=True),
)
def test_error_attribution_completeness(resolved_ids, unresolved_ids):
    """For any set of requested NACCIDs where a subset resolves and the
    remainder does not, the error writer contains exactly one no-participant
    error for each unresolved NACCID and zero for resolved ones.

    Validates: Requirements 1.3, 5.1
    """
    # Ensure no overlap between resolved and unresolved
    unresolved_ids = [nid for nid in unresolved_ids if nid not in set(resolved_ids)]
    if not unresolved_ids:
        return

    all_naccids = resolved_ids + unresolved_ids
    csv_content = make_csv_content(all_naccids)

    project_id = "project-123"
    project = create_mock_project(project_id=project_id, label="ingest-form")

    # Create mock subjects only for resolved IDs
    subjects = [
        create_mock_subject(label=nid, subject_id=f"subj-{nid}", project_id=project_id)
        for nid in resolved_ids
    ]

    proxy = create_mock_proxy(
        projects=[project],
        subjects_by_project={project_id: subjects},
    )

    error_writer = ListErrorWriter(container_id="test-id", fw_path="/test/path")

    success, _ = run(
        request_file=csv_content,
        proxy=proxy,
        config=create_gather_config(),
        error_writer=error_writer,
    )

    errors = error_writer.errors()
    no_participant_errors = [e for e in errors if e.error_code == "no-participant"]

    # Should be exactly one error per unresolved NACCID
    assert len(no_participant_errors) == len(unresolved_ids)

    # All unresolved NACCIDs should appear in error messages
    error_messages = " ".join(e.message for e in no_participant_errors)
    for nid in unresolved_ids:
        assert nid in error_messages

    # Success should be False when there are unresolved NACCIDs
    assert success is False


# --- Property 5: Non-positive config parameters rejected ---
#
# These tests exercise the actual validation in GatherFormDataVisitor.create()
# by mocking the dependencies that precede the config validation (GearBotClient,
# InputFileWrapper) and providing a mock GearContext with controlled config opts.


def _create_mock_gear_context(opts: dict) -> Mock:
    """Create a minimal mock GearContext with controlled config opts."""
    context = Mock()
    context.config.opts = {
        "project_names": "ingest-form",
        "modules": "UDS",
        "study_id": "adrc",
        "apikey_path_prefix": "/prod/flywheel/gearbot",
        **opts,
    }
    return context


@settings(max_examples=50, deadline=None)
@given(
    batch_size=st.integers(max_value=0),
)
def test_nonpositive_batch_size_rejected(batch_size):
    """Non-positive batch_size raises GearExecutionError before processing.

    Validates: Requirement 3.3
    """
    context = _create_mock_gear_context({"batch_size": batch_size})

    with (
        patch("gather_form_data_app.run.GearBotClient.create", return_value=Mock()),
        patch("gather_form_data_app.run.InputFileWrapper.create", return_value=Mock()),
        pytest.raises(GearExecutionError, match="batch_size"),
    ):
        GatherFormDataVisitor.create(context=context, parameter_store=Mock())


@settings(max_examples=50, deadline=None)
@given(
    reload_workers=st.integers(max_value=0),
)
def test_nonpositive_reload_workers_rejected(reload_workers):
    """Non-positive reload_workers raises GearExecutionError before processing.

    Validates: Requirement 3.4
    """
    context = _create_mock_gear_context({"reload_workers": reload_workers})

    with (
        patch("gather_form_data_app.run.GearBotClient.create", return_value=Mock()),
        patch("gather_form_data_app.run.InputFileWrapper.create", return_value=Mock()),
        pytest.raises(GearExecutionError, match="reload_workers"),
    ):
        GatherFormDataVisitor.create(context=context, parameter_store=Mock())
