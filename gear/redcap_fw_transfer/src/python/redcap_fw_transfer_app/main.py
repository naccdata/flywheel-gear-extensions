"""Defines REDCap to Flywheel Transfer."""

import json
import logging
from datetime import datetime
from json.decoder import JSONDecodeError
from typing import Any, Dict, List

import pandas as pd
from flywheel import FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from redcap.redcap_connection import (
    REDCapConnection,
    REDCapConnectionError,
    REDCapReportConnection,
)
from redcap.redcap_project import REDCapProject

log = logging.getLogger(__name__)


def upload_to_flywheel(*, visits: List[Dict[str,
                                            Any]], extra_fields: List[str],
                       filename: str, prj_adaptor: ProjectAdaptor):
    """Convert the visits details to CSV format and upload to Flywheel.

    Args:
        visits: List of new/updated visits
        output_file: output file created in the Flywheel ingest project
        extra_fields: list of extra fields to be dropped before upload

    Raises:
        GearExecutionError if CSV upload fails
    """

    input_df = pd.DataFrame(visits)

    # drop any extra columns that are not part of the module schema
    if extra_fields:
        output_df = input_df.drop(labels=extra_fields, axis=1, errors='ignore')

    try:
        csv_contents = output_df.to_csv(index=False, doublequote=False)
    except Exception as error:
        raise GearExecutionError(
            f'Problem occurred while generating CSV file: {error}') from error

    file_spec = FileSpec(name=filename,
                         contents=csv_contents,
                         content_type="text/csv")

    try:
        prj_adaptor.upload_file(file_spec)
        log.info('Successfully uploaded file %s to %s/%s', filename,
                 prj_adaptor.group, prj_adaptor.label)
    except ApiException as error:
        raise GearExecutionError(
            'Failed to upload file '
            f'{filename} to {prj_adaptor.group}/{prj_adaptor.label}: {error}'
        ) from error


def reset_upload_checkbox(redcap_prj: REDCapProject,
                          visits: List[Dict[str, str]], timestamp: datetime):
    """Reset the upload checkboxes in REDCap records.

    Args:
        redcap_prj: REDCap project to update records
        visits: List of new/updated visits
        timestamp: Upload timestamp

    Raises:
        GearExecutionError if failed to update REDCap records
    """

    updates = []

    for visit in visits:
        update = {}
        update[redcap_prj.primary_key_field] = visit[
            redcap_prj.primary_key_field]
        if redcap_prj.has_repeating_instruments_or_events():
            update['redcap_event_name'] = visit['redcap_event_name']
            update['redcap_repeat_instance'] = visit['redcap_repeat_instance']
        update['upld_ready___1'] = '0'
        update['upld_time'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        updates.append(update)

    try:
        num_updated = redcap_prj.import_records(json.dumps(updates))
        log.info('Number of updated records: %s', num_updated)
    except REDCapConnectionError as error:
        raise GearExecutionError(error.message) from error


def validate_redcap_report(redcap_prj: REDCapProject, report_id: str,
                           record: Dict[str, str],
                           schema: Dict[str, Any]) -> List[str]:
    """Check whether the required fields included in the report.

    Args:
        redcap_prj: REDCap project the report is exported from
        report_id: REDCap report id
        record: sample record from the report
        schema: expected schema for the module

    Returns:
        List(str): list of extra fields included in the record that are
            not in the schema for the module (if any)
    Raises:
        GearExecutionError if required fields are missing in the report
    """

    if redcap_prj.primary_key_field not in record:
        raise GearExecutionError(
            f'Primary key {redcap_prj.primary_key_field} not included '
            f'in project {redcap_prj.title} report {report_id}')

    if (redcap_prj.has_repeating_instruments_or_events()
            and ('redcap_event_name' not in record
                 or 'redcap_repeat_instance' not in record)):
        raise GearExecutionError(
            f'REDCap repeating instance fields not included '
            f'in project {redcap_prj.title} report {report_id}')

    extra_fields = set(record.keys()).difference(set(schema.keys()))
    return list(extra_fields)


def run(*, gear_context: GearToolkitContext, redcap_con: REDCapConnection,
        redcap_pid: str, module: str, fw_group: str,
        prj_adaptor: ProjectAdaptor):
    """Download new/updated records from REDCap and upload to Flywheel as a CSV
    file.

    Args:
        context: the gear execution context
        redcap_con: API connection to REDCap project
        redcap_pid: REDCap project id
        module: Forms module
        fw_group: Flywheel group id
        prj_adaptor: Flywheel project to transfer data

    Raises:
        GearExecutionError if any problem occurs during the transfer
    """

    schema_file = module + '-schema.json'
    try:
        schema = json.loads(prj_adaptor.read_file(schema_file))
    except (ApiException, JSONDecodeError) as error:
        raise GearExecutionError(
            f'Failed to read schema file {schema_file}: {error}') from error

    if 'definitions' not in schema:
        raise GearExecutionError(
            f'Field definitions not found in schema file {schema_file}')

    records_list: List[Dict[str, Any]] = []
    try:
        redcap_prj = REDCapProject.create(redcap_con)
        if isinstance(redcap_con, REDCapReportConnection):
            records_list = redcap_con.get_report_records()
            extra_fields = validate_redcap_report(redcap_prj,
                                                  redcap_con.report_id,
                                                  records_list[0],
                                                  schema['definitions'])
        # If no report available export records using the schema definition
        # For longitudinal projects assumes the events are defined by module
        else:
            events = None
            fields = list(schema['definitions'].keys())
            filters = '[upld_ready(1)] = 1'

            extra_fields = []
            if redcap_prj.primary_key_field not in fields:
                fields.append(redcap_prj.primary_key_field)
                extra_fields.append(redcap_prj.primary_key_field)

            if redcap_prj.has_repeating_instruments_or_events():
                event = redcap_prj.get_event_name_for_label(f'{module}-visit')
                if not event:
                    raise GearExecutionError(
                        f'Cannot find event {module}-visit'
                        f' in project {redcap_prj.title}')
                events = [event]
                extra_fields.extend([
                    'redcap_event_name', 'redcap_repeat_instance',
                    'redcap_repeat_instrument'
                ])

            records_list = redcap_prj.export_records(
                fields=fields, events=events, filters=filters)  # type: ignore
    except REDCapConnectionError as error:
        raise GearExecutionError(error.message) from error

    if len(records_list) == 0:
        log.info(
            'No new/updated visits found in REDCap project pid=%s module=%s '
            'for Flywheel project %s/%s', redcap_pid, module, fw_group,
            prj_adaptor.label)
        return

    filename = 'redcap-ingest-' + module + '.csv'
    upload_to_flywheel(visits=records_list,
                       extra_fields=extra_fields,
                       filename=filename,
                       prj_adaptor=prj_adaptor)

    reset_upload_checkbox(redcap_prj, records_list, datetime.now())
