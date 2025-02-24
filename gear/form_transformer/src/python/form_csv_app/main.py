"""Defines CSV to JSON transformations."""

import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, TextIO

from configs.ingest_configs import ModuleConfigs
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames, SysErrorCodes
from outputs.errors import (
    ListErrorWriter,
    empty_field_error,
    get_error_log_name,
    missing_field_error,
    partially_failed_file_error,
    preprocess_errors,
    preprocessing_error,
    system_error,
    unexpected_value_error,
    update_error_log_and_qc_metadata,
)
from preprocess.preprocessor import FormPreprocessor
from transform.transformer import BaseRecordTransformer, TransformerFactory
from uploads.uploader import FormJSONUploader

log = logging.getLogger(__name__)


class CSVTransformVisitor(CSVVisitor):
    """Class to transform a participant visit CSV record."""

    def __init__(self,
                 *,
                 id_column: str,
                 module: str,
                 transformed_records: DefaultDict[str, Dict[str, Dict[str,
                                                                      Any]]],
                 error_writer: ListErrorWriter,
                 transformer_factory: TransformerFactory,
                 preprocessor: FormPreprocessor,
                 module_configs: ModuleConfigs,
                 gear_name: str,
                 project: Optional[ProjectAdaptor] = None) -> None:
        self.__module = module
        self.__id_column = id_column
        self.__transformed = transformed_records
        self.__error_writer = error_writer
        self.__transformer_factory = transformer_factory
        self.__preprocessor = preprocessor
        self.__module_configs = module_configs
        self.__gear_name = gear_name
        self.__project = project
        self.__transformer: Optional[BaseRecordTransformer] = None

        self.__date_field = self.__module_configs.date_field
        # TODO - set required fields in module configs template
        self.__req_fields = [
            self.__id_column, self.__date_field, FieldNames.MODULE,
            FieldNames.VISITNUM, FieldNames.FORMVER
        ]
        if self.__id_column != FieldNames.PTID:
            self.__req_fields.append(FieldNames.PTID)

        # TODO - set this in module configs template
        self.__error_log_template = {
            "ptid": FieldNames.PTID,
            "visitdate": self.__date_field
        }

        self.__existing_visits: DefaultDict[str, List[Dict[
            str, Any]]] = defaultdict(list)
        self.__current_batch: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    @property
    def module(self) -> str:
        """Returns the detected module for the CSV file."""
        return self.__module

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to process rows using the given header columns.
        If the header doesn't have required fields writes an error.

        Args:
          header: the list of header names

        Returns:
          True if the header has all required fields, False otherwise
        """

        if not set(self.__req_fields).issubset(set(header)):
            self.__error_writer.write(
                missing_field_error(set(self.__req_fields)))
            return False

        if FieldNames.MODULE not in header:
            raise GearExecutionError(
                'Module information not found in the input file')

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Apply necessary transformations on the given data row. Assumes all
        records in the CSV file belongs to the same module.

        Args:
          row: the dictionary for a row from a CSV file
          line_num: line number in the CSV file

        Returns:
          True if the row was processed without error, False otherwise
        """

        self.__error_writer.clear()

        found_all = True
        empty_fields = set()
        for field in self.__req_fields:
            if field not in row or not row[field]:
                empty_fields.add(field)
                found_all = False

        if not found_all:
            self.__error_writer.write(empty_field_error(
                empty_fields, line_num))
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        self.__set_module(row)
        # All records in the CSV file must belongs to the same module.
        if not self.__check_module(row=row, line_num=line_num):
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        # Set transformer for the module
        if not self.__transformer:
            self.__transformer = self.__transformer_factory.create(
                self.__module, self.__error_writer)

        transformed_row = self.__transformer.transform(row, line_num)
        if not transformed_row:
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        # check for duplicates (should be done after transformations)
        # if existing visit add to duplicate visit list and skip processing further
        # error logs will be updated later when processing the list of duplicates
        subject_lbl = transformed_row[self.__id_column]
        if self.__preprocessor.is_existing_visit(input_record=transformed_row,
                                                 module=self.module):
            self.__existing_visits[subject_lbl].append(transformed_row)
            return True

        transformed_row['linenumber'] = line_num
        # if not existing visit, add to current batch
        self.__add_to_current_batch(subject_lbl=subject_lbl,
                                    input_record=transformed_row)
        return True

    def update_existing_visits_error_log(
            self, downstream_gears: Optional[List[str]] = None) -> bool:
        """For re-submitted existing visits, pull error metadata from previous
        run.

        Args:
            downstream_gears (optional): list of downstream gears to copy metadata

        Returns:
            bool: True if metadata update successful
        """
        if not self.__existing_visits:
            return True

        success = True
        for visits in self.__existing_visits.values():
            for visit in visits:
                self.__error_writer.clear()
                success = success and self.__copy_downstream_gears_metadata(
                    input_record=visit, downstream_gears=downstream_gears)

        return success

    def process_current_batch(self) -> bool:
        """Process new/updated visits in the current batch. Check for
        duplicates within current batch. Apply pre-processing checks.

        Returns:
            bool: True, if all visits accepted for upload
        """
        success = True
        for subject, visits in self.__current_batch.items():
            # process in order of visit date
            sorted_visits = sorted(visits.items())
            ivp_packet = None
            prev_visit_num = None
            for visitdate, list_visits in sorted_visits:
                self.__error_writer.clear()

                # report duplicate visits within current batch
                if len(list_visits) > 1:
                    success = success and self.__report_duplicates_within_current_batch(
                        subject=subject, duplicate_records=list_visits)
                    continue

                line_num = list_visits[0].pop('linenumber')
                transformed_row = list_visits[0]

                is_ivp = False
                if transformed_row[
                        FieldNames.
                        PACKET] in self.__module_configs.initial_packets:
                    is_ivp = True
                visit_num = transformed_row[FieldNames.VISITNUM]

                # check the validity of visit numbers within current batch
                if not prev_visit_num or prev_visit_num < visit_num:
                    prev_visit_num = visit_num
                elif prev_visit_num == visit_num:
                    self.__error_writer.write(
                        preprocessing_error(
                            field=FieldNames.VISITNUM,
                            value=transformed_row[FieldNames.VISITNUM],
                            line=line_num,
                            error_code=SysErrorCodes.DIFF_VISITDATE,
                            ptid=transformed_row[FieldNames.PTID],
                            visitnum=transformed_row[FieldNames.VISITNUM]))
                    success = False
                    continue
                else:
                    self.__error_writer.write(
                        preprocessing_error(
                            field=FieldNames.VISITNUM,
                            value=transformed_row[FieldNames.VISITNUM],
                            line=line_num,
                            error_code=SysErrorCodes.LOWER_VISITNUM,
                            ptid=transformed_row[FieldNames.PTID],
                            visitnum=transformed_row[FieldNames.VISITNUM]))
                    success = False
                    continue

                if not self.__preprocessor.preprocess(
                        input_record=transformed_row,
                        module=self.module,
                        line_num=line_num,
                        ivp_record=ivp_packet):
                    self.__update_visit_error_log(input_record=transformed_row,
                                                  qc_passed=False)
                    log.error(
                        'Failed pre-processing checks in line %s - visit date %s',
                        line_num, visitdate)
                    success = False
                    continue

                if is_ivp:
                    ivp_packet = transformed_row

                # for the records that passed transformation, only obtain the log name
                # error metadata will be updated when the acquisition file is uploaded
                error_log_name = self.__update_visit_error_log(
                    input_record=transformed_row, qc_passed=True, update=False)
                if not error_log_name:
                    success = False
                    continue

                self.__transformed[subject][error_log_name] = transformed_row

        return success

    def __get_module(self, row: Dict[str, Any]) -> str:
        """Returns the module from the row.

        Args:
          row: the input row
        Returns:
          the module in uppercase.
        """
        return row.get(FieldNames.MODULE, '').upper()

    def __set_module(self, row: Dict[str, Any]) -> None:
        """Sets the module for the visitor from the row.

        Args:
          row: the input row
        """
        if not self.__module:
            self.__module = self.__get_module(row)

    def __check_module(self, row: Dict[str, Any], line_num: int) -> bool:
        """Checks the module in the row matches the module in this visitor.

        Args:
          row: the input row
          line_num: the line number of row

        Returns:
          True if module matches. False, otherwise.
        """
        row_module = self.__get_module(row)
        if self.__module == row_module:
            return True

        self.__error_writer.write(
            unexpected_value_error(
                field=FieldNames.MODULE,
                value=row_module,  # type: ignore
                expected=self.__module,  # type: ignore
                line=line_num))

        return False

    def __update_visit_error_log(
            self,
            *,
            input_record: Dict[str, Any],
            qc_passed: bool,
            update: Optional[bool] = True) -> Optional[str]:
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            input_record: input visit record
            qc_passed: whether the visit passed QC checks
            update (optional): whether to update the log or return only name

        Returns:
            str (optional): error log name if update successful, else None
        """

        if not self.__project or not self.module:
            log.warning(
                'Parent project or module not specified to upload visit error log'
            )
            return None

        error_log_name = get_error_log_name(
            module=self.module,
            input_data=input_record,
            naming_template=self.__error_log_template)

        if not update or not error_log_name:
            return error_log_name

        if not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=self.__project,
                gear_name=self.__gear_name,
                state='PASS' if qc_passed else 'FAIL',
                errors=self.__error_writer.errors()):
            log.error('Failed to update error log for visit %s, %s',
                      input_record[FieldNames.PTID],
                      input_record[self.__date_field])
            return None

        return error_log_name

    def __copy_downstream_gears_metadata(self,
                                         *,
                                         input_record: Dict[str, Any],
                                         downstream_gears: Optional[
                                             List[str]] = None,
                                         gear_state: str = 'PASS') -> bool:
        """Copy any downstream gears metadata from visit file to error log
        file.

        Args:
            input_record: input visit record
            downstream_gears (optional): list of downstream gears to copy metadata
            gear_state: status of current gear, defaults to PASS

        Returns:
            bool: True if copying metadata successful
        """

        if not self.__project or not self.module:
            log.warning(
                'Parent project or module not specified to update visit error log'
            )
            return False

        error_log_name = get_error_log_name(
            module=self.module,
            input_data=input_record,
            naming_template=self.__error_log_template)

        if not error_log_name:
            return False

        error_log_file = self.__project.get_file(error_log_name)
        if not error_log_file:
            log.error(
                'Failed to retrieve visit error log file %s from project',
                error_log_name)
            return False

        error_log_file = error_log_file.reload()
        info = error_log_file.info if (error_log_file.info
                                       and 'qc' in error_log_file.info) else {
                                           'qc': {}
                                       }

        # TODO: decide whether we need to show this warning, commenting out for now
        # self.__error_writer.write(
        #     system_error(message=(
        #         f'Found duplicate visit {visit_file_name}, exit submission pipeline'
        #     ),
        #                  error_type='warning'))

        if downstream_gears:
            visit_file = None
            visit_file_id = input_record.get('file_id')
            if visit_file_id:
                visit_file = self.__project.proxy.get_file(visit_file_id)
            else:
                log.error(
                    'Missing file id for existing visit, '
                    'failed to update error log - %s', error_log_name)

            if visit_file and visit_file.info_exists:
                visit_file = visit_file.reload()

                for ds_gear in downstream_gears:
                    ds_gear_metadata = visit_file.info.get('qc', {}).get(
                        ds_gear, {})
                    if not ds_gear_metadata:
                        gear_state = 'FAIL'
                        self.__error_writer.write(
                            system_error(message=(
                                f'QC metadata not found for gear {ds_gear} in the '
                                f'existing duplicate visit file {visit_file.name}'
                            ),
                                         error_type='warning'))
                        continue

                    info['qc'][ds_gear] = ds_gear_metadata
            else:
                gear_state = 'FAIL'
                self.__error_writer.write(
                    system_error(message=(
                        'Failed to load QC metadata from existing duplicate visit file'
                    ),
                                 error_type='warning'))
        else:
            log.warning('No downstream gears defined for current gear %s',
                        self.__gear_name)

        # add current gear
        info["qc"][self.__gear_name] = {
            "validation": {
                "state": gear_state.upper(),
                "data": self.__error_writer.errors()
            }
        }

        try:
            error_log_file.update_info(info)
        except ApiException as error:
            log.error(error)
            return False

        return True

    def __add_to_current_batch(self, subject_lbl: str,
                               input_record: Dict[str, Any]):
        """Group the input records by subject and visit date to detect any
        duplicates within the current batch.

        Args:
            subject_lbl: Flywheel subject label
            input_record: input visit record
        """
        visitdate = input_record[self.__date_field]
        if not self.__current_batch.get(subject_lbl):
            self.__current_batch[subject_lbl] = {visitdate: [input_record]}
            return

        if not self.__current_batch[subject_lbl].get(visitdate):
            self.__current_batch[subject_lbl][visitdate] = [input_record]
            return

        self.__current_batch[subject_lbl][visitdate].append(input_record)

    def __report_duplicates_within_current_batch(
            self, subject: str, duplicate_records: List[Dict[str,
                                                             Any]]) -> bool:
        """Report duplicate visits, if there are multiple records in the input
        file with same visit date for same participant.

        Args:
            subject: Flywheel subject label
            duplicate_records: list of duplicate records
        """
        input_record = None
        for record in duplicate_records:
            input_record = record
            packet = record[FieldNames.PACKET]
            visitdate = record[self.__date_field]
            line_num = record.pop('linenumber', None)
            log.error('%s - %s/%s/%s/%s',
                      preprocess_errors[SysErrorCodes.DUPLICATE_VISIT],
                      subject, self.module, packet, visitdate)
            self.__error_writer.write(
                preprocessing_error(field=self.__date_field,
                                    value=visitdate,
                                    line=line_num,
                                    error_code=SysErrorCodes.DUPLICATE_VISIT,
                                    ptid=record[FieldNames.PTID],
                                    visitnum=record[FieldNames.VISITNUM]))

        # use the last record since all records have the same PTID, visitdate
        return self.__update_visit_error_log(
            input_record=input_record,  # type: ignore
            qc_passed=False)


def notify_upload_errors():
    # TODO: send an email to nacc_dev@uw.edu
    pass


def run(*,
        input_file: TextIO,
        id_column: str,
        module: str,
        destination: ProjectAdaptor,
        transformer_factory: TransformerFactory,
        preprocessor: FormPreprocessor,
        module_configs: ModuleConfigs,
        error_writer: ListErrorWriter,
        gear_name: str,
        downstream_gears: Optional[List[str]] = None) -> bool:
    """Reads records from the input file and transforms each into a JSON file.
    Uploads the JSON file to the respective acquisition in Flywheel.

    Args:
        input_file: the input file
        id_column: the subject identifier (usually NACCID)
        module: the module label
        destination: Flyhweel project container
        transformer_factory: the factory for column transformers
        preprocessor: class to run pre-processing checks
        module_configs: form ingest configs for the module
        error_writer: the writer for error output
        gear_name: gear name
        downstream_gears: list of downstream gears

    Returns:
        bool: True if transformation/upload successful
    """

    transformed_records: DefaultDict[str, Dict[str,
                                               Dict[str,
                                                    Any]]] = defaultdict(dict)
    visitor = CSVTransformVisitor(id_column=id_column,
                                  module=module,
                                  transformed_records=transformed_records,
                                  error_writer=error_writer,
                                  transformer_factory=transformer_factory,
                                  preprocessor=preprocessor,
                                  module_configs=module_configs,
                                  gear_name=gear_name,
                                  project=destination)
    result = read_csv(input_file=input_file,
                      error_writer=error_writer,
                      visitor=visitor,
                      clear_errors=True)

    result = result and visitor.update_existing_visits_error_log(
        downstream_gears=downstream_gears)

    result = result and visitor.process_current_batch()

    if not len(transformed_records) > 0:
        return result

    uploader = FormJSONUploader(project=destination,
                                module=visitor.module,
                                gear_name=gear_name,
                                error_writer=error_writer)
    upload_status = uploader.upload(transformed_records)
    if not upload_status:
        error_writer.clear()
        error_writer.write(partially_failed_file_error())
        notify_upload_errors()

    return result and upload_status
