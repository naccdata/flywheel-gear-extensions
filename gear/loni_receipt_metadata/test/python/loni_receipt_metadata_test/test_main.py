"""Tests for the receipt processor."""

import csv
import io
import logging

from loni_receipt_metadata_app.main import ReceiptProcessor

from .conftest import RecordingTarget, file_id, load_receipt


def copy_rows(contents: str, column: str = "LONI UID"):
    reader = csv.DictReader(io.StringIO(contents, newline=""))
    return [r[column] for r in reader]


def test_successful_receipt_writes_entry_and_copy(resolver):
    target = RecordingTarget()
    resolver.add(file_id(1), "acq1", target, file_name="mprage.dicom.zip")
    receipt = load_receipt("receipt_successful.csv")

    result = ReceiptProcessor(receipt, resolver).run()

    assert result.passed
    assert target.writes == [
        {
            file_id(1): {
                "file_name": "mprage.dicom.zip",
                "upload_id": "CLARITI_ADC00-1790000000001",
                "status": "ARCHIVED",
                "uploads": [
                    {"loni_uid": "I10000001", "upload_date": "2026-09-21 09:14:51"}
                ],
            }
        }
    ]
    assert target.copies == [(receipt.name, receipt.to_csv(receipt.rows))]


def test_multi_echo_groups_one_upload_in_order(resolver):
    target = RecordingTarget()
    resolver.add(file_id(1), "acq1", target)
    receipt = load_receipt("receipt_multi_echo.csv")

    result = ReceiptProcessor(receipt, resolver).run()

    assert result.passed
    assert resolver.requested == [file_id(1)]
    (entry,) = target.writes[0].values()
    assert entry["uploads"] == [
        {"loni_uid": "I10000001", "upload_date": "2026-09-21 09:14:51"},
        {"loni_uid": "I10000002", "upload_date": "2026-09-21 09:14:54"},
        {"loni_uid": "I10000003", "upload_date": "2026-09-21 09:14:57"},
    ]
    assert set(entry["uploads"][0]) == {"loni_uid", "upload_date"}
    assert len(target.writes) == 1


def test_two_acquisitions_processed_independently(resolver):
    first, second = RecordingTarget("one"), RecordingTarget("two")
    resolver.add(file_id(1), "acq1", first)
    resolver.add(file_id(2), "acq2", second)
    resolver.add(file_id(3), "acq2", second)
    receipt = load_receipt("receipt_multi_acquisition.csv")

    result = ReceiptProcessor(receipt, resolver).run()

    assert result.passed
    assert list(first.writes[0]) == [file_id(1)]
    assert list(second.writes[0]) == [file_id(2), file_id(3)]
    assert copy_rows(first.copies[0][1]) == ["I10000001"]
    assert copy_rows(second.copies[0][1]) == ["I10000002", "I10000003", "I10000004"]
    assert len(first.copies) == len(second.copies) == 1


def test_mixed_upload_has_no_entry_but_row_in_copy(resolver, caplog):
    target = RecordingTarget()
    resolver.add(file_id(1), "acq1", target)
    resolver.add(file_id(2), "acq1", target)
    receipt = load_receipt("receipt_mixed.csv")

    with caplog.at_level(logging.WARNING):
        result = ReceiptProcessor(receipt, resolver).run()

    assert not result.passed
    assert result.failed_rows == 1
    assert list(target.writes[0]) == [file_id(1)]
    assert copy_rows(target.copies[0][1], "Status") == [
        "ARCHIVED",
        "ARCHIVED",
        "Duplicate files",
    ]


def test_acquisition_with_only_failed_uploads_gets_nothing(resolver):
    target = RecordingTarget()
    resolver.add(file_id(1), "acq1", target)
    receipt = load_receipt("receipt_failed.csv")

    result = ReceiptProcessor(receipt, resolver).run()

    assert result.failed_rows == 1
    assert not result.passed
    assert target.writes == []
    assert target.copies == []


def test_unresolved_id_fails_rows_and_processing_continues(resolver, caplog):
    target = RecordingTarget()
    resolver.add(file_id(2), "acq2", target)
    resolver.add(file_id(3), "acq2", target)
    receipt = load_receipt("receipt_multi_acquisition.csv")

    with caplog.at_level(logging.WARNING):
        result = ReceiptProcessor(receipt, resolver).run()

    assert result.failed_rows == 1
    assert list(target.writes[0]) == [file_id(2), file_id(3)]
    assert caplog.text.count(file_id(1)) == 1
    assert "ARCHIVED" in caplog.text


