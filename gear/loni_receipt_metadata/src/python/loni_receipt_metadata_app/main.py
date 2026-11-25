"""Core logic for recording LONI receipt metadata on acquisitions.

Has no dependency on the gear context or Flywheel.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, Set, Tuple

from .receipt import Receipt, ReceiptRow

log = logging.getLogger(__name__)


class TargetWriteError(Exception):
    """A write to an acquisition failed.

    Raised by AcquisitionTarget implementations.
    """


class AcquisitionTarget(Protocol):
    """Writes receipt-derived data to one acquisition."""

    @property
    def label(self) -> str:
        """The acquisition label."""
        ...

    def write_upload_loni(self, entries: Mapping[str, Dict[str, Any]]) -> None:
        """Writes entries to `info.upload_loni`, keyed by file ID.

        Entries for other file IDs are left unchanged.
        """
        ...

    def attach_receipt_copy(self, name: str, contents: str) -> None:
        """Uploads a file with the name; a same-name file gains a new
        version."""
        ...


@dataclass(frozen=True)
class ResolvedFile:
    """A file ID resolved to the acquisition containing it."""

    file_id: str
    file_name: str
    acquisition_id: str
    acquisition: AcquisitionTarget


class FileResolver(Protocol):
    """Resolves file IDs to acquisitions."""

    def resolve(self, file_id: str) -> Optional[ResolvedFile]:
        """Resolves the file ID.

        Returns:
          the resolved file, or None if the ID is not a file in an acquisition
        """
        ...


class ReceiptTagger(Protocol):
    """Tags the input receipt with the outcome."""

    def mark(self, passed: bool) -> None:
        """Tags the receipt as passed or failed."""
        ...


@dataclass(frozen=True)
class ReceiptResult:
    """Outcome of processing a receipt."""

    failed_rows: int

    @property
    def passed(self) -> bool:
        return self.failed_rows == 0


@dataclass
class _Upload:
    file_id: str
    rows: List[Tuple[int, ReceiptRow]]
    resolved: ResolvedFile
    entry: Optional[Dict[str, Any]] = None


@dataclass
class _AcquisitionGroup:
    target: AcquisitionTarget
    uploads: List[_Upload] = field(default_factory=list)


class ReceiptProcessor:
    """Processes the rows of a receipt."""

    def __init__(self, receipt: Receipt, resolver: FileResolver) -> None:
        self.__receipt = receipt
        self.__resolver = resolver
        self.__failed: Set[int] = set()

    def run(self) -> ReceiptResult:
        """Processes every Upload in the receipt.

        Returns:
          the result with the number of failed rows
        """
        self.__failed = set()
        groups: Dict[str, List[Tuple[int, ReceiptRow]]] = {}
        for index, row in enumerate(self.__receipt.rows):
            file_id = row.directory_file_id
            if file_id is None:
                self.__fail(index, row, "no file ID in Directory")
                continue
            groups.setdefault(file_id, []).append((index, row))

        acquisitions: Dict[str, _AcquisitionGroup] = {}
        for file_id, rows in groups.items():
            resolved = self.__resolver.resolve(file_id)
            if resolved is None:
                for index, row in rows:
                    self.__fail(index, row, "file not resolved to an acquisition")
                continue

            upload = _Upload(file_id=file_id, rows=rows, resolved=resolved)
            self.__build_entry(upload)
            group = acquisitions.setdefault(
                resolved.acquisition_id, _AcquisitionGroup(target=resolved.acquisition)
            )
            group.uploads.append(upload)

        for group in acquisitions.values():
            self.__write(group)

        return ReceiptResult(failed_rows=len(self.__failed))

    def __fail(self, index: int, row: ReceiptRow, reason: str) -> None:
        """Counts the row as failed, warning once per row."""
        if index in self.__failed:
            return

        self.__failed.add(index)
        log.warning(
            "Failed row for %s: Status '%s' (%s)",
            row.directory_file_id or row.directory,
            row.status,
            reason,
        )

    def __build_entry(self, upload: _Upload) -> None:
        """Sets the entry for the upload if none of its rows failed."""
        failed = [(index, row) for index, row in upload.rows if row.is_failed]
        if failed:
            for index, row in failed:
                self.__fail(index, row, "unsuccessful or incomplete upload")
            return

        first = upload.rows[0][1]
        if any(
            row.upload_id != first.upload_id or row.status != first.status
            for _, row in upload.rows
        ):
            log.warning(
                "Rows for file %s differ in Upload ID or Status; using first row",
                upload.file_id,
            )

        upload.entry = {
            "file_name": upload.resolved.file_name,
            "upload_id": first.upload_id,
            "status": first.status,
            "uploads": [
                {"loni_uid": row.loni_uid, "upload_date": row.upload_date}
                for _, row in upload.rows
            ],
        }

    def __write(self, group: _AcquisitionGroup) -> None:
        """Writes entries and receipt copy for the acquisition, if any
        entry."""
        entries = {
            upload.file_id: upload.entry
            for upload in group.uploads
            if upload.entry is not None
        }
        if not entries:
            return

        rows = sorted(
            (item for upload in group.uploads for item in upload.rows),
            key=lambda item: item[0],
        )
        try:
            group.target.write_upload_loni(entries)
            group.target.attach_receipt_copy(
                self.__receipt.name, self.__receipt.to_csv([row for _, row in rows])
            )
        except TargetWriteError as error:
            log.error(
                "Failed to write to acquisition %s for receipt %s: %s",
                group.target.label,
                self.__receipt.name,
                error,
            )
            for index, row in rows:
                self.__fail(index, row, "write to acquisition failed")
