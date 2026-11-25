"""Tests for the Flywheel-bound implementations."""

import logging
from typing import Any
from unittest.mock import Mock

import pytest
from flywheel.rest import ApiException

from gear_execution.gear_execution import GearExecutionError
from loni_receipt_metadata_app.flywheel_io import (
    DryRunAcquisitionTarget,
    DryRunReceiptTagger,
    FlywheelAcquisitionTarget,
    FlywheelFileResolver,
    FlywheelReceiptTagger,
)
from loni_receipt_metadata_app.main import TargetWriteError
from test_mocks.mock_flywheel import (
    MockAcquisition,
    MockFlywheelProxy,
    MockParents,
    create_mock_acquisition_file,
)

from .conftest import create_acquisition, file_id, mock_client_with_tags

ENTRY = {"file_name": "f", "upload_id": "u", "status": "ARCHIVED", "uploads": []}


@pytest.fixture
def proxy() -> MockFlywheelProxy:
    return MockFlywheelProxy()


class TestResolver:
    def test_resolves_with_reloaded_acquisition(self, proxy):
        acquisition = create_acquisition(proxy, "acq1", {file_id(1): "a.dicom.zip"})
        factory = Mock()

        resolved = FlywheelFileResolver(proxy, factory).resolve(file_id(1))

        assert resolved is not None
        assert resolved.file_id == file_id(1)
        assert resolved.file_name == "a.dicom.zip"
        assert resolved.acquisition_id == "acq1"
        assert resolved.acquisition is factory.return_value
        passed = factory.call_args.args[0]
        assert passed.id == acquisition.id
        assert passed is not acquisition  # the reloaded copy

    def test_one_target_per_acquisition(self, proxy):
        create_acquisition(proxy, "acq1", {file_id(1): "a", file_id(2): "b"})
        factory = Mock()
        resolver = FlywheelFileResolver(proxy, factory)

        first = resolver.resolve(file_id(1))
        second = resolver.resolve(file_id(2))

        assert first is not None and second is not None
        assert factory.call_count == 1
        assert first.acquisition is second.acquisition

    def test_unknown_file_returns_none(self, proxy, caplog):
        with caplog.at_level(logging.WARNING):
            assert FlywheelFileResolver(proxy, Mock()).resolve(file_id(9)) is None
        assert file_id(9) in caplog.text

    def test_file_not_in_acquisition_returns_none(self, proxy):
        file = create_mock_acquisition_file("a", file_id(1), "")
        proxy.add_file(file)

        assert FlywheelFileResolver(proxy, Mock()).resolve(file_id(1)) is None

    def test_deleted_file_returns_none(self, proxy):
        create_acquisition(proxy, "acq1", {file_id(1): "a"}, in_acquisition=False)

        assert FlywheelFileResolver(proxy, Mock()).resolve(file_id(1)) is None

    def test_acquisition_lookup_failure_returns_none(self, proxy):
        file = create_mock_acquisition_file("a", file_id(1), "missing-acq")
        proxy.add_file(file)

        assert FlywheelFileResolver(proxy, Mock()).resolve(file_id(1)) is None


def make_target(info=None, files=None) -> MockAcquisition:
    return MockAcquisition(
        id="acq1",
        label="label",
        parents=MockParents(),
        info=info or {},
        files=files or [],
    )


def target_for(acquisition: Any) -> FlywheelAcquisitionTarget:
    return FlywheelAcquisitionTarget(acquisition)


