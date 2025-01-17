"""Module to implement form data pre-processing checks."""

import logging
from typing import Any, Dict, List, Optional

from datastore.forms_store import FormsStore
from keys.keys import DefaultValues, FieldNames, SysErrorCodes
from outputs.errors import ListErrorWriter, preprocess_errors, preprocessing_error
from pydantic import BaseModel

log = logging.getLogger(__name__)


class PreprocessingException(Exception):
    pass


class ModuleConfigs(BaseModel):
    initial_packets: List[str]
    followup_packets: List[str]
    versions: List[str]
    date_field: str
    legacy_module: Optional[str] = None
    legacy_date: Optional[str] = None

    @classmethod
    def create(cls, label: str, configs: Dict[str, Any]) -> 'ModuleConfigs':
        """Create from given configs."""
        return ModuleConfigs(initial_packets=configs['initial_packets'],
                             followup_packets=configs['followup_packets'],
                             versions=configs['versions'],
                             date_field=configs['date_field'],
                             legacy_module=configs.get('legacy_module', label),
                             legacy_date=configs.get('legacy_date',
                                                     configs['date_field']))


class FormProjectConfigs(BaseModel):
    primary_key: str
    legacy_project_label: Optional[str] = DefaultValues.LEGACY_PRJ_LABEL
    module_configs: Dict[str, ModuleConfigs]


