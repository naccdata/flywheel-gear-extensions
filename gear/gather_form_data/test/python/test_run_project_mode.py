"""Property test for resilience of run_project_mode.

**Feature: gather-form-data-project-mode,
  Property 4: All subjects processed with resilience**
**Validates: Requirements 4.2, 5.1, 5.3, 5.4, 8.2**
"""

from unittest.mock import Mock, patch

from data_requests.data_request import (
    DataRequestMatch,
    ModuleDataError,
    ModuleDataGatherer,
)
from gather_form_data_app.main import run_project_mode
from hypothesis import given, settings
from hypothesis import strategies as st


def data_request_match_strategy() -> st.SearchStrategy[DataRequestMatch]:
    """Strategy to generate DataRequestMatch objects."""
    return st.builds(
        DataRequestMatch,
        naccid=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=10,
        ),
        subject_id=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
        project_label=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
            min_size=1,
            max_size=30,
        ),
    )


def mock_gatherer_strategy(raises: bool, module_name: str) -> Mock:
    """Create a mock ModuleDataGatherer that either succeeds or raises."""
    mock = Mock(spec=ModuleDataGatherer)
    mock.module_name = module_name
    if raises:
        mock.gather_request_data.side_effect = ModuleDataError(
            f"Simulated error for {module_name}"
        )
    return mock


MODULE_NAMES = ["UDS", "FTLD", "LBD"]


class TestRunProjectModeResilience:
    """Property tests for run_project_mode resilience.

    Verifies that run_project_mode always returns True regardless of
    whether individual gatherers raise ModuleDataError, and that all
    request-gatherer combinations are attempted.
    """

    @given(
        requests=st.lists(
            data_request_match_strategy(),
            min_size=0,
            max_size=5,
        ),
        failure_mask=st.lists(
            st.booleans(),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=200)
    def test_always_returns_true(
        self,
        requests: list[DataRequestMatch],
        failure_mask: list[bool],
    ):
        """run_project_mode always returns True regardless of gatherer
        failures.

        **Feature: gather-form-data-project-mode,
          Property 4: All subjects processed with resilience**
        **Validates: Requirements 4.2, 5.1**
        """
        gatherers = [
            mock_gatherer_strategy(
                raises=failure_mask[i % len(failure_mask)],
                module_name=MODULE_NAMES[i % len(MODULE_NAMES)],
            )
            for i in range(len(failure_mask))
        ]

        with patch("gather_form_data_app.main.log"):
            result = run_project_mode(requests=requests, gatherers=gatherers)  # type: ignore[arg-type]

        assert result is True

    @given(
        requests=st.lists(
            data_request_match_strategy(),
            min_size=1,
            max_size=5,
        ),
        failure_mask=st.lists(
            st.booleans(),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=200)
    def test_all_combinations_attempted(
        self,
        requests: list[DataRequestMatch],
        failure_mask: list[bool],
    ):
        """All request-gatherer combinations are attempted even when some fail.

        **Feature: gather-form-data-project-mode,
          Property 4: All subjects processed with resilience**
        **Validates: Requirements 5.3, 5.4, 8.2**
        """
        gatherers = [
            mock_gatherer_strategy(
                raises=failure_mask[i % len(failure_mask)],
                module_name=MODULE_NAMES[i % len(MODULE_NAMES)],
            )
            for i in range(len(failure_mask))
        ]

        with patch("gather_form_data_app.main.log"):
            run_project_mode(requests=requests, gatherers=gatherers)  # type: ignore[arg-type]

        # Every gatherer should be called once for every request
        for gatherer in gatherers:
            assert gatherer.gather_request_data.call_count == len(requests)

        # Verify each request was passed to each gatherer
        for gatherer in gatherers:
            called_requests = [
                call.args[0] for call in gatherer.gather_request_data.call_args_list
            ]
            for request in requests:
                assert request in called_requests

    @given(
        requests=st.lists(
            data_request_match_strategy(),
            min_size=2,
            max_size=5,
        ),
        num_gatherers=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=200)
    def test_exception_does_not_prevent_other_subjects(
        self,
        requests: list[DataRequestMatch],
        num_gatherers: int,
    ):
        """Exceptions from one subject don't prevent processing of others.

        All gatherers raise for the first request but succeed for the rest.
        Verifies remaining subjects are still processed.

        **Feature: gather-form-data-project-mode,
          Property 4: All subjects processed with resilience**
        **Validates: Requirements 5.1, 5.4**
        """
        first_request = requests[0]
        gatherers: list = []

        for i in range(num_gatherers):
            mock = Mock(spec=ModuleDataGatherer)
            mock.module_name = MODULE_NAMES[i % len(MODULE_NAMES)]

            def make_side_effect(req_to_fail):
                def side_effect(req):
                    if req == req_to_fail:
                        raise ModuleDataError("Simulated failure")

                return side_effect

            mock.gather_request_data.side_effect = make_side_effect(first_request)
            gatherers.append(mock)

        with patch("gather_form_data_app.main.log"):
            result = run_project_mode(requests=requests, gatherers=gatherers)  # type: ignore[arg-type]

        assert result is True

        # All gatherers should still be called for all requests
        for gatherer in gatherers:
            assert gatherer.gather_request_data.call_count == len(requests)
