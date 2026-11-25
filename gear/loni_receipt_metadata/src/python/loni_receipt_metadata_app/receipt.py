"""Parsing of receipt CSV files written by the loni-upload gear.

Pure Python: no Flywheel dependencies.
"""

import csv
import io
import logging
import posixpath
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, TextIO

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("Upload ID", "Directory", "Status")

# Keep in sync with LONI_PROGRESS_SUCCESS_STATUS in
# fw-loni-export/fw_gear_loni_upload/constants.py
SUCCESS_STATUSES = frozenset({"ARCHIVED"})

_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{24}(?=_)")


class ReceiptError(Exception):
    """Raised when a receipt is malformed."""


@dataclass(frozen=True)
class ReceiptRow:
    """A row of a receipt.

    Attributes:
      values: raw (unstripped) cell values by column name
    """

    values: Dict[str, str]

    def _stripped(self, column: str) -> str:
        return self.values.get(column, "").strip()

    @property
    def upload_id(self) -> str:
        return self._stripped("Upload ID")

    @property
    def status(self) -> str:
        return self._stripped("Status")

    @property
    def loni_uid(self) -> str:
        return self._stripped("LONI UID")

    @property
    def upload_date(self) -> str:
        return self._stripped("Upload Date")

    @property
    def directory(self) -> str:
        return self._stripped("Directory")

    @property
    def directory_file_id(self) -> Optional[str]:
        """The Flywheel file ID at the start of the directory name, if any."""
        match = _FILE_ID_PATTERN.match(posixpath.basename(self.directory))
        return match.group(0) if match else None

    @property
    def is_successful(self) -> bool:
        return bool(self.upload_id) and self.status in SUCCESS_STATUSES

    @property
    def is_failed(self) -> bool:
        return not self.is_successful or not self.loni_uid or not self.upload_date


@dataclass(frozen=True)
class Receipt:
    """A parsed receipt."""

    name: str
    header: List[str]
    rows: List[ReceiptRow]

    def to_csv(self, rows: Sequence[ReceiptRow]) -> str:
        """Writes the header and the given rows as CSV text.

        Args:
          rows: the rows to include
        Returns:
          the CSV text with all fields quoted
        """
        output = io.StringIO(newline="")
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow(self.header)
        for row in rows:
            writer.writerow([row.values.get(column, "") for column in self.header])
        return output.getvalue()


def parse_receipt(name: str, stream: TextIO) -> Receipt:
    """Parses a receipt.

    Args:
      name: the name of the receipt file
      stream: text stream with the receipt CSV
    Returns:
      the parsed receipt
    Raises:
      ReceiptError: if required columns are missing
    """
    reader = csv.reader(stream)
    header = next(reader, [])
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise ReceiptError(
            f"Receipt {name} is missing required columns: {', '.join(missing)}"
        )

    duplicates = sorted({column for column in header if header.count(column) > 1})
    if duplicates:
        log.warning(
            "Receipt %s has duplicate columns %s; using the last of each",
            name,
            ", ".join(duplicates),
        )

    rows: List[ReceiptRow] = []
    for cells in reader:
        if not cells:
            continue

        if len(cells) > len(header):
            log.warning(
                "Row %d of receipt %s has %d cells but header has %d; "
                "ignoring extra cells",
                reader.line_num,
                name,
                len(cells),
                len(header),
            )
            cells = cells[: len(header)]
        elif len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))

        rows.append(ReceiptRow(values=dict(zip(header, cells, strict=True))))

    if not rows:
        log.warning("Receipt %s has no rows", name)

    return Receipt(name=name, header=header, rows=rows)
