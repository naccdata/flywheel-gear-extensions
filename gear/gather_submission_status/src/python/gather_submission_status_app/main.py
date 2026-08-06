"""Defines Gather Submission Status Gear."""

import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import DictWriter
from dataclasses import dataclass, field
from typing import Any, TextIO

from data_requests.status_request import StatusRequestClusteringVisitor
from flywheel.models.file_entry import FileEntry
from inputs.csv_reader import read_csv
from nacc_common.error_models import FileQCModel
from nacc_common.qc_report import (
    QC_FILENAME_PATTERN,
    DictReportWriter,
    FileQCReportVisitorBuilder,
    ListReportWriter,
    QCTransformerError,
    ReportTableVisitor,
    WriterTableVisitor,
)
from outputs.error_writer import ErrorWriter
from pydantic import ValidationError

log = logging.getLogger(__name__)

# Fields for consolidated status output (no stage column)
CONSOLIDATED_FIELDNAMES = ["adcid", "ptid", "module", "visitdate", "status"]


def _should_process_file(
    *,
    filename: str,
    matcher: re.Pattern[str],
    ptid_set: set[str],
    modules: set[str],
) -> bool:
    """Check if a file should be processed based on ptid and module filters.

    Replicates ProjectReportVisitor.__should_process_file logic without the
    Optional handling — callers must provide populated sets (not None).

    Args:
        filename: the filename to check
        matcher: compiled QC_FILENAME_PATTERN regex
        ptid_set: set of participant IDs to include (must not be None)
        modules: set of module names to include, uppercased (must not be None)

    Returns:
        True if the file matches pattern and passes ptid/module filters.
    """
    match = matcher.match(filename)
    if not match:
        return False

    ptid = match.group("ptid")
    if ptid not in ptid_set:
        return False

    module = match.group("module").upper()
    return module in modules


def _process_reloaded_file(
    *,
    file: FileEntry,
    adcid: int,
    file_visitor_builder: FileQCReportVisitorBuilder,
    table_visitor: ReportTableVisitor,
) -> None:
    """Process a single reloaded QC log file.

    Validates QC info, builds the model, creates a file visitor, applies the
    model, and writes results to the table visitor.

    Args:
        file: the reloaded file entry with populated info
        adcid: the ADCID for this file's center
        file_visitor_builder: factory for creating FileQCReportVisitors
        table_visitor: visitor that writes report table rows
    """
    if not file.info or not file.info.get("qc"):
        log.warning("file does not have qc: %s", file.name)
        return

    try:
        qc_model = FileQCModel.model_validate(file.info, by_alias=True)
    except ValidationError as error:
        log.warning("Failed to load QC data for %s: %s", file.name, error)
        return

    file_visitor = file_visitor_builder(file, adcid)
    if file_visitor.visit_details is None:
        log.warning("Could not extract visit details from %s", file.name)
        return

    try:
        qc_model.apply(file_visitor)
    except QCTransformerError as error:
        log.error(
            "Unexpected QC transformation error for file %s: %s", file.name, error
        )
        return

    table_visitor.visit_table(file_visitor.table)


@dataclass
class ConsolidatedResult:
    """Result of consolidating per-stage rows into per-submission rows."""

    passed: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)


def consolidate_status_rows(
    rows: list[dict[str, Any]],
) -> ConsolidatedResult:
    """Consolidate per-stage status rows into per-submission pass/fail.

    Groups rows by (adcid, ptid, module, visitdate) and determines overall
    status: PASS only if all stages passed, otherwise FAIL.

    Args:
        rows: list of row dicts with keys including adcid, ptid, module,
              visitdate, status

    Returns:
        ConsolidatedResult with passed and failed row lists
    """
    grouped: dict[tuple, list[str]] = defaultdict(list)

    for row in rows:
        key = (row["adcid"], row["ptid"], row["module"], row["visitdate"])
        status = row.get("status", "")
        grouped[key].append(status.upper() if status else "")

    result = ConsolidatedResult()
    for (adcid, ptid, module, visitdate), statuses in grouped.items():
        all_passed = all(s == "PASS" for s in statuses)
        consolidated_row = {
            "adcid": adcid,
            "ptid": ptid,
            "module": module,
            "visitdate": visitdate,
            "status": "PASS" if all_passed else "FAIL",
        }
        if all_passed:
            result.passed.append(consolidated_row)
        else:
            result.failed.append(consolidated_row)

    return result


