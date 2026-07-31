"""Property tests for determine_qc_status.

**Feature: dicom-qc-checker**
"""

from dicom_qc_checker_app.main import determine_qc_status
from hypothesis import given, settings
from hypothesis import strategies as st

# --- Strategies ---

# Valid check state values
_PASS_STATE = st.just("PASS")
_FAIL_STATES = st.text(min_size=1, max_size=10).filter(lambda s: s != "PASS")


@st.composite
def check_result_entry(draw, state_strategy=None):
    """Generate a single check result dict with a state field."""
    if state_strategy is None:
        state_strategy = st.one_of(_PASS_STATE, _FAIL_STATES)
    state = draw(state_strategy)
    # Optionally include extra fields that should be ignored
    extra = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10).filter(lambda k: k != "state"),
            values=st.text(max_size=20),
            max_size=3,
        )
    )
    return {"state": state, **extra}


@st.composite
def non_check_entry(draw):
    """Generate an entry that is NOT a valid check result.

    Either a non-dict value, or a dict without a 'state' key.
    """
    return draw(
        st.one_of(
            st.integers(),
            st.text(max_size=20),
            st.lists(st.integers(), max_size=3),
            st.none(),
            st.booleans(),
            # Dict without 'state' key
            st.dictionaries(
                keys=st.text(min_size=1, max_size=10).filter(lambda k: k != "state"),
                values=st.text(max_size=20),
                max_size=3,
            ),
        )
    )


@st.composite
def dicom_qc_metadata(draw, min_checks=0, max_checks=10, all_pass=None):
    """Generate a DICOM QC metadata dictionary.

    Args:
        min_checks: Minimum number of check result entries.
        max_checks: Maximum number of check result entries.
        all_pass: If True, all checks have state "PASS".
                  If False, at least one check has state != "PASS".
                  If None, random mix.
    """
    num_checks = draw(st.integers(min_value=min_checks, max_value=max_checks))

    result: dict = {}

    # Optionally add job_info with arbitrary content
    if draw(st.booleans()):
        result["job_info"] = draw(
            st.one_of(
                st.dictionaries(
                    keys=st.text(min_size=1, max_size=10),
                    values=st.text(max_size=20),
                    max_size=5,
                ),
                st.text(max_size=20),
                st.integers(),
            )
        )

    # Generate check result entries with unique keys
    check_keys = draw(
        st.lists(
            st.text(
                min_size=1, max_size=15, alphabet="abcdefghijklmnopqrstuvwxyz_"
            ).filter(lambda k: k != "job_info"),
            min_size=num_checks,
            max_size=num_checks,
            unique=True,
        )
    )

    if all_pass is True:
        for key in check_keys:
            result[key] = draw(check_result_entry(state_strategy=_PASS_STATE))
    elif all_pass is False and num_checks > 0:
        # At least one must be non-PASS
        for i, key in enumerate(check_keys):
            if i == 0:
                result[key] = draw(check_result_entry(state_strategy=_FAIL_STATES))
            else:
                result[key] = draw(check_result_entry())
    else:
        for key in check_keys:
            result[key] = draw(check_result_entry())

    # Optionally add non-check entries
    num_non_checks = draw(st.integers(min_value=0, max_value=3))
    non_check_keys = draw(
        st.lists(
            st.text(
                min_size=1, max_size=15, alphabet="abcdefghijklmnopqrstuvwxyz_"
            ).filter(lambda k: k != "job_info" and k not in check_keys),
            min_size=num_non_checks,
            max_size=num_non_checks,
            unique=True,
        )
    )
    for key in non_check_keys:
        result[key] = draw(non_check_entry())

    return result


# --- Property Tests ---


@given(metadata=dicom_qc_metadata(min_checks=1, all_pass=True))
@settings(max_examples=100)
def test_status_pass_when_all_checks_pass(metadata):
    """Property 1: Status determination correctness (all PASS case).

    **Feature: dicom-qc-checker, Property 1: Status determination correctness**
    **Validates: Requirements 2.3, 2.4, 2.6**

    For any metadata dict where every check result has state "PASS",
    status SHALL be "PASS".
    """
    status, problem_checks = determine_qc_status(metadata)

    assert status == "PASS", (
        f"Expected PASS when all checks pass, got {status}. Metadata: {metadata}"
    )
    assert problem_checks == [], (
        f"Expected no problem checks when all pass, got {problem_checks}"
    )


