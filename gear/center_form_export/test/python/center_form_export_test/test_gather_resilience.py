"""Property test for resilience of data gathering.

Verifies that the gathering loop calls every configured gatherer exactly
once for the project, and that an unexpected (non-ModuleDataError)
exception from a gatherer propagates rather than being silently swallowed.

Per-file resilience to ModuleDataError now lives inside
``ModuleDataGatherer.gather_project_data`` (see
``common/test/python/data_requests/test_data_request.py``), since that
method — not ``main.run()`` — issues the batched, subject-scoped queries
and iterates the returned files.

**Feature: center-form-export,
  Property 3: All modules processed with resilience**
**Validates: Requirements 4.2, 4.3, 4.4**
"""

from unittest.mock import Mock, patch

import pytest
from center_form_export_app.main import run
from data_requests.data_request import ModuleDataGatherer
from hypothesis import given, settings
from hypothesis import strategies as st

MODULE_NAMES = ["UDS", "FTLD", "LBD"]


def mock_gatherer(module_name: str) -> Mock:
    """Create a mock ModuleDataGatherer."""
    mock = Mock(spec=ModuleDataGatherer)
    mock.module_name = module_name
    return mock


class TestGatherResilience:
    """Property tests for module-level data gathering."""

    @given(num_gatherers=st.integers(min_value=0, max_value=5))
    @settings(max_examples=50)
    def test_always_returns_true(self, num_gatherers: int):
        """run() always returns True when no gatherer raises.

        **Validates: Requirements 4.3**
        """
        gatherers = [
            mock_gatherer(MODULE_NAMES[i % len(MODULE_NAMES)])
            for i in range(num_gatherers)
        ]

        with patch("center_form_export_app.main.log"):
            result = run(subject_ids=["sub-1"], gatherers=gatherers)  # type: ignore[arg-type]

        assert result is True

    @given(num_gatherers=st.integers(min_value=1, max_value=5))
    @settings(max_examples=50)
    def test_every_gatherer_called_once_with_subject_ids(self, num_gatherers: int):
        """Every gatherer's gather_project_data is called exactly once, with
        the resolved subject ids.

        **Validates: Requirements 3.3**
        """
        gatherers = [
            mock_gatherer(MODULE_NAMES[i % len(MODULE_NAMES)])
            for i in range(num_gatherers)
        ]
        subject_ids = ["sub-1", "sub-2"]

        with patch("center_form_export_app.main.log"):
            run(subject_ids=subject_ids, gatherers=gatherers)  # type: ignore[arg-type]

        for gatherer in gatherers:
            gatherer.gather_project_data.assert_called_once_with(subject_ids)

    def test_unexpected_error_propagates(self):
        """An unexpected (non-ModuleDataError) exception from a gatherer is not
        swallowed by run().

        **Validates: Requirements 4.4**
        """
        failing = mock_gatherer("UDS")
        failing.gather_project_data.side_effect = RuntimeError("boom")
        ok = mock_gatherer("FTLD")

        with (
            patch("center_form_export_app.main.log"),
            pytest.raises(RuntimeError, match="boom"),
        ):
            run(subject_ids=["sub-1"], gatherers=[failing, ok])  # type: ignore[arg-type]

        ok.gather_project_data.assert_not_called()

    def test_on_module_gathered_called_once_per_gatherer_in_order(self):
        """The callback fires once per gatherer, immediately after that
        gatherer's data is gathered, in gatherer order -- not batched until the
        end.

        **Validates: Requirements written re: incremental output writing**
        """
        gatherers = [mock_gatherer("UDS"), mock_gatherer("FTLD"), mock_gatherer("LBD")]
        calls = []

        def record_call(gatherer):
            calls.append(gatherer.module_name)
            # Assert the gatherer this callback fired for has already been
            # gathered, but nothing later in the list has been touched yet.
            gatherer.gather_project_data.assert_called_once()
            for later in gatherers[len(calls) :]:
                later.gather_project_data.assert_not_called()

        with patch("center_form_export_app.main.log"):
            run(
                subject_ids=["sub-1"],
                gatherers=gatherers,  # type: ignore[arg-type]
                on_module_gathered=record_call,
            )

        assert calls == ["UDS", "FTLD", "LBD"]

    def test_on_module_gathered_error_propagates_and_halts(self):
        """If the callback raises (e.g. a write failure), the exception
        propagates and remaining gatherers are not processed."""
        gatherers = [mock_gatherer("UDS"), mock_gatherer("FTLD")]

        def failing_callback(gatherer):
            raise OSError("disk full")

        with (
            patch("center_form_export_app.main.log"),
            pytest.raises(OSError, match="disk full"),
        ):
            run(
                subject_ids=["sub-1"],
                gatherers=gatherers,  # type: ignore[arg-type]
                on_module_gathered=failing_callback,
            )

        gatherers[1].gather_project_data.assert_not_called()

    def test_on_module_gathered_is_optional(self):
        """run() works with no callback at all (the default)."""
        gatherers = [mock_gatherer("UDS")]

        with patch("center_form_export_app.main.log"):
            result = run(subject_ids=["sub-1"], gatherers=gatherers)  # type: ignore[arg-type]

        assert result is True

    def test_batch_size_and_reload_workers_passed_through_when_given(self):
        """When batch_size/reload_workers are provided, they're forwarded to
        gather_project_data."""
        gatherer = mock_gatherer("UDS")

        with patch("center_form_export_app.main.log"):
            run(
                subject_ids=["sub-1"],
                gatherers=[gatherer],  # type: ignore[arg-type]
                batch_size=250,
                reload_workers=5,
            )

        gatherer.gather_project_data.assert_called_once_with(
            ["sub-1"], batch_size=250, reload_workers=5
        )

    def test_batch_size_and_reload_workers_omitted_when_not_given(self):
        """When batch_size/reload_workers are not provided, they're left out of
        the call entirely, so gather_project_data's own defaults apply."""
        gatherer = mock_gatherer("UDS")

        with patch("center_form_export_app.main.log"):
            run(subject_ids=["sub-1"], gatherers=[gatherer])  # type: ignore[arg-type]

        gatherer.gather_project_data.assert_called_once_with(["sub-1"])
