"""Defines Gather Submission Status Gear."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import DictWriter
from typing import TextIO

from data_requests.status_request import StatusRequestClusteringVisitor
from flywheel.models.file_entry import FileEntry
from inputs.csv_reader import read_csv
from nacc_common.error_models import FileQCModel
from nacc_common.qc_report import (
    QC_FILENAME_PATTERN,
    DictReportWriter,
    FileQCReportVisitorBuilder,
    QCTransformerError,
    ReportTableVisitor,
    WriterTableVisitor,
)
from outputs.error_writer import ErrorWriter
from pydantic import ValidationError

log = logging.getLogger(__name__)


def _should_process_file(
    *,
    filename: str,
    matcher: re.Pattern[str],
    ptid_set: set[str],
    modules: set[str],
) -> bool:
    """Check if a file should be processed based on ptid and module filters.

    Replicates ProjectReportVisitor.__should_process_file logic.

    Args:
        filename: the filename to check
        matcher: compiled QC_FILENAME_PATTERN regex
        ptid_set: set of participant IDs to include
        modules: set of module names to include (uppercased)

    Returns:
        True if the file matches pattern and passes ptid/module filters.
    """
    match = matcher.match(filename)
    if not match:
        return False

    ptid = match.group(1)
    if ptid not in ptid_set:
        return False

    module = match.group(3).upper()
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

    Phase 1: Reads and clusters the input CSV by ADCID (unchanged).
    Phase 2: For each ADCID's projects, filters QC log files, reloads them
    concurrently, then processes each single-threaded.

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
    # Phase 1: Clustering (unchanged)
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

    # Phase 2: Concurrent file gathering
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
            request_adcid = request_list[0].adcid  # all requests have same adcid
            if request_adcid != pipeline_adcid:
                log.error("Expect ADCID: %s got %s", pipeline_adcid, request_adcid)
                continue

            ptid_set = {request.ptid for request in request_list}
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

                # Submit all reloads concurrently
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