class TestAcquisitionTarget:
    def test_label(self):
        assert target_for(make_target()).label == "label"

    def test_writes_under_upload_loni(self):
        acquisition = make_target()

        target_for(acquisition).write_upload_loni({"x": ENTRY})

        assert acquisition.info == {"upload_loni": {"x": ENTRY}}

    def test_preserves_other_ids_and_replaces_same(self):
        old = {"file_name": "old"}
        acquisition = make_target(
            info={"upload_loni": {"keep": old, "x": old}, "other": 1}
        )

        target_for(acquisition).write_upload_loni({"x": ENTRY})

        assert acquisition.info["upload_loni"] == {"keep": old, "x": ENTRY}
        assert acquisition.info["other"] == 1

    def test_sequential_writes_accumulate(self):
        acquisition = make_target()
        target = target_for(acquisition)

        target.write_upload_loni({"x": ENTRY})
        target.write_upload_loni({"y": ENTRY})

        assert set(acquisition.info["upload_loni"]) == {"x", "y"}

    def test_reloaded_info_none_handled(self):
        acquisition = Mock()
        acquisition.reload.return_value = Mock(info=None)
        target_for(acquisition).write_upload_loni({"x": ENTRY})
        acquisition.update_info.assert_called_once_with({"upload_loni": {"x": ENTRY}})

    def test_write_error_converted(self):
        acquisition = Mock()
        acquisition.reload.return_value = Mock(info={})
        acquisition.update_info.side_effect = ApiException(status=500, reason="boom")

        with pytest.raises(TargetWriteError):
            target_for(acquisition).write_upload_loni({"x": ENTRY})

    def test_attach_passes_file_spec(self):
        acquisition = make_target()

        target_for(acquisition).attach_receipt_copy("r.csv", "a,b")

        (spec,) = acquisition.uploads
        assert spec.name == "r.csv"
        assert spec.content_type == "text/csv"

    def test_attach_replaces_existing(self):
        existing = create_mock_acquisition_file("r.csv", file_id(1), "acq1")
        acquisition = make_target(files=[existing])
        acquisition.conflict_on_upload = True

        target_for(acquisition).attach_receipt_copy("r.csv", "a,b")

        assert acquisition.deleted == ["r.csv"]
        assert len(acquisition.uploads) == 1

    def test_attach_error_converted(self):
        acquisition = Mock()
        acquisition.upload_file.side_effect = ApiException(status=500, reason="boom")

        with pytest.raises(TargetWriteError):
            target_for(acquisition).attach_receipt_copy("r.csv", "a")


class TestDryRunTarget:
    def test_logs_without_writing(self, caplog):
        target = DryRunAcquisitionTarget("label")

        with caplog.at_level(logging.INFO):
            target.write_upload_loni({"x": ENTRY})
            target.attach_receipt_copy("r.csv", '"h"\r\n"v1"\r\n')

        assert target.label == "label"
        assert "upload_loni.x" in caplog.text
        assert "r.csv" in caplog.text
        assert '"v1"' in caplog.text


class TestReceiptTagger:
    def tagger(self, client):
        return FlywheelReceiptTagger(client=client, file_id="rid", gear_name="g")

    def test_pass_adds_tag_and_removes_fail(self):
        client = mock_client_with_tags(["g-FAIL", "x"])

        self.tagger(client).mark(True)

        client.delete_file_tags.assert_called_once_with("rid", body=["g-FAIL"])
        client.add_file_tags.assert_called_once_with("rid", body=["g-PASS"])

    def test_fail_path_without_stale_tag(self):
        client = mock_client_with_tags([])

        self.tagger(client).mark(False)

        client.delete_file_tags.assert_not_called()
        client.add_file_tags.assert_called_once_with("rid", body=["g-FAIL"])

    def test_no_duplicate_add(self):
        client = mock_client_with_tags(["g-PASS"])

        self.tagger(client).mark(True)

        client.add_file_tags.assert_not_called()
        client.delete_file_tags.assert_not_called()

    def test_unknown_tags_clear_unconditionally(self):
        client = mock_client_with_tags(None)

        self.tagger(client).mark(True)

        client.delete_file_tags.assert_called_once_with("rid", body=["g-FAIL"])
        client.add_file_tags.assert_called_once_with("rid", body=["g-PASS"])

    def test_unknown_tags_ignores_delete_failure(self):
        client = mock_client_with_tags(None)
        client.delete_file_tags.side_effect = ApiException(status=404, reason="no")

        self.tagger(client).mark(True)

        client.add_file_tags.assert_called_once_with("rid", body=["g-PASS"])

    def test_add_failure_raises(self):
        client = mock_client_with_tags(None)
        client.add_file_tags.side_effect = ApiException(status=403, reason="no")

        with pytest.raises(GearExecutionError):
            self.tagger(client).mark(True)

    def test_delete_failure_with_known_tags_raises(self):
        client = mock_client_with_tags(["g-FAIL"])
        client.delete_file_tags.side_effect = ApiException(status=403, reason="no")

        with pytest.raises(GearExecutionError):
            self.tagger(client).mark(True)


class TestDryRunTagger:
    def test_logs_tag(self, caplog):
        with caplog.at_level(logging.INFO):
            DryRunReceiptTagger("g").mark(False)

        assert "g-FAIL" in caplog.text