def _gather_status_rows(
    *,
    input_file: TextIO,
    modules: set[str],
    clustering_visitor: StatusRequestClusteringVisitor,
    file_visitor_builder: FileQCReportVisitorBuilder,
    error_writer: ErrorWriter,
    reload_workers: int = 10,
) -> tuple[bool, list[dict[str, Any]]]:
    """Gather all per-stage status rows from QC log files.

    Phase 1: Reads and clusters the input CSV by ADCID.
    Phase 2: For each ADCID's projects, filters QC log files, reloads them
    concurrently, then processes each single-threaded.

    Args:
        input_file: the input CSV stream
        modules: set of module names to include
        clustering_visitor: the CSV visitor that clusters requests by ADCID
        file_visitor_builder: factory for creating FileQCReportVisitors
        error_writer: collects per-request errors
        reload_workers: number of concurrent threads for file.reload() calls

    Returns:
        Tuple of (success, rows) where rows is a list of row dicts.
    """
    ok_status = read_csv(
        input_file=input_file, error_writer=error_writer, visitor=clustering_visitor
    )
    if not ok_status:
        log.error("Request clustering failed. See QC output.")
        return False, []

    project_map = clustering_visitor.pipeline_map
    if not project_map:
        log.warning("No projects found for requested data")
        return False, []

    collected_rows: list[dict[str, Any]] = []
    table_visitor = WriterTableVisitor(ListReportWriter(collected_rows))
    matcher = re.compile(QC_FILENAME_PATTERN)

    with ThreadPoolExecutor(max_workers=reload_workers) as pool:
        for pipeline_adcid, project_list in project_map.items():
            if not project_list:
                log.warning(
                    "No projects found for center %s participants", pipeline_adcid
                )
                continue

            request_list = clustering_visitor.request_map.get(pipeline_adcid)
            if not request_list:
                log.warning("No participants found for center %s", pipeline_adcid)
                continue
            request_adcid = request_list[0].adcid
            if request_adcid != pipeline_adcid:
                log.error("Expect ADCID: %s got %s", pipeline_adcid, request_adcid)
                continue

            ptid_set = {request.ptid.strip().lstrip("0") for request in request_list}
            for project in project_list:
                log.info("visiting project %s/%s", pipeline_adcid, project.label)

                candidate_files = [
                    f
                    for f in project.project.files
                    if _should_process_file(
                        filename=f.name,
                        matcher=matcher,
                        ptid_set=ptid_set,
                        modules=modules,
                    )
                ]

                futures = {pool.submit(f.reload): f for f in candidate_files}

                for future in as_completed(futures):
                    original_file = futures[future]
                    try:
                        reloaded_file = future.result()
                    except Exception as error:
                        log.warning(
                            "Failed to reload file %s: %s",
                            original_file.name,
                            error,
                        )
                        continue

                    _process_reloaded_file(
                        file=reloaded_file,
                        adcid=request_adcid,
                        file_visitor_builder=file_visitor_builder,
                        table_visitor=table_visitor,
                    )

    return True, collected_rows


