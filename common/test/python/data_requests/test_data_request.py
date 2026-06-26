from unittest.mock import MagicMock

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