@given(metadata=dicom_qc_metadata(min_checks=1, all_pass=False))
@settings(max_examples=100)
def test_status_fail_when_any_check_not_pass(metadata):
    """Property 1: Status determination correctness (FAIL case).

    **Feature: dicom-qc-checker, Property 1: Status determination correctness**
    **Validates: Requirements 2.3, 2.4, 2.6**

    For any metadata dict where at least one check result has state != "PASS",
    status SHALL be "FAIL".
    """
    status, _ = determine_qc_status(metadata)

    assert status == "FAIL", (
        f"Expected FAIL when a check has non-PASS state, got {status}. "
        f"Metadata: {metadata}"
    )


@given(
    metadata=dicom_qc_metadata(min_checks=1),
    job_info_value=st.one_of(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.text(max_size=20),
            max_size=5,
        ),
        st.text(max_size=20),
        st.integers(),
        st.lists(st.integers(), max_size=3),
    ),
)
@settings(max_examples=100)
def test_job_info_excluded_from_evaluation(metadata, job_info_value):
    """Property 2: Job_info and non-check entry exclusion.

    **Feature: dicom-qc-checker, Property 2: Job_info and non-check entry exclusion**
    **Validates: Requirements 2.1, 2.2**

    Modifying the job_info entry does not change the status result.
    """
    # Get baseline result without job_info modification
    status_before, problems_before = determine_qc_status(metadata)

    # Modify job_info to an arbitrary value
    modified = dict(metadata)
    modified["job_info"] = job_info_value
    status_after, problems_after = determine_qc_status(modified)

    assert status_before == status_after, (
        f"Status changed from {status_before} to {status_after} "
        f"after modifying job_info"
    )
    assert sorted(problems_before) == sorted(problems_after), (
        f"Problem checks changed from {problems_before} to {problems_after} "
        f"after modifying job_info"
    )


@given(
    metadata=dicom_qc_metadata(min_checks=1),
    extra_value=st.one_of(
        st.integers(),
        st.text(max_size=20),
        st.none(),
        st.booleans(),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10).filter(lambda k: k != "state"),
            values=st.text(max_size=20),
            max_size=3,
        ),
    ),
)
@settings(max_examples=100)
def test_non_check_entries_excluded_from_evaluation(metadata, extra_value):
    """Property 2: Non-check entries do not affect status.

    **Feature: dicom-qc-checker, Property 2: Job_info and non-check entry exclusion**
    **Validates: Requirements 2.1, 2.2**

    Adding or modifying entries that are not check results (non-dict values
    or dicts without a 'state' field) does not change the status result.
    """
    status_before, problems_before = determine_qc_status(metadata)

    # Add a non-check entry with a unique key
    modified = dict(metadata)
    modified["zzz_extra_non_check_entry"] = extra_value
    status_after, problems_after = determine_qc_status(modified)

    assert status_before == status_after, (
        f"Status changed from {status_before} to {status_after} "
        f"after adding non-check entry"
    )
    assert sorted(problems_before) == sorted(problems_after), (
        f"Problem checks changed from {problems_before} to {problems_after} "
        f"after adding non-check entry"
    )


@given(metadata=dicom_qc_metadata(min_checks=1, all_pass=False))
@settings(max_examples=100)
def test_failure_reporting_completeness(metadata):
    """Property 3: Failure reporting completeness.

    **Feature: dicom-qc-checker, Property 3: Failure reporting completeness**
    **Validates: Requirements 3.1, 3.2**

    When status is FAIL, problem_checks includes every check key whose
    state != "PASS".
    """
    status, problem_checks = determine_qc_status(metadata)

    assert status == "FAIL"

    # Compute expected problem checks independently
    expected_problems = []
    for key, value in metadata.items():
        if key == "job_info":
            continue
        if not isinstance(value, dict) or "state" not in value:
            continue
        if value["state"] != "PASS":
            expected_problems.append(key)

    assert sorted(problem_checks) == sorted(expected_problems), (
        f"Expected problem checks {sorted(expected_problems)} "
        f"but got {sorted(problem_checks)}"
    )
