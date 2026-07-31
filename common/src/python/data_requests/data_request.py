import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from identifiers.model import NACCID_PATTERN
from inputs.csv_reader import CSVVisitor
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_common.error_models import CSVLocation, FileError
from outputs.error_writer import ErrorWriter
from outputs.errors import malformed_file_error, missing_field_error
from outputs.outputs import StringCSVWriter
from pydantic import BaseModel, Field, ValidationError, model_validator

log = logging.getLogger(__name__)


class DataRequest(BaseModel):
    """Data model for a row of a data request file."""

    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)

    @model_validator(mode="before")
    @classmethod
    def fix_case(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k.lower(): v for k, v in value.items()}

        return value


class DataRequestMatch(BaseModel):
    """Data model representing a participant matching data request for
    NACCID."""

    naccid: str
    subject_id: str
    project_label: str


def formver_label(formver: Any) -> str:
    """Normalize a form version value into a filename-safe label.

    Examples:
        "1"   -> "v1"
        "1.0" -> "v1"
        "1.5" -> "v1.5"
        "3.0" -> "v3"
        ""    -> "unknown"
        None  -> "unknown"

    Args:
      formver: the raw form version value (any type; coerced via str)
    Returns:
      a label suitable for use in a filename, e.g. "v3" or "unknown"
    """
    s = str(formver if formver is not None else "").strip()
    if not s:
        return "unknown"
    if s.endswith(".0"):
        s = s[:-2]
    return f"v{s}"


