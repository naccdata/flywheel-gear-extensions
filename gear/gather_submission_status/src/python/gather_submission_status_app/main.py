"""Defines Gather Submission Status Gear."""

import logging
from csv import DictWriter
from typing import TextIO

from data_requests.status_request import StatusRequestClusteringVisitor
from inputs.csv_reader import read_csv
from nacc_common.qc_report import (
    DictReportWriter,
    FileQCReportVisitorBuilder,
    ProjectReportVisitor,
    WriterTableVisitor,
)
from outputs.error_writer import ErrorWriter

ModuleName = str

log = logging.getLogger(__name__)


def run(
    *,
    input_file: TextIO,
    modules: set[ModuleName],
    clustering_visitor: StatusRequestClusteringVisitor,
    file_visitor_builder: FileQCReportVisitorBuilder,
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
        log.error("Request clustering failed. See QC output.")
        return False

    project_map = clustering_visitor.pipeline_map
    if not project_map:
        log.warning("No projects found for requested data")
        return False

    for pipeline_adcid, project_list in project_map.items():
        if not project_list:
            log.warning("No projects found for center %s participants", pipeline_adcid)
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
            project_visitor = ProjectReportVisitor(
                adcid=pipeline_adcid,
                modules=set(modules),
                ptid_set=ptid_set,
                file_visitor_factory=file_visitor_builder,
                table_visitor=WriterTableVisitor(DictReportWriter(writer)),
            )
            project_visitor.visit_project(project.project)

    return True
