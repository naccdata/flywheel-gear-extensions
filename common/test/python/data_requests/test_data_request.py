import logging
import time
from unittest.mock import MagicMock, patch

import pytest
from data_requests.data_request import (
    DataRequest,
    ModuleDataGatherer,
    formver_label,
)


class TestDataRequest:
    def test_case(self):
        request = DataRequest.model_validate({"NACCID": "NACC000000"})
        assert request == DataRequest(naccid="NACC000000")


class TestFormverLabel:
    """Normalization of form version values into filename-safe labels."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("1", "v1"),
            ("1.0", "v1"),
            ("1.5", "v1.5"),
            ("2", "v2"),
            ("3.0", "v3"),
            ("4.0", "v4"),
            ("4", "v4"),
            ("", "unknown"),
            ("   ", "unknown"),
            (None, "unknown"),
            (1.0, "v1"),  # numeric input — coerced via str()
            (3, "v3"),
        ],
    )
    def test_label(self, raw, expected):
        assert formver_label(raw) == expected


def _make_file_mock(merged_data: dict, file_id: str = "fake-file-id"):
    """Build a mock FileEntry whose reload().info contains a 'forms.json' key
    matching ``merged_data``."""
    file_mock = MagicMock()
    file_mock.file_id = file_id
    reloaded = MagicMock()
    reloaded.info = {"forms.json": merged_data}
    reloaded.file_id = file_id
    file_mock.reload.return_value = reloaded
    return file_mock


class TestModuleDataGathererSingleWriter:
    """Default mode (split_by_formver=False) — backward-compatible."""

    def test_content_returns_csv_string(self):
        gatherer = ModuleDataGatherer(
            proxy=MagicMock(),
            module_name="UDS",
            info_paths=["forms.json"],
        )
        gatherer.gather_file_info(
            _make_file_mock({"naccid": "NACC0001", "formver": "4.0", "field_a": "x"})
        )
        content = gatherer.content
        assert "naccid" in content
        assert "NACC0001" in content
        assert "field_a" in content

    def test_content_by_formver_raises_in_default_mode(self):
        gatherer = ModuleDataGatherer(
            proxy=MagicMock(),
            module_name="UDS",
            info_paths=["forms.json"],
        )
        with pytest.raises(AttributeError, match="split_by_formver=False"):
            _ = gatherer.content_by_formver

    def test_split_by_formver_property_reports_false(self):
        gatherer = ModuleDataGatherer(
            proxy=MagicMock(),
            module_name="UDS",
            info_paths=["forms.json"],
        )
        assert gatherer.split_by_formver is False


class TestModuleDataGathererFormverSplit:
    """split_by_formver=True groups rows by formver into separate writers, each
    with its own column set."""

    def _build_with_rows(self, rows: list[dict], module_name: str = "UDS"):
        gatherer = ModuleDataGatherer(
            proxy=MagicMock(),
            module_name=module_name,
            info_paths=["forms.json"],
            split_by_formver=True,
        )
        for row in rows:
            gatherer.gather_file_info(_make_file_mock(row))
        return gatherer

    def test_split_by_formver_property_reports_true(self):
        gatherer = ModuleDataGatherer(
            proxy=MagicMock(),
            module_name="UDS",
            info_paths=["forms.json"],
            split_by_formver=True,
        )
        assert gatherer.split_by_formver is True

    def test_content_raises_in_split_mode(self):
        gatherer = self._build_with_rows([{"formver": "4.0"}])
        with pytest.raises(AttributeError, match="split_by_formver=True"):
            _ = gatherer.content

    def test_separates_rows_by_formver(self):
        gatherer = self._build_with_rows(
            [
                {"naccid": "NACC0001", "formver": "3.0", "v3_field": "a"},
                {"naccid": "NACC0002", "formver": "3.0", "v3_field": "b"},
                {"naccid": "NACC0003", "formver": "4.0", "v4_field": "c"},
            ]
        )
        buckets = gatherer.content_by_formver
        assert set(buckets.keys()) == {"v3", "v4"}
        assert "NACC0001" in buckets["v3"]
        assert "NACC0002" in buckets["v3"]
        assert "NACC0003" in buckets["v4"]
        assert "NACC0003" not in buckets["v3"]
        assert "NACC0001" not in buckets["v4"]

    def test_each_bucket_has_its_own_column_set(self):
        """A row's columns only appear in its own formver bucket — no cross-
        version sparse columns."""
        gatherer = self._build_with_rows(
            [
                {"naccid": "NACC0001", "formver": "3.0", "v3_only_field": "a"},
                {"naccid": "NACC0002", "formver": "4.0", "v4_only_field": "b"},
            ]
        )
        buckets = gatherer.content_by_formver
        # Each bucket's header should include only that bucket's columns
        v3_header = buckets["v3"].splitlines()[0]
        v4_header = buckets["v4"].splitlines()[0]
        assert "v3_only_field" in v3_header
        assert "v3_only_field" not in v4_header
        assert "v4_only_field" in v4_header
        assert "v4_only_field" not in v3_header

    def test_missing_formver_routes_to_unknown_bucket(self):
        gatherer = self._build_with_rows(
            [
                {"naccid": "NACC0001", "field_a": "value"},  # no formver
                {"naccid": "NACC0002", "formver": "", "field_a": "value2"},
                {"naccid": "NACC0003", "formver": "4.0", "v4_field": "c"},
            ]
        )
        buckets = gatherer.content_by_formver
        assert "unknown" in buckets
        assert "v4" in buckets
        assert "NACC0001" in buckets["unknown"]
        assert "NACC0002" in buckets["unknown"]
        assert "NACC0003" not in buckets["unknown"]

    def test_normalizes_formver_to_label(self):
        gatherer = self._build_with_rows(
            [
                {"naccid": "NACC0001", "formver": "1.0", "f1": "a"},
                {"naccid": "NACC0002", "formver": "1.5", "f15": "b"},
                {"naccid": "NACC0003", "formver": "2", "f2": "c"},
            ]
        )
        buckets = gatherer.content_by_formver
        assert set(buckets.keys()) == {"v1", "v1.5", "v2"}

    def test_no_rows_yields_empty_dict(self):
        gatherer = ModuleDataGatherer(
            proxy=MagicMock(),
            module_name="UDS",
            info_paths=["forms.json"],
            split_by_formver=True,
        )
        assert gatherer.content_by_formver == {}


class TestModuleDataGathererProjectQuery:
    """gather_project_data batches subject ids into OR-list-filtered queries,
    instead of one query per subject or one unscoped query for the whole
    project."""

    def test_single_batch_query_uses_or_list_filter(self):
        proxy = MagicMock()
        proxy.get_files.return_value = []
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        gatherer.gather_project_data(["sub-1", "sub-2", "sub-3"])

        proxy.get_files.assert_called_once_with(
            "parent_ref.type=acquisition,parents.subject=|[sub-1,sub-2,sub-3],"
            "acquisition.label=UDS"
        )

    def test_batches_subjects_by_batch_size(self):
        """More subjects than batch_size results in multiple queries, each
        scoped to its own batch."""
        proxy = MagicMock()
        proxy.get_files.return_value = []
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )
        subject_ids = [f"sub-{i}" for i in range(5)]

        gatherer.gather_project_data(subject_ids, batch_size=2)

        assert proxy.get_files.call_count == 3
        calls = [call.args[0] for call in proxy.get_files.call_args_list]
        assert "parents.subject=|[sub-0,sub-1]" in calls[0]
        assert "parents.subject=|[sub-2,sub-3]" in calls[1]
        assert "parents.subject=|[sub-4]" in calls[2]

    def test_processes_every_returned_file_across_batches(self):
        proxy = MagicMock()
        proxy.get_files.side_effect = [
            [_make_file_mock({"naccid": "NACC0001", "field_a": "x"}, "file-1")],
            [_make_file_mock({"naccid": "NACC0002", "field_a": "y"}, "file-2")],
        ]
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        gatherer.gather_project_data(["sub-1", "sub-2"], batch_size=1)

        content = gatherer.content
        assert "NACC0001" in content
        assert "NACC0002" in content

    def test_skips_and_logs_files_that_fail_without_halting(self, caplog):
        """A file that raises ModuleDataError is logged and skipped; the
        remaining files (including in later batches) are still processed.

        **Validates: Requirements 4.1, 4.2**
        """
        good_file = _make_file_mock({"naccid": "NACC0001", "field_a": "x"}, "file-1")
        bad_file = MagicMock()
        bad_file.file_id = "file-2"
        bad_reloaded = MagicMock()
        bad_reloaded.info = {}  # missing "forms.json" -> ModuleDataError
        bad_reloaded.file_id = "file-2"
        bad_file.reload.return_value = bad_reloaded

        proxy = MagicMock()
        proxy.get_files.return_value = [bad_file, good_file]
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        with caplog.at_level(logging.WARNING):
            gatherer.gather_project_data(["sub-1"])

        assert "NACC0001" in gatherer.content
        assert "Failed to load data" in caplog.text

    def test_reloads_files_within_a_batch_concurrently(self):
        """Reloading N files takes much less than N times a single reload's
        duration, confirming reloads within a batch run in parallel rather than
        serially."""

        def make_slow_file(file_id: str) -> MagicMock:
            file_mock = MagicMock()
            file_mock.file_id = file_id

            def slow_reload():
                time.sleep(0.1)
                reloaded = MagicMock()
                reloaded.info = {"forms.json": {"naccid": file_id}}
                reloaded.file_id = file_id
                return reloaded

            file_mock.reload.side_effect = slow_reload
            return file_mock

        proxy = MagicMock()
        proxy.get_files.return_value = [make_slow_file(f"file-{i}") for i in range(10)]
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        start = time.time()
        gatherer.gather_project_data(["sub-1"])
        elapsed = time.time() - start

        # Serial would take >= 1.0s (10 * 0.1s); concurrent should be a
        # small fraction of that.
        assert elapsed < 0.5

    def test_unexpected_reload_error_propagates(self):
        """An error raised by file.reload() itself (not a ModuleDataError) is
        not swallowed.

        **Validates: Requirements 4.4**
        """
        bad_file = MagicMock()
        bad_file.file_id = "file-1"
        bad_file.reload.side_effect = ConnectionError("network broke")

        proxy = MagicMock()
        proxy.get_files.return_value = [bad_file]
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        with pytest.raises(ConnectionError, match="network broke"):
            gatherer.gather_project_data(["sub-1"])

    def test_no_subjects_issues_no_queries(self):
        proxy = MagicMock()
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        gatherer.gather_project_data([])

        proxy.get_files.assert_not_called()

    def test_reload_workers_is_configurable(self):
        """The reload_workers param controls the thread pool's max_workers, not
        just an internal, unconfigurable constant."""
        proxy = MagicMock()
        proxy.get_files.return_value = []
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )

        with patch("data_requests.data_request.ThreadPoolExecutor") as mock_pool_cls:
            mock_pool_cls.return_value.__enter__.return_value.map.return_value = []
            gatherer.gather_project_data(["sub-1"], reload_workers=3)

        mock_pool_cls.assert_called_once_with(max_workers=3)

    def test_thread_pool_reused_across_batches_not_recreated_per_batch(self):
        """One ThreadPoolExecutor is created for the whole gather_project_data
        call, not once per batch."""
        proxy = MagicMock()
        proxy.get_files.return_value = []
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name="UDS",
            info_paths=["forms.json"],
        )
        subject_ids = [f"sub-{i}" for i in range(25)]

        with patch("data_requests.data_request.ThreadPoolExecutor") as mock_pool_cls:
            mock_pool_cls.return_value.__enter__.return_value.map.return_value = []
            gatherer.gather_project_data(subject_ids, batch_size=10)

        # 3 batches (10, 10, 5), but only one pool for the whole call.
        assert proxy.get_files.call_count == 3
        mock_pool_cls.assert_called_once()