class ModuleDataGatherer:
    """Defines process to gather file.info.form custom info for data requests.

    When ``split_by_formver`` is True, rows are bucketed by form version
    (using the ``formver`` field in the merged form data) and surfaced via
    ``content_by_formver`` instead of ``content``. Each formver bucket has
    its own ``StringCSVWriter``, which means the column set for each bucket
    is naturally restricted to the columns that bucket's rows actually use —
    no cross-version sparse columns.

    When ``split_by_formver`` is False (default), behavior is identical to
    the original single-CSV-per-module flow: ``content`` returns the union-
    schema CSV string, ``content_by_formver`` is unavailable.
    """

    def __init__(
        self,
        proxy: FlywheelProxy,
        module_name: str,
        info_paths: Optional[list[str]] = None,
        split_by_formver: bool = False,
    ) -> None:
        self.__proxy = proxy
        self.__module_name = module_name
        self.__info_paths = info_paths if info_paths is not None else ["forms.json"]
        self.__split_by_formver = split_by_formver
        # Writers keyed by formver label when splitting; a single writer under
        # the "default" label otherwise.
        self.__writers: dict[str, StringCSVWriter] = {}

    @property
    def module_name(self):
        return self.__module_name

    @property
    def split_by_formver(self) -> bool:
        return self.__split_by_formver

    @property
    def content(self):
        """Returns the CSV content for this module (single-bucket mode).

        Raises:
          AttributeError if this gatherer was constructed with
          split_by_formver=True; use ``content_by_formver`` instead.
        """
        if self.__split_by_formver:
            raise AttributeError(
                "content is unavailable when split_by_formver=True; "
                "use content_by_formver instead"
            )
        writer = self.__writers.setdefault("default", StringCSVWriter())
        return writer.get_content()

    @property
    def content_by_formver(self) -> dict[str, str]:
        """Returns CSV content keyed by form-version label.

        Each value is a complete CSV string whose header is restricted to
        the columns present in that formver bucket — rows are not padded
        across buckets.

        Raises:
          AttributeError if this gatherer was constructed with
          split_by_formver=False; use ``content`` instead.
        """
        if not self.__split_by_formver:
            raise AttributeError(
                "content_by_formver is unavailable when "
                "split_by_formver=False; use content instead"
            )
        return {label: writer.get_content() for label, writer in self.__writers.items()}

    def gather_file_info(self, file: FileEntry) -> None:
        """Writes file info to the writer. Uses the info paths of this object
        to pull the dictionary at file.info.<path> and merges the dictionaries.

        Args:
          file: the file object
        Raises:
          ModuleDataError if path doesn't exist or the value is not a dictionary.
        """
        self.__process_reloaded_file(file.reload())

    def __process_reloaded_file(self, file: FileEntry) -> None:
        """Writes file info to the writer for a file that has already been
        reloaded (i.e. ``file.info`` is populated).

        Args:
          file: the reloaded file object
        Raises:
          ModuleDataError if path doesn't exist or the value is not a dictionary.
        """
        merged_data = {}
        symbol_table = SymbolTable(file.info)

        for path in self.__info_paths:
            try:
                form_data = symbol_table[path]
            except KeyError as error:
                raise ModuleDataError(
                    f"file.info.{path} not found for {file.file_id}"
                ) from error
            if not isinstance(form_data, dict):
                raise ModuleDataError(
                    f"expected a dictionary at {path}, got {type(form_data)}"
                )

            merged_data.update(form_data)

        label = (
            formver_label(merged_data.get("formver"))
            if self.__split_by_formver
            else "default"
        )
        writer = self.__writers.setdefault(label, StringCSVWriter())
        writer.write(merged_data)

    def gather_request_data(self, request: DataRequestMatch) -> None:
        """Writes the file custom info to the writer of this object for each
        acquisition of the request subject that is labeled byt the module name.

        Args:
          request: the data request
        """
        files = self.__proxy.get_files(
            f"parent_ref.type=acquisition,parents.subject={request.subject_id},"
            f"acquisition.label={self.__module_name}"
        )
        for file in files:
            try:
                self.gather_file_info(file)
            except ModuleDataError as error:
                log.warning("Failed to load data: %s", str(error))
                continue

    def gather_project_data(
        self,
        subject_ids: list[str],
        batch_size: int = 100,
        reload_workers: int = 10,
    ) -> None:
        """Writes the file custom info to the writer of this object for every
        acquisition labeled by the module name, across the given subjects.

        Unlike ``gather_request_data``, this batches subjects into groups
        using Flywheel's OR-list filter syntax (``field=|[v1,v2,...]``)
        instead of issuing one query per subject. This is the appropriate
        access pattern when there is no participant list to narrow the
        subjects of interest (e.g. a full-center export): one query per
        subject doesn't scale to centers with thousands of subjects, and a
        single query scoped to the whole project (with no subject
        narrowing at all) can time out on Flywheel's backend for large
        projects instead of paginating cleanly.

        Within each batch, the per-file ``.reload()`` calls needed to
        populate ``file.info`` are issued concurrently across a shared
        worker pool (they are independent I/O-bound requests), since
        serially reloading every matching file dominates runtime for
        modules with many visits per subject (e.g. UDS). The merge/write
        step for each reloaded file still runs single-threaded, since
        ``StringCSVWriter`` is not thread-safe.

        Args:
          subject_ids: Flywheel subject ids to search across
          batch_size: number of subject ids per query batch. The default
            of 100 was tuned empirically against real center data rather
            than swept systematically -- worth revisiting if it proves
            slow.
          reload_workers: number of concurrent workers used to reload
            each batch's files. Defaults to 10 to match the underlying
            ``requests.Session`` connection pool size
            (``requests.adapters.DEFAULT_POOLSIZE``); using more workers
            than that causes connections to be discarded and reopened
            rather than reused. Assumes concurrent use of one shared
            Flywheel client/session across threads is safe -- observed
            correct in testing, but not guaranteed by the SDK docs.
        """
        total_subjects = len(subject_ids)
        with ThreadPoolExecutor(max_workers=reload_workers) as pool:
            for start in range(0, total_subjects, batch_size):
                batch = subject_ids[start : start + batch_size]
                files = self.__proxy.get_files(
                    f"parent_ref.type=acquisition,"
                    f"parents.subject=|[{','.join(batch)}],"
                    f"acquisition.label={self.__module_name}"
                )
                reloaded_files = pool.map(lambda file: file.reload(), files)
                for file in reloaded_files:
                    try:
                        self.__process_reloaded_file(file)
                    except ModuleDataError as error:
                        log.warning("Failed to load data: %s", str(error))
                log.info(
                    "Processed %d/%d subjects for module %s",
                    min(start + batch_size, total_subjects),
                    total_subjects,
                    self.__module_name,
                )


