"""Flywheel-bound implementations of the interfaces used by the receipt
processor."""

import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from flywheel import Client
from flywheel.file_spec import FileSpec
from flywheel.models.acquisition import Acquisition
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from nacc_common.error_models import GearTags
from uploads.acquisition import replace_in_acquisition
from utils.decorators import api_retry

from .main import AcquisitionTarget, ResolvedFile, TargetWriteError

log = logging.getLogger(__name__)

UPLOAD_LONI_KEY = "upload_loni"


@api_retry
def _get_file(proxy: FlywheelProxy, file_id: str) -> FileEntry:
    return proxy.get_file(file_id)


@api_retry
def _get_acquisition(proxy: FlywheelProxy, acquisition_id: str) -> Acquisition:
    return proxy.get_acquisition(acquisition_id)


@api_retry
def _reload(acquisition: Acquisition) -> Acquisition:
    return acquisition.reload()


@api_retry
def _update_info(acquisition: Acquisition, info: Dict[str, Any]) -> None:
    acquisition.update_info(info)


class FlywheelAcquisitionTarget:
    """Writes receipt data to a Flywheel acquisition."""

    def __init__(self, acquisition: Acquisition) -> None:
        self.__acquisition = acquisition

    @property
    def label(self) -> str:
        return self.__acquisition.label

    def write_upload_loni(self, entries: Mapping[str, Dict[str, Any]]) -> None:
        """Merges the entries into `info.upload_loni`.

        Replaces entries with the same file ID and leaves others alone. The
        whole `upload_loni` object is written because update_info replaces
        second-level objects instead of merging into them.

        Raises:
          TargetWriteError: if the Flywheel calls fail
        """
        try:
            current = _reload(self.__acquisition)
            # update_info replaces the whole upload_loni object, so a
            # concurrent writer between this reload and the write could lose
            # entries. The gear is the only writer of this key.
            merged = dict((current.info or {}).get(UPLOAD_LONI_KEY, {}))
            merged.update(entries)
            _update_info(self.__acquisition, {UPLOAD_LONI_KEY: merged})
        except ApiException as error:
            raise TargetWriteError(
                f"Failed to update info on acquisition {self.label}: {error}"
            ) from error

    def attach_receipt_copy(self, name: str, contents: str) -> None:
        """Attaches the file to the acquisition, replacing a file of the same
        name.

        Raises:
          TargetWriteError: if the Flywheel calls fail
        """
        file_spec = FileSpec(name=name, contents=contents, content_type="text/csv")
        try:
            replace_in_acquisition(self.__acquisition, file_spec)
        except ApiException as error:
            raise TargetWriteError(
                f"Failed to upload {name} to acquisition {self.label}: {error}"
            ) from error


class DryRunAcquisitionTarget:
    """Logs what would be written to an acquisition."""

    def __init__(self, label: str) -> None:
        self.__label = label

    @property
    def label(self) -> str:
        return self.__label

    def write_upload_loni(self, entries: Mapping[str, Dict[str, Any]]) -> None:
        for file_id, entry in entries.items():
            log.info(
                "DRY RUN: would set upload_loni.%s = %s on acquisition %s",
                file_id,
                entry,
                self.__label,
            )

    def attach_receipt_copy(self, name: str, contents: str) -> None:
        log.info(
            "DRY RUN: would attach %s (%d rows) to acquisition %s:\n%s",
            name,
            max(len(contents.splitlines()) - 1, 0),
            self.__label,
            contents,
        )


class FlywheelFileResolver:
    """Resolves file IDs to acquisitions using Flywheel."""

    def __init__(
        self,
        proxy: FlywheelProxy,
        target_factory: Callable[[Acquisition], AcquisitionTarget],
    ) -> None:
        self.__proxy = proxy
        self.__target_factory = target_factory
        self.__cache: Dict[str, Tuple[Acquisition, AcquisitionTarget]] = {}

    def resolve(self, file_id: str) -> Optional[ResolvedFile]:
        """Resolves the file ID to the acquisition that currently contains it.

        Returns:
          the resolved file, or None if the file cannot be found in an
          acquisition
        """
        try:
            file = _get_file(self.__proxy, file_id)
        except ApiException as error:
            log.warning("Cannot get file %s: %s", file_id, error)
            return None

        acquisition_id = file.parents.acquisition
        if not acquisition_id:
            log.warning("File %s is not in an acquisition", file_id)
            return None

        try:
            fresh, target = self.__get_acquisition(acquisition_id)
        except ApiException as error:
            log.warning("Cannot get acquisition %s: %s", acquisition_id, error)
            return None

        if not any(entry.file_id == file_id for entry in fresh.files or []):
            log.warning("File %s is not in acquisition %s", file_id, acquisition_id)
            return None

        return ResolvedFile(
            file_id=file_id,
            file_name=file.name,
            acquisition_id=fresh.id,
            acquisition=target,
        )

    def __get_acquisition(
        self, acquisition_id: str
    ) -> Tuple[Acquisition, AcquisitionTarget]:
        if acquisition_id not in self.__cache:
            acquisition = _get_acquisition(self.__proxy, acquisition_id)
            fresh = _reload(acquisition)
            self.__cache[acquisition_id] = (fresh, self.__target_factory(fresh))

        return self.__cache[acquisition_id]


class FlywheelReceiptTagger:
    """Tags the input receipt file with the outcome."""

    def __init__(self, *, client: Client, file_id: str, gear_name: str) -> None:
        self.__client = client
        self.__file_id = file_id
        self.__tags = GearTags(gear_name)

    def mark(self, passed: bool) -> None:
        """Sets the PASS or FAIL tag on the receipt.

        Raises:
          GearExecutionError: if the tag cannot be set
        """
        status = "PASS" if passed else "FAIL"
        current: Optional[List[str]]
        try:
            file = self.__client.get_file(self.__file_id)
            current = list(file.tags or [])
        except ApiException as error:
            log.warning(
                "Cannot read tags of %s, clearing stale tag unconditionally: %s",
                self.__file_id,
                error,
            )
            current = None

        to_add, to_remove = self.__tags.tag_changes(current, status)
        for tag in to_remove:
            try:
                self.__client.delete_file_tags(self.__file_id, body=[tag])
            except ApiException as error:
                if current is not None:
                    raise self.__error("remove", tag, error) from error
                log.warning("Ignoring failure to remove tag %s: %s", tag, error)

        for tag in to_add:
            try:
                self.__client.add_file_tags(self.__file_id, body=[tag])
            except ApiException as error:
                raise self.__error("add", tag, error) from error

    def __error(self, action: str, tag: str, error: ApiException):
        message = f"Failed to {action} tag {tag} on file {self.__file_id}: {error}"
        log.error(message)
        return GearExecutionError(message)


class DryRunReceiptTagger:
    """Logs the tag that would be set."""

    def __init__(self, gear_name: str) -> None:
        self.__tags = GearTags(gear_name)

    def mark(self, passed: bool) -> None:
        tag = self.__tags.pass_tag if passed else self.__tags.fail_tag
        log.info("DRY RUN: would tag receipt with %s", tag)
