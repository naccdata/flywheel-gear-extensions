"""Tests for receipt parsing."""

import csv
import io
import logging

import pytest

from loni_receipt_metadata_app.receipt import (
    ReceiptError,
    ReceiptRow,
    parse_receipt,
)

from .conftest import file_id, load_receipt

HEADER = '"Upload ID","Directory","Status","LONI UID","Upload Date"\n'


def parse(text: str):
    return parse_receipt("r.csv", io.StringIO(text, newline=""))


def row(**values: str) -> ReceiptRow:
    return ReceiptRow(values=values)


class TestHeaderValidation:
    @pytest.mark.parametrize("missing", ["Upload ID", "Directory", "Status"])
    def test_missing_column_named(self, missing):
        columns = [c for c in ("Upload ID", "Directory", "Status") if c != missing]
        with pytest.raises(ReceiptError) as info:
            parse(",".join(columns) + "\n")
        assert missing in str(info.value)

    def test_empty_file_misses_all(self):
        with pytest.raises(ReceiptError) as info:
            parse("")
        for column in ("Upload ID", "Directory", "Status"):
            assert column in str(info.value)

    def test_optional_columns_not_required(self):
        receipt = load_receipt("receipt_failed.csv")
        assert "LONI UID" not in receipt.header
        assert len(receipt.rows) == 1

    def test_duplicate_header_last_wins(self, caplog):
        receipt = parse('"Upload ID","Directory","Status","Status"\n"u","d","a","b"\n')
        assert receipt.rows[0].status == "b"
        assert "duplicate" in caplog.text


class TestRows:
    def test_long_row_truncated_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            receipt = parse(HEADER + '"u","d","s","uid","date","extra"\n')
        assert receipt.rows[0].upload_date == "date"
        assert "Row 2" in caplog.text

    def test_short_row_padded(self):
        receipt = parse(HEADER + '"u","d","s"\n')
        assert receipt.rows[0].loni_uid == ""
        assert receipt.rows[0].is_failed

    def test_blank_lines_skipped(self):
        receipt = parse(HEADER + '\n"u","d","s","uid","date"\n\n')
        assert len(receipt.rows) == 1

    def test_header_only_valid_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            receipt = parse(HEADER)
        assert receipt.rows == []
        assert "no rows" in caplog.text

    def test_bom_tolerated_when_decoded(self):
        data = ("\ufeff" + HEADER).encode("utf-8")
        text = data.decode("utf-8-sig")
        assert parse(text).header[0] == "Upload ID"


class TestDirectoryFileId:
    @pytest.mark.parametrize(
        "directory",
        [
            f"/flywheel/v0/work/tmpabc/{file_id(1)}_00002-Name.dicom",
            f"/flywheel/v0/work/tmpabc/{file_id(1)}_name.dicom.zip",
            f"{file_id(1)}_name",
            f"/a/b/{file_id(1)}_",
        ],
    )
    def test_extracted(self, directory):
        assert row(Directory=directory).directory_file_id == file_id(1)

    @pytest.mark.parametrize(
        "directory",
        [
            "/flywheel/v0/work/tmpabc/name.dicom",
            f"/a/{file_id(1)}",
            f"/a/{file_id(1).upper()}_name",
            f"/a/{file_id(1)}x_name",
            f"/{file_id(1)}_dir/name",
            "",
        ],
    )
    def test_not_extracted(self, directory):
        assert row(Directory=directory).directory_file_id is None

    def test_strips_whitespace(self):
        assert row(Directory=f"  /a/{file_id(1)}_n  ").directory_file_id == file_id(1)


GOOD = {
    "Upload ID": "u",
    "Status": "ARCHIVED",
    "LONI UID": "I1",
    "Upload Date": "2026-01-01 00:00:00",
}


class TestRowStatus:
    def test_success(self):
        assert row(**GOOD).is_successful
        assert not row(**GOOD).is_failed

    @pytest.mark.parametrize(
        ("column", "value"),
        [("Upload ID", " "), ("Status", "Duplicate files"), ("Status", "")],
    )
    def test_not_successful(self, column, value):
        values = {**GOOD, column: value}
        assert not row(**values).is_successful
        assert row(**values).is_failed

    @pytest.mark.parametrize("column", ["LONI UID", "Upload Date"])
    def test_blank_or_absent_value_failed(self, column):
        blank = {**GOOD, column: " "}
        absent = {k: v for k, v in GOOD.items() if k != column}
        for values in (blank, absent):
            assert row(**values).is_successful
            assert row(**values).is_failed

    def test_values_stripped(self):
        assert row(Status=" ARCHIVED ", **{"Upload ID": " u "}).is_successful


class TestToCsv:
    def test_header_order_quoting_and_subset(self):
        receipt = load_receipt("receipt_multi_acquisition.csv")
        text = receipt.to_csv(receipt.rows[1:3])

        lines = text.split("\r\n")
        assert lines[0] == ",".join(f'"{c}"' for c in receipt.header)
        parsed = list(csv.reader(io.StringIO(text, newline="")))
        assert parsed[0] == receipt.header
        assert [r[receipt.header.index("LONI UID")] for r in parsed[1:]] == [
            "I10000002",
            "I10000003",
        ]
        assert text.endswith("\r\n")

    def test_roundtrip_values_unstripped(self):
        receipt = parse(HEADER + '"u"," d ","s","uid","date"\n')
        again = parse(receipt.to_csv(receipt.rows))
        assert again.rows[0].values == receipt.rows[0].values