def test_directory_without_file_id_fails_and_logs_directory(resolver, caplog):
    receipt = load_receipt("receipt_successful.csv")
    bad = receipt.rows[0].values | {"Directory": "/tmp/no_id_here"}
    receipt = type(receipt)(
        name=receipt.name,
        header=receipt.header,
        rows=[type(receipt.rows[0])(values=bad)],
    )

    with caplog.at_level(logging.WARNING):
        result = ReceiptProcessor(receipt, resolver).run()

    assert result.failed_rows == 1
    assert resolver.requested == []
    assert "/tmp/no_id_here" in caplog.text
    assert "ARCHIVED" in caplog.text


def test_failed_row_warning_has_file_id_and_status_once(resolver, caplog):
    resolver.add(file_id(1), "acq1", RecordingTarget())
    resolver.add(file_id(2), "acq1", RecordingTarget())
    receipt = load_receipt("receipt_mixed.csv")

    with caplog.at_level(logging.WARNING):
        ReceiptProcessor(receipt, resolver).run()

    messages = [r.getMessage() for r in caplog.records if file_id(2) in r.getMessage()]
    assert len(messages) == 1
    assert "Duplicate files" in messages[0]


def test_write_error_fails_all_rows_of_acquisition_and_continues(resolver, caplog):
    broken = RecordingTarget("broken", fail_write=True)
    fine = RecordingTarget("fine")
    resolver.add(file_id(1), "acq1", broken)
    resolver.add(file_id(2), "acq2", fine)
    resolver.add(file_id(3), "acq2", fine)
    receipt = load_receipt("receipt_multi_acquisition.csv")

    with caplog.at_level(logging.WARNING):
        result = ReceiptProcessor(receipt, resolver).run()

    assert result.failed_rows == 1
    assert not result.passed
    assert fine.writes and fine.copies
    assert broken.copies == []
    assert any(
        r.levelno == logging.ERROR and "broken" in r.getMessage()
        for r in caplog.records
    )
    assert caplog.text.count(file_id(1)) == 1


def test_write_error_does_not_double_count_failed_rows(resolver, caplog):
    target = RecordingTarget(fail_write=True)
    resolver.add(file_id(1), "acq1", target)
    resolver.add(file_id(2), "acq1", target)
    receipt = load_receipt("receipt_mixed.csv")

    with caplog.at_level(logging.WARNING):
        result = ReceiptProcessor(receipt, resolver).run()

    # 3 rows total, the third already failed by itself
    assert result.failed_rows == 3
    messages = [r.getMessage() for r in caplog.records if file_id(2) in r.getMessage()]
    assert len(messages) == 2  # one warning per row of file 2, no repeats


def test_copy_failure_after_write_keeps_entries_and_fails_rows(resolver):
    target = RecordingTarget(fail_copy=True)
    resolver.add(file_id(1), "acq1", target)
    receipt = load_receipt("receipt_multi_echo.csv")

    result = ReceiptProcessor(receipt, resolver).run()

    assert len(target.writes) == 1
    assert target.copies == []
    assert result.failed_rows == 3
    assert not result.passed


def test_mismatched_upload_id_uses_first_row_with_warning(resolver, caplog):
    target = RecordingTarget()
    resolver.add(file_id(1), "acq1", target)
    receipt = load_receipt("receipt_multi_echo.csv")
    changed = receipt.rows[1].values | {"Upload ID": "OTHER-ID"}
    rows = list(receipt.rows)
    rows[1] = type(rows[1])(values=changed)
    receipt = type(receipt)(name=receipt.name, header=receipt.header, rows=rows)

    with caplog.at_level(logging.WARNING):
        result = ReceiptProcessor(receipt, resolver).run()

    assert result.passed
    assert target.writes[0][file_id(1)]["upload_id"] == "CLARITI_ADC00-1790000000001"
    assert "differ" in caplog.text


def test_copy_uses_receipt_name(resolver):
    target = RecordingTarget()
    resolver.add(file_id(1), "acq1", target)
    receipt = load_receipt("receipt_successful.csv")

    ReceiptProcessor(receipt, resolver).run()

    assert target.copies[0][0] == "receipt_successful.csv"


def test_header_only_receipt_passes(resolver):
    receipt = load_receipt("receipt_successful.csv")
    empty = type(receipt)(name="e.csv", header=receipt.header, rows=[])

    assert ReceiptProcessor(empty, resolver).run().passed