class ModuleDataError(Exception):
    """Error when accessing form module data."""


def create_project_matcher(study_id: str, project_names: list[str]) -> re.Pattern[str]:
    """Creates a regex pattern for matching project names.

    Includes the unqualified project names and the names with the study_id as
    a suffix.

    Args:
      study_id: the study-id
      project_names: the list of project names
    Returns:
      the regex pattern to match any of the project names
    """
    temp_project_names = set(project_names)
    temp_project_names.update({f"{name}-{study_id}" for name in project_names})
    return re.compile(f"^{'|'.join(temp_project_names)}$")


class DataRequestVisitor(CSVVisitor):
    """Gathers subject matches for a data request file given as a CSV file
    where each row loads as a DataRequest object."""

    def __init__(
        self,
        *,
        proxy: FlywheelProxy,
        error_writer: ErrorWriter,
        project_names: list[str],
        study_id: str,
        gatherers: list[ModuleDataGatherer],
    ) -> None:
        self.__proxy = proxy
        self.__error_writer = error_writer
        self.__expected_studies = {study_id, "adrc"}
        self.__gatherers = gatherers
        self.__project_matcher = create_project_matcher(
            study_id=study_id, project_names=project_names
        )

    @property
    def gatherers(self) -> list[ModuleDataGatherer]:
        return self.__gatherers

    def visit_header(self, header: List[str]) -> bool:
        """Checks that the header has ADCID, PTID and study keys.

        Args:
          header: list of header names
        Returns:
          True if the header has expected column names. False, otherwise.
        """
        missing_headers = set(DataRequest.model_fields).difference(header)
        if missing_headers:
            self.__error_writer.write(missing_field_error(missing_headers))
            return False

        return True

    def __get_matches(self, request: DataRequest) -> list[DataRequestMatch]:
        """Returns list of subject IDs matching the NACCID in the request that
        have projects matching the study and name constraints.

        Args:
          request: the data request
        Returns:
          a list of subject IDs
        """
        result = []
        subjects = self.__proxy.get_subject_by_label(request.naccid)
        for subject in subjects:
            parent_project = self.__proxy.get_container_by_id(subject.parents.project)
            if self.__project_matcher.match(parent_project.label):
                result.append(
                    DataRequestMatch(
                        naccid=request.naccid,
                        subject_id=subject.id,
                        project_label=parent_project.label,
                    )
                )

        return result

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Applies this visitor to the data request row at the line number.

        If the data request validates, matches the subjects with the request
        and project names for this visitor.
        If there are any matches, applies the gatherers of this visitor to
        collect data for the subject.

        Args:
          row: the data request object
          line_num: the line number
        Returns:
          True if the visit had no failure
        """
        try:
            query = DataRequest.model_validate(row)
        except ValidationError as error:
            self.__error_writer.write(malformed_file_error(str(error)))
            return True  # ignore row

        matching_requests = self.__get_matches(request=query)
        if not matching_requests:
            self.__error_writer.write(
                FileError(
                    error_code="no-participant",  # pyright: ignore[reportCallIssue]
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    location=CSVLocation(line=line_num, column_name="naccid"),
                    message=(
                        f"no participant {query.naccid} with data for "
                        f"{','.join(self.__expected_studies)}"
                    ),
                )
            )
            return True  # ignore row

        for request in matching_requests:
            for gatherer in self.__gatherers:
                try:
                    gatherer.gather_request_data(request)
                except ModuleDataError as error:
                    log.warning(
                        "Request error for subject %s, module %s: %s",
                        request.subject_id,
                        gatherer.module_name,
                        str(error),
                    )

        return True
