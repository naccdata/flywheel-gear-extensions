"""Tests for the gear visitor."""

import shutil
from unittest.mock import Mock, patch

import pytest

from gear_execution.gear_execution import (
    ClientWrapper,
    GearExecutionError,
    InputFileWrapper,
)
from loni_receipt_metadata_app.run import LoniReceiptMetadataVisitor
from test_mocks.mock_flywheel import MockFlywheelProxy

from .conftest import DATA_DIR, create_acquisition, file_id, mock_client_with_tags

RECEIPT_ID = "receipt-file-id"


class TestCreate:
    @patch("loni_receipt_metadata_app.run.ContextClient.create")
    @patch("loni_receipt_metadata_app.run.InputFileWrapper.create")
    def test_uses_context_client_without_parameter_store(
        self, mock_input: Mock, mock_context_client: Mock
    ):
        context = Mock()
        context.config.opts = {}
        context.manifest.name = "loni-receipt-metadata"

        visitor = LoniReceiptMetadataVisitor.create(context, parameter_store=None)

        assert isinstance(visitor, LoniReceiptMetadataVisitor)
        mock_context_client.assert_called_once_with(context=context)
        mock_input.assert_called_once_with(input_name="input_file", context=context)


def build_visitor(tmp_path, receipt_name: str, proxy, client, *, dry_run=False):
    path = tmp_path / receipt_name
    shutil.copy(DATA_DIR / receipt_name, path)
    file_input = Mock(spec=InputFileWrapper)
    file_input.filepath = str(path)
    file_input.filename = receipt_name
    file_input.file_id = RECEIPT_ID
    wrapper = Mock(spec=ClientWrapper)
    wrapper.get_proxy.return_value = proxy
    wrapper.client = client
    return LoniReceiptMetadataVisitor(
        client=wrapper, file_input=file_input, gear_name="g", dry_run=dry_run
    )


def test_success_writes_and_tags_pass(tmp_path):
    proxy = MockFlywheelProxy()
    acquisition = create_acquisition(proxy, "acq1", {file_id(1): "a.dicom.zip"})
    client = mock_client_with_tags([])
    visitor = build_visitor(tmp_path, "receipt_successful.csv", proxy, client)

    visitor.run(Mock())

    assert list(acquisition.info["upload_loni"]) == [file_id(1)]
    assert acquisition.uploads[0].name == "receipt_successful.csv"
    client.add_file_tags.assert_called_once_with(RECEIPT_ID, body=["g-PASS"])


def test_failed_rows_tag_fail_before_raising(tmp_path):
    proxy = MockFlywheelProxy()
    acquisition = create_acquisition(proxy, "acq1", {file_id(1): "a"})
    client = mock_client_with_tags([])
    visitor = build_visitor(tmp_path, "receipt_failed.csv", proxy, client)

    with pytest.raises(GearExecutionError) as info:
        visitor.run(Mock())

    assert "1 row" in str(info.value)
    client.add_file_tags.assert_called_once_with(RECEIPT_ID, body=["g-FAIL"])
    assert acquisition.info == {}


def test_bad_receipt_raises_before_any_lookup(tmp_path):
    proxy = Mock()
    client = mock_client_with_tags([])
    path = tmp_path / "bad.csv"
    path.write_text("a,b\n1,2\n")
    file_input = Mock(spec=InputFileWrapper)
    file_input.filepath = str(path)
    file_input.filename = "bad.csv"
    file_input.file_id = RECEIPT_ID
    wrapper = Mock(spec=ClientWrapper)
    wrapper.get_proxy.return_value = proxy
    wrapper.client = client
    visitor = LoniReceiptMetadataVisitor(
        client=wrapper, file_input=file_input, gear_name="g"
    )

    with pytest.raises(GearExecutionError) as info:
        visitor.run(Mock())

    assert "Upload ID" in str(info.value)
    proxy.get_file.assert_not_called()
    client.add_file_tags.assert_not_called()


def test_unreadable_receipt_raises(tmp_path):
    wrapper = Mock(spec=ClientWrapper)
    file_input = Mock(spec=InputFileWrapper)
    file_input.filepath = str(tmp_path / "missing.csv")
    file_input.filename = "missing.csv"
    visitor = LoniReceiptMetadataVisitor(
        client=wrapper, file_input=file_input, gear_name="g"
    )

    with pytest.raises(GearExecutionError):
        visitor.run(Mock())


def test_dry_run_writes_nothing(tmp_path, caplog):
    proxy = MockFlywheelProxy()
    acquisition = create_acquisition(proxy, "acq1", {file_id(1): "a"})
    client = mock_client_with_tags([])
    visitor = build_visitor(
        tmp_path, "receipt_successful.csv", proxy, client, dry_run=True
    )

    with caplog.at_level("INFO"):
        visitor.run(Mock())

    assert acquisition.info == {}
    assert acquisition.uploads == []
    client.add_file_tags.assert_not_called()
    client.delete_file_tags.assert_not_called()
    assert "DRY RUN" in caplog.text
