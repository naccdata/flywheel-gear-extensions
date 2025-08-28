"""Defines Gather Submission Status Gear."""

import logging
from csv import DictWriter
from typing import TextIO

from inputs.csv_reader import read_csv
from keys.types import ModuleName
from outputs.error_writer import ErrorWriter
from outputs.qc_report import FileQCReportVisitor, ProjectReportVisitor

from gather_submission_status_app.status_request import RequestClusteringVisitor

log = logging.getLogger(__name__)


def run(
    *,
    input_file: TextIO,
    modules: set[ModuleName],
    clustering_visitor: RequestClusteringVisitor,
    file_visitor: FileQCReportVisitor,
    writer: DictWriter,
    error_writer: ErrorWriter,
):
    """Runs the Gather Submission Status process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    ok_status = read_csv(
        input_file=input_file, error_writer=error_writer, visitor=clustering_visitor
    )
    if not ok_status:
        log.error("Request clustering failed")
        return False

    project_map = clustering_visitor.project_map
    if not project_map:
        log.warning("No projects found for requested data")
        return False

    for center_id, project_list in project_map.items():
        if not project_list:
            log.warning("No projects found for center %s participants", center_id)
            continue

        request_list = clustering_visitor.request_map.get(center_id)
        if not request_list:
            log.warning("No participants found for center %s", center_id)
            continue

        ptid_set = {request.ptid for request in request_list}
        request_adcid = request_list[0].adcid  # all requests have same adcid

        for project in project_list:
            log.info("visiting project %s/%s", center_id, project.label)
            project_visitor = ProjectReportVisitor(
                adcid=request_adcid,
                modules=set(modules),
                ptid_set=ptid_set,
                file_visitor=file_visitor,
                writer=writer,
            )
            project_visitor.visit_project(project)

    return True