class FormPreprocessor():
    """Class to carryout preprocessing checks for a participant visit
    record."""

    def __init__(self, primary_key: str, forms_store: FormsStore,
                 module_info: Dict[str, ModuleConfigs],
                 error_writer: ListErrorWriter) -> None:
        self.__primary_key = primary_key
        self.__forms_store = forms_store
        self.__module_info = module_info
        self.__error_writer = error_writer

    def __is_accepted_packet(self, *, input_record: Dict[str, Any],
                             module: str, module_configs: ModuleConfigs,
                             line_num: int) -> bool:
        """_summary_

        Args:
            module (str): _description_
            module_configs (ModuleConfigs): _description_
            input_record: _description_
            line_num (int): _description_

        Returns:
            bool: _description_
        """

        packet = input_record[FieldNames.PACKET]
        if (packet not in module_configs.initial_packets
                and packet not in module_configs.followup_packets):
            log.error('%s - %s/%s',
                      preprocess_errors[SysErrorCodes.INVALID_PACKET], module,
                      packet)
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.INVALID_PACKET,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        return True

    def __is_accepted_version(self, *, input_record: Dict[str, Any],
                              module: str, module_configs: ModuleConfigs,
                              line_num: int) -> bool:
        """_summary_

        Args:
            module (str): _description_
            module_configs (ModuleConfigs): _description_
            version (str): _description_
            line_num (int): _description_

        Returns:
            bool: _description_
        """

        version = input_record[FieldNames.FORMVER]
        if version not in module_configs.versions:
            log.error('%s - %s/%s',
                      preprocess_errors[SysErrorCodes.INVALID_VERSION], module,
                      version)
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=version,
                    line=line_num,
                    error_code=SysErrorCodes.INVALID_VERSION,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        return True

    def __check_initial_visit(  # noqa: C901
            self, *, subject_lbl: str, input_record: Dict[str, Any],
            module: str, module_configs: ModuleConfigs, line_num: int) -> bool:
        """_summary_

        Args:
            subject_lbl (str): _description_
            input_record: _description_
            module: module
            module_configs (str): _description_
            line_num: the line number of the input record

        Raises:
            PreprocessingException: _description_

        Returns:
            bool: _description_
        """

        packet = input_record[FieldNames.PACKET]

        if self.__forms_store.is_new_subject(subject_lbl):
            if packet in module_configs.initial_packets:
                return True

            if packet in module_configs.followup_packets:
                log.error('%s - %s',
                          preprocess_errors[SysErrorCodes.MISSING_IVP], packet)
                self.__error_writer.write(
                    preprocessing_error(
                        field=FieldNames.PACKET,
                        value=packet,
                        line=line_num,
                        error_code=SysErrorCodes.MISSING_IVP,
                        ptid=input_record[FieldNames.PTID],
                        visitnum=input_record[FieldNames.VISITNUM]))
                return False

        initial_packets = self.__forms_store.query_ingest_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=FieldNames.PACKET,
            search_val=module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR)  # type: ignore

        if not initial_packets:
            if module_configs.legacy_module:
                module = module_configs.legacy_module

            initial_packets = self.__forms_store.query_legacy_project(
                subject_lbl=subject_lbl,
                module=module,
                search_col=FieldNames.PACKET,
                search_val=module_configs.initial_packets,
                search_op=DefaultValues.FW_SEARCH_OR)  # type: ignore

        if initial_packets and len(initial_packets) > 1:
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.MULTIPLE_IVP,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        initial_packet = initial_packets[0] if initial_packets else None

        if packet in module_configs.followup_packets and not initial_packet:
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.MISSING_IVP,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        if packet in module_configs.initial_packets and initial_packet:
            ivp_record = self.__forms_store.get_visit_data(
                initial_packet['file.name'],
                initial_packet['file.parents.acquisition'])

            if not ivp_record:
                raise PreprocessingException(
                    f"Error reading previous visit file {initial_packet['file.name']}"
                )

            # allow if this is an update to the existing initial visit packet
            if (ivp_record[module_configs.date_field]
                    == input_record[module_configs.date_field]
                    and ivp_record[FieldNames.VISITNUM]
                    == input_record[FieldNames.VISITNUM]):
                return True

            # allow if this is a new I4 submission
            if (ivp_record[FieldNames.PACKET] == DefaultValues.UDS_I_PACKET
                    and input_record[FieldNames.PACKET]
                    == DefaultValues.UDS_I4_PACKET):
                return True

            log.error('%s: %s - %s, %s - %s',
                      preprocess_errors[SysErrorCodes.IVP_EXISTS],
                      ivp_record[module_configs.date_field],
                      ivp_record[FieldNames.VISITNUM],
                      input_record[module_configs.date_field],
                      input_record[FieldNames.VISITNUM])

            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.IVP_EXISTS,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        return True

    def __find_conflicting_visits(self, visits: List[Dict[str, str]],
                                  field: str, value: Any) -> bool:
        """_summary_

        Args:
            visits (List[Dict[str, str]]): _description_
            field (str): _description_
            value (Any): _description_

        Returns:
            bool: _description_
        """

        field_lbl = f'{DefaultValues.FORM_METADATA_PATH}.{field}'
        for visit in visits:
            if visit[field_lbl] != value:
                log.error(
                    'Found a visit with conflicting values [%s != %s] for field %s',
                    visit[field_lbl], value, field)
                return True

        return False

    def __check_visitdate_visitnum(self, *, subject_lbl: str,
                                   input_record: Dict[str, Any], module: str,
                                   module_configs: ModuleConfigs,
                                   line_num: int) -> bool:
        """_summary_

        Args:
            subject_lbl (str): _description_
            input_record (Dict[str, Any]): _description_
            module (str): _description_
            module_configs (str): _description_
            line_num: the line number of the input record

        Returns:
            bool: _description_
        """

        date_field = module_configs.date_field
        date_matches = self.__forms_store.query_ingest_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=date_field,
            search_val=input_record[date_field],
            search_op='=',
            extra_columns=[FieldNames.VISITNUM])

        if (date_matches and self.__find_conflicting_visits(
                visits=date_matches,
                field=FieldNames.VISITNUM,
                value=input_record[FieldNames.VISITNUM])):
            self.__error_writer.write(
                preprocessing_error(
                    field=date_field,
                    value=input_record[date_field],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITNUM,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        if module_configs.legacy_module:
            module = module_configs.legacy_module
        if module_configs.legacy_date:
            date_field = module_configs.legacy_date

        legacy_matches = self.__forms_store.query_legacy_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=date_field,
            search_val=input_record[date_field],
            search_op='=',
            extra_columns=[FieldNames.VISITNUM])

        if (legacy_matches and self.__find_conflicting_visits(
                visits=legacy_matches,
                field=FieldNames.VISITNUM,
                value=input_record[FieldNames.VISITNUM])):
            self.__error_writer.write(
                preprocessing_error(
                    field=date_field,
                    value=input_record[date_field],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITNUM,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        return True

    def __check_visitnum_visitdate(self, *, subject_lbl: str,
                                   input_record: Dict[str, Any], module: str,
                                   module_configs: ModuleConfigs,
                                   line_num: int) -> bool:
        """_summary_

        Args:
            subject_lbl (str): _description_
            input_record (Dict[str, Any]): _description_
            module (str): _description_
            module_configs (str): _description_
            line_num: the line number of the input record

        Returns:
            bool: _description_
        """

        date_field = module_configs.date_field
        visitnum_matches = self.__forms_store.query_ingest_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=FieldNames.VISITNUM,
            search_val=input_record[FieldNames.VISITNUM],
            search_op='=',
            extra_columns=[date_field])

        if (visitnum_matches and self.__find_conflicting_visits(
                visits=visitnum_matches,
                field=date_field,
                value=input_record[date_field])):
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITDATE,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        if module_configs.legacy_module:
            module = module_configs.legacy_module
        if module_configs.legacy_date:
            date_field = module_configs.legacy_date

        legacy_matches = self.__forms_store.query_legacy_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=FieldNames.VISITNUM,
            search_val=input_record[FieldNames.VISITNUM],
            search_op='=',
            extra_columns=[date_field])

        if (legacy_matches and self.__find_conflicting_visits(
                visits=legacy_matches,
                field=date_field,
                value=input_record[date_field])):
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITDATE,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        return True

    def __check_udsv4_initial_visit(self, *, subject_lbl: str,
                                    input_record: Dict[str, Any], module: str,
                                    module_configs: ModuleConfigs,
                                    line_num: int) -> bool:
        """_summary_

        Args:
            subject_lbl (str): _description_
            input_record (Dict[str, Any]): _description_
            module (str): _description_
            module_configs (str): _description_
            line_num: the line number of the input record

        Returns:
            bool: _description_
        """

        if input_record[FieldNames.PACKET] != DefaultValues.UDS_I4_PACKET:
            return True

        date_field = module_configs.date_field
        if module_configs.legacy_module:
            module = module_configs.legacy_module
        if module_configs.legacy_date:
            date_field = module_configs.legacy_date

        legacy_visits = self.__forms_store.query_legacy_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=date_field,
            search_val=input_record[date_field],
            search_op='<=',
            extra_columns=[FieldNames.VISITNUM],
            find_all=True)

        legacy_visit = legacy_visits[0] if legacy_visits else None

        date_field_lbl = f'{DefaultValues.FORM_METADATA_PATH}.{date_field}'
        if (not legacy_visit or legacy_visit[date_field_lbl]
                >= input_record[module_configs.date_field]):
            self.__error_writer.write(
                preprocessing_error(
                    field=module_configs.date_field,
                    value=input_record[module_configs.date_field],
                    line=line_num,
                    error_code=SysErrorCodes.LOWER_I4_VISITDATE,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        visitnum_lbl = f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
        if legacy_visit[visitnum_lbl] >= input_record[FieldNames.VISITNUM]:
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    line=line_num,
                    error_code=SysErrorCodes.LOWER_I4_VISITNUM,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM]))
            return False

        return True

    def preprocess(self, *, input_record: Dict[str, Any], module: str,
                   line_num: int) -> bool:
        """_summary_

        Args:
            input_record (Dict[str, Any]): _description_
            module (str): _description_
            line_num: the line number of the input record

        Returns:
            bool: _description_
        """

        module_configs = self.__module_info.get(module)
        if not module_configs:
            raise PreprocessingException(
                f'No configurations found for module {module}')

        subject_lbl = input_record[self.__primary_key]
        log.info('Running preprocessing checks for subject %s', subject_lbl)

        if not self.__is_accepted_version(module_configs=module_configs,
                                          module=module,
                                          input_record=input_record,
                                          line_num=line_num):
            return False

        if not self.__is_accepted_packet(module_configs=module_configs,
                                         module=module,
                                         input_record=input_record,
                                         line_num=line_num):
            return False

        if not self.__check_initial_visit(subject_lbl=subject_lbl,
                                          input_record=input_record,
                                          module=module,
                                          module_configs=module_configs,
                                          line_num=line_num):
            return False

        if not self.__check_udsv4_initial_visit(subject_lbl=subject_lbl,
                                                input_record=input_record,
                                                module=module,
                                                module_configs=module_configs,
                                                line_num=line_num):
            return False

        if not self.__check_visitdate_visitnum(subject_lbl=subject_lbl,
                                               module=module,
                                               module_configs=module_configs,
                                               input_record=input_record,
                                               line_num=line_num):
            return False

        return self.__check_visitnum_visitdate(subject_lbl=subject_lbl,
                                               module=module,
                                               module_configs=module_configs,
                                               input_record=input_record,
                                               line_num=line_num)