def run(
    *,
    input_file: TextIO,
    modules: set[str],
    clustering_visitor: StatusRequestClusteringVisitor,
    file_visitor_builder: FileQCReportVisitorBuilder,
    writer: DictWriter,
    error_writer: ErrorWriter,
    reload_workers: int = 10,
) -> bool:
    """Runs the Gather Submission Status process with concurrent file
    reloading.

    Collects per-stage rows and writes them directly to the writer.
    Used for the error report query type which does not need consolidation.

    Args:
        input_file: the input CSV stream
        modules: set of module names to include
        clustering_visitor: the CSV visitor that clusters requests by ADCID
        file_visitor_builder: factory for creating FileQCReportVisitors
        writer: the DictWriter for output rows
        error_writer: collects per-request errors
        reload_workers: number of concurrent threads for file.reload() calls

    Returns:
        True if processing completed successfully, False otherwise.
    """
    ok_status = read_csv(
        input_file=input_file, error_writer=error_writer, visitor=clustering_visitor
    )
    if not ok_status:
        log.error("Request clustering failed. See QC output.")
        return False

    project_map = clustering_visitor.pipeline_map
    if not project_map:
        log.warning("No projects found for requested data")
        return False

    table_visitor = WriterTableVisitor(DictReportWriter(writer))
    matcher = re.compile(QC_FILENAME_PATTERN)

    with ThreadPoolExecutor(max_workers=reload_workers) as pool:
        for pipeline_adcid, project_list in project_map.items():
            if not project_list:
                log.warning(
                    "No projects found for center %s participants", pipeline_adcid
                )
                continue

            request_list = clustering_visitor.request_map.get(pipeline_adcid)
            if not request_list:
                log.warning("No participants found for center %s", pipeline_adcid)
                continue
            request_adcid = request_list[0].adcid
            if request_adcid != pipeline_adcid:
                log.error("Expect ADCID: %s got %s", pipeline_adcid, request_adcid)
                continue

            ptid_set = {request.ptid.strip().lstrip("0") for request in request_list}
            for project in project_list:
                log.info("visiting project %s/%s", pipeline_adcid, project.label)

                candidate_files = [
                    f
                    for f in project.project.files
                    if _should_process_file(
                        filename=f.name,
                        matcher=matcher,
                        ptid_set=ptid_set,
                        modules=modules,
                    )
                ]

                futures = {pool.submit(f.reload): f for f in candidate_files}

                for future in as_completed(futures):
                    original_file = futures[future]
                    try:
                        reloaded_file = future.result()
                    except Exception as error:
                        log.warning(
                            "Failed to reload file %s: %s",
                            original_file.name,
                            error,
                        )
                        continue

                    _process_reloaded_file(
                        file=reloaded_file,
                        adcid=request_adcid,
                        file_visitor_builder=file_visitor_builder,
                        table_visitor=table_visitor,
                    )

    return True


def run_consolidated(
    *,
    input_file: TextIO,
    modules: set[str],
    clustering_visitor: StatusRequestClusteringVisitor,
    file_visitor_builder: FileQCReportVisitorBuilder,
    error_writer: ErrorWriter,
    reload_workers: int = 10,
) -> tuple[bool, ConsolidatedResult]:
    """Runs gather submission status and returns consolidated pass/fail
    results.

    Gathers per-stage status rows, then consolidates them by
    (adcid, ptid, module, visitdate). A submission passes only if all
    its stages passed.

    Args:
        input_file: the input CSV stream
        modules: set of module names to include
        clustering_visitor: the CSV visitor that clusters requests by ADCID
        file_visitor_builder: factory for creating FileQCReportVisitors
        error_writer: collects per-request errors
        reload_workers: number of concurrent threads for file.reload() calls

    Returns:
        Tuple of (success, ConsolidatedResult with passed/failed lists).
    """
    success, rows = _gather_status_rows(
        input_file=input_file,
        modules=modules,
        clustering_visitor=clustering_visitor,
        file_visitor_builder=file_visitor_builder,
        error_writer=error_writer,
        reload_workers=reload_workers,
    )
    if not success:
        return False, ConsolidatedResult()

    return True, consolidate_status_rows(rows)
