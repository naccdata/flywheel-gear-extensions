"""Property-based tests for FlywheelProxy.find_subjects_by_labels batching.

Properties tested:
  2. Batching correctness — for N labels and batch_size B, exactly ceil(N/B)
     queries issued, each with at most B labels (Req 1.2)
  4. Resolution preserves multiplicity — NACCID matching K projects produces
     K subject IDs (Req 1.4)
"""

import math
from unittest.mock import Mock

from flywheel.models.subject import Subject
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from hypothesis import given, settings
from hypothesis import strategies as st


def create_proxy_with_mock_fw(find_results=None):
    """Create a FlywheelProxy with a mocked Flywheel client.

    Args:
      find_results: callable or list to use as side_effect for subjects.find
    Returns:
      (proxy, mock_fw) tuple
    """
    mock_fw = Mock()
    if find_results is not None:
        mock_fw.subjects.find.side_effect = find_results
    else:
        mock_fw.subjects.find.return_value = []

    # Access the private __fw attribute by using the mangled name
    proxy = FlywheelProxy.__new__(FlywheelProxy)
    # Set private attributes directly via name mangling
    object.__setattr__(proxy, "_FlywheelProxy__fw", mock_fw)
    object.__setattr__(proxy, "_FlywheelProxy__fw_client", None)
    object.__setattr__(proxy, "_FlywheelProxy__dry_run", False)
    object.__setattr__(proxy, "_FlywheelProxy__project_roles", None)
    object.__setattr__(proxy, "_FlywheelProxy__project_admin_role", None)

    return proxy, mock_fw


# --- Strategy: NACCID-like labels ---
naccid_strategy = st.from_regex(r"NACC\d{6}", fullmatch=True)


# --- Property 2: Batching correctness ---


@settings(max_examples=100)
@given(
    labels=st.lists(naccid_strategy, min_size=1, max_size=50, unique=True),
    batch_size=st.integers(min_value=1, max_value=20),
)
def test_batching_issues_correct_number_of_queries(labels, batch_size):
    """For N labels and batch_size B, exactly ceil(N/B) queries are issued,
    each containing at most B labels in the OR-list.

    Validates: Requirement 1.2
    """
    proxy, mock_fw = create_proxy_with_mock_fw(
        find_results=lambda _query: []  # Return empty for each call
    )

    proxy.find_subjects_by_labels(
        labels=labels,
        project_id="project-123",
        batch_size=batch_size,
    )

    expected_calls = math.ceil(len(labels) / batch_size)
    assert mock_fw.subjects.find.call_count == expected_calls

    # Verify each query has at most batch_size labels
    for call_args in mock_fw.subjects.find.call_args_list:
        query = call_args[0][0]
        # Extract labels from query: "label=|[l1,l2,...],parents.project=..."
        label_part = query.split("label=|[")[1].split("],parents.project=")[0]
        label_list = label_part.split(",")
        assert len(label_list) <= batch_size


@settings(max_examples=100)
@given(
    labels=st.lists(naccid_strategy, min_size=1, max_size=30, unique=True),
    batch_size=st.integers(min_value=1, max_value=15),
)
def test_batching_covers_all_labels(labels, batch_size):
    """All input labels appear in exactly one query batch (no duplicates, no
    omissions).

    Validates: Requirement 1.2 (completeness)
    """
    all_queried_labels: list[str] = []

    def capture_query(query):
        label_part = query.split("label=|[")[1].split("],parents.project=")[0]
        batch_labels = label_part.split(",")
        all_queried_labels.extend(batch_labels)
        return []

    proxy, _mock_fw = create_proxy_with_mock_fw(find_results=capture_query)

    proxy.find_subjects_by_labels(
        labels=labels,
        project_id="project-123",
        batch_size=batch_size,
    )

    # All labels should be covered exactly once
    assert sorted(all_queried_labels) == sorted(labels)


# --- Property 4: Resolution preserves multiplicity ---


@settings(max_examples=100)
@given(
    num_projects=st.integers(min_value=1, max_value=5),
)
def test_resolution_preserves_multiplicity(num_projects):
    """A NACCID matching subjects in K distinct projects produces exactly K
    subject IDs in the result.

    Validates: Requirement 1.4
    """
    naccid = "NACC000001"
    project_ids = [f"project-{i}" for i in range(num_projects)]

    # For each project, find_subjects_by_labels should return 1 subject
    # We call the method once per project (as main.py does)
    all_subjects = []
    for i, project_id in enumerate(project_ids):
        mock_subject = Mock(spec=Subject)
        mock_subject.label = naccid
        mock_subject.id = f"subject-{i}"

        proxy, _mock_fw = create_proxy_with_mock_fw(
            find_results=lambda _query, subj=mock_subject: [subj]
        )

        results = proxy.find_subjects_by_labels(
            labels=[naccid],
            project_id=project_id,
            batch_size=100,
        )
        all_subjects.extend(results)

    # Should have exactly K subject entries
    assert len(all_subjects) == num_projects
    # All should have the same label
    assert all(s.label == naccid for s in all_subjects)
    # But different IDs
    subject_ids = [s.id for s in all_subjects]
    assert len(set(subject_ids)) == num_projects
