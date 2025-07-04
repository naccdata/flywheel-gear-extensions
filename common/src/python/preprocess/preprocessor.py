"""Module to implement form data pre-processing checks."""

import logging
from typing import Any, Dict, List, Optional

from configs.ingest_configs import ModuleConfigs
from datastore.forms_store import FormFilter, FormsStore
from keys.keys import (
    DefaultValues,
    FieldNames,
    MetadataKeys,
    PreprocessingChecks,
    SysErrorCodes,
)
from outputs.errors import ListErrorWriter, preprocess_errors, preprocessing_error
from uploads.acquisition import is_duplicate_dict

log = logging.getLogger(__name__)


class PreprocessingException(Exception):
    pass


class FormPreprocessor:
    """Class to carryout preprocessing checks for a participant visit
    record."""

    def __init__(
        self,
        primary_key: str,
        forms_store: FormsStore,
        module_info: Dict[str, ModuleConfigs],
        error_writer: ListErrorWriter,
    ) -> None:
        self.__primary_key = primary_key
        self.__forms_store = forms_store
        self.__module_info = module_info
        self.__error_writer = error_writer

    def is_accepted_packet(
        self,
        *,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
    ) -> bool:
        """Validate whether the provided packet code matches with an expected
        code for the module.

        Args:
            module: module label
            module_configs: module configurations
            input_record: input record
            line_num: line number in CSV file

        Returns:
            bool: True if packet code is valid
        """

        packet = input_record[FieldNames.PACKET]
        if (
            packet not in module_configs.initial_packets
            and packet not in module_configs.followup_packets
        ):
            log.error(
                "%s - %s/%s",
                preprocess_errors[SysErrorCodes.INVALID_PACKET],
                module,
                packet,
            )
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.INVALID_PACKET,
                    ptid=input_record.get(FieldNames.PTID),
                    visitnum=input_record.get(FieldNames.VISITNUM),
                )
            )
            return False

        return True

    def is_accepted_version(
        self,
        *,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
    ) -> bool:
        """Validate whether the provided version matches with an expected
        version for the module.

        Args:
            module: module label
            module_configs: module configurations
            input_record: input record
            line_num: line number in CSV file

        Returns:
            bool: True if form version is valid
        """

        version = float(input_record[FieldNames.FORMVER])
        accepted_versions = [float(version) for version in module_configs.versions]
        if version not in accepted_versions:
            log.error(
                "%s - %s/%s",
                preprocess_errors[SysErrorCodes.INVALID_VERSION],
                module,
                version,
            )
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.FORMVER,
                    value=str(version),
                    line=line_num,
                    error_code=SysErrorCodes.INVALID_VERSION,
                    ptid=input_record.get(FieldNames.PTID),
                    visitnum=input_record.get(FieldNames.VISITNUM),
                )
            )
            return False

        return True

    def __check_optional_forms_status(
        self,
        *,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
    ) -> bool:
        """Validate whether the submission status filled for optional forms for
        the respective module/version/packet.

        Args:
            module: module label
            module_configs: module configurations
            input_record: input record
            line_num: line number in CSV file

        Returns:
            bool: True if submission status filled for all optional forms
        """

        if not module_configs.optional_forms:
            log.warning("Optional forms information not defined for module %s", module)
            return True

        version = float(input_record[FieldNames.FORMVER])
        packet = input_record[FieldNames.PACKET]

        optional_forms = module_configs.optional_forms.get_optional_forms(
            version=str(version), packet=packet
        )

        if not optional_forms:
            log.warning(
                "Optional forms information not available for %s/%s/%s",
                module,
                version,
                packet,
            )
            return True

        found_all = True
        missing_vars = []
        for form in optional_forms:
            mode_var = f"{FieldNames.MODE}{form.lower()}"
            mode = str(input_record.get(mode_var, ""))
            if not mode.strip():
                missing_vars.append(mode_var)
                found_all = False

        if not found_all:
            log.error(
                "%s - %s/%s/%s - %s",
                preprocess_errors[SysErrorCodes.MISSING_SUBMISSION_STATUS],
                module,
                version,
                packet,
                missing_vars,
            )
            self.__error_writer.write(
                preprocessing_error(
                    field="MODExx",
                    value="",
                    line=line_num,
                    error_code=SysErrorCodes.MISSING_SUBMISSION_STATUS,
                    ptid=input_record.get(FieldNames.PTID),
                    visitnum=input_record.get(FieldNames.VISITNUM),
                )
            )
            return False

        return True

    def __compare_visit_order(
        self,
        *,
        current_record: Dict[str, Any],
        date_field: str,
        date_to_compare: str,
        visitnum_to_compare: str,
        date_error: str,
        visitnum_error: str,
        line_num: int,
    ) -> bool:
        """Check whether the current visit date and visit number is greater
        than the provided visit date and visit number.

        Note: CH 050225 - removed visitnum order check to support centers
        already using visitnum scheme that doesn't follow natural order

        Args:
            current_record: record to validate
            date_field: visit date column for the module
            date_to_compare: visit date to compare with
            visitnum_to_compare: visit number to compare with
            date_error: error code to report if dates are not in order
            visitnum_error: error code to report if visit numbers are not in order
            line_num: Batch CSV file line number

        Returns:
            bool: True if records are in correct order
        """
        correct_order = True
        ptid = current_record.get(FieldNames.PTID)
        current_visitnum = current_record.get(FieldNames.VISITNUM)
        current_date = current_record[date_field]

        if date_to_compare >= current_date:
            self.__error_writer.write(
                preprocessing_error(
                    field=date_field,
                    value=current_date,
                    line=line_num,
                    error_code=date_error,
                    ptid=ptid,
                    visitnum=current_visitnum,
                )
            )
            correct_order = False

        # CH - commenting out visitnum order check

        # if get_min_value([visitnum_to_compare,
        #                   current_visitnum]) == current_visitnum:
        #     self.__error_writer.write(
        #         preprocessing_error(field=FieldNames.VISITNUM,
        #                             value=current_visitnum,
        #                             line=line_num,
        #                             error_code=visitnum_error,
        #                             ptid=ptid,
        #                             visitnum=current_visitnum))
        #     correct_order = False

        if not correct_order:
            log.error(
                "Incorrect visit order for PID %s: "
                "compared visitnum=%s, date=%s - submitted visitnum=%s, date=%s",
                ptid,
                visitnum_to_compare,
                date_to_compare,
                current_visitnum,
                current_date,
            )

        return correct_order

    def __check_initial_visit(  # noqa: C901
        self,
        *,
        subject_lbl: str,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
        ivp_record: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Initial visit validations (missing, duplicate, multiple, etc)

        Args:
            subject_lbl: Flywheel subject label
            input_record: input visit record
            module: module label
            module_configs: module configurations
            line_num: line number in CSV file
            ivp_record (optional): IVP packet, if found in current batch, else None

        Returns:
            bool: False if any of the validations fail
        """

        date_field = module_configs.date_field
        packet = input_record[FieldNames.PACKET]

        if (
            packet in module_configs.initial_packets
            and self.__forms_store.is_new_subject(subject_lbl)
        ):
            return True

        if packet in module_configs.followup_packets and ivp_record:
            return self.__compare_visit_order(
                current_record=input_record,
                date_field=module_configs.date_field,
                date_to_compare=ivp_record[module_configs.date_field],
                visitnum_to_compare=ivp_record[FieldNames.VISITNUM],
                date_error=SysErrorCodes.LOWER_FVP_VISITDATE,
                visitnum_error=SysErrorCodes.LOWER_FVP_VISITNUM,
                line_num=line_num,
            )

        initial_packets = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=FieldNames.PACKET,
            search_val=module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR,  # type: ignore
            extra_columns=[FieldNames.VISITNUM, date_field],
        )

        if not initial_packets:
            if module_configs.legacy_module:
                module = module_configs.legacy_module
            if module_configs.legacy_date:
                date_field = module_configs.legacy_date

            initial_packets = self.__forms_store.query_form_data(
                subject_lbl=subject_lbl,
                module=module,
                legacy=True,
                search_col=FieldNames.PACKET,
                search_val=module_configs.initial_packets,
                search_op=DefaultValues.FW_SEARCH_OR,  # type: ignore
                extra_columns=[FieldNames.VISITNUM, date_field],
            )

        # this cannot happen, adding as a sanity check
        if initial_packets and len(initial_packets) > 1:
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.MULTIPLE_IVP,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        initial_packet = initial_packets[0] if initial_packets else None

        date_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{date_field}"
        visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
        packet_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PACKET}"

        if packet in module_configs.followup_packets:
            if not initial_packet:
                self.__error_writer.write(
                    preprocessing_error(
                        field=FieldNames.PACKET,
                        value=packet,
                        line=line_num,
                        error_code=SysErrorCodes.MISSING_IVP,
                        ptid=input_record[FieldNames.PTID],
                        visitnum=input_record[FieldNames.VISITNUM],
                    )
                )
                return False

            return self.__compare_visit_order(
                current_record=input_record,
                date_field=module_configs.date_field,
                date_to_compare=initial_packet[date_lbl],
                visitnum_to_compare=initial_packet[visitnum_lbl],
                date_error=SysErrorCodes.LOWER_FVP_VISITDATE,
                visitnum_error=SysErrorCodes.LOWER_FVP_VISITNUM,
                line_num=line_num,
            )

        if packet in module_configs.initial_packets and initial_packet:
            # allow if this is an update to the existing initial visit packet
            if (
                initial_packet[date_lbl] == input_record[module_configs.date_field]
                and initial_packet[visitnum_lbl] == input_record[FieldNames.VISITNUM]
            ):
                return True

            # allow if this is a new I4 submission
            if (
                initial_packet[packet_lbl] == DefaultValues.UDS_I_PACKET
                and input_record[FieldNames.PACKET] == DefaultValues.UDS_I4_PACKET
            ):
                return True

            log.error(
                "%s: %s - visitnum:%s - packet:%s, %s - visitnum:%s - packet:%s",
                preprocess_errors[SysErrorCodes.IVP_EXISTS],
                initial_packet[date_lbl],
                initial_packet[visitnum_lbl],
                initial_packet[packet_lbl],
                input_record[module_configs.date_field],
                input_record[FieldNames.VISITNUM],
                input_record[FieldNames.PACKET],
            )

            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.IVP_EXISTS,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        return True

    def __find_conflicting_visits(
        self, visits: List[Dict[str, str]], field: str, value: Any
    ) -> bool:
        """Check for any conflicting visits in existing records.

        Args:
            visits: list of existing visits to check
            field: field to check
            value: input value for the field

        Returns:
            bool: True, if any conflicting visits found
        """

        field_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{field}"
        for visit in visits:
            if visit[field_lbl] != value:
                log.error(
                    "Found a visit with conflicting values [%s != %s] for field %s",
                    visit[field_lbl],
                    value,
                    field,
                )
                return True

        return False

    def __check_visitdate_visitnum(
        self,
        *,
        subject_lbl: str,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
    ) -> bool:
        """Check for conflicting visitnum for same visit date.

        Args:
            subject_lbl: Flywheel subject label
            input_record: input visit record
            module: module label
            module_configs: module configurations
            line_num: line number in CSV file

        Returns:
            bool: False, if a conflicting visitnum found
        """

        date_field = module_configs.date_field
        date_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=date_field,
            search_val=input_record[date_field],
            search_op="=",
            extra_columns=[FieldNames.VISITNUM],
        )

        if date_matches and self.__find_conflicting_visits(
            visits=date_matches,
            field=FieldNames.VISITNUM,
            value=input_record[FieldNames.VISITNUM],
        ):
            self.__error_writer.write(
                preprocessing_error(
                    field=date_field,
                    value=input_record[date_field],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITNUM,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        if module_configs.legacy_module:
            module = module_configs.legacy_module
        if module_configs.legacy_date:
            date_field = module_configs.legacy_date

        legacy_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=True,
            search_col=date_field,
            search_val=input_record[date_field],
            search_op="=",
            extra_columns=[FieldNames.VISITNUM],
        )

        if legacy_matches and self.__find_conflicting_visits(
            visits=legacy_matches,
            field=FieldNames.VISITNUM,
            value=input_record[FieldNames.VISITNUM],
        ):
            self.__error_writer.write(
                preprocessing_error(
                    field=date_field,
                    value=input_record[date_field],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITNUM,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        return True

    def __check_visitnum_visitdate(
        self,
        *,
        subject_lbl: str,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
    ) -> bool:
        """Check for conflicting visit date for same visitnum.

        Args:
            subject_lbl: Flywheel subject label
            input_record: input visit record
            module: module label
            module_configs: module configurations
            line_num: line number in CSV file

        Returns:
            bool: False, if a conflicting visit date found
        """

        date_field = module_configs.date_field
        visitnum_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=FieldNames.VISITNUM,
            search_val=input_record[FieldNames.VISITNUM],
            search_op="=",
            extra_columns=[date_field],
        )

        if visitnum_matches and self.__find_conflicting_visits(
            visits=visitnum_matches, field=date_field, value=input_record[date_field]
        ):
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITDATE,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        if module_configs.legacy_module:
            module = module_configs.legacy_module
        if module_configs.legacy_date:
            date_field = module_configs.legacy_date

        legacy_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=True,
            search_col=FieldNames.VISITNUM,
            search_val=input_record[FieldNames.VISITNUM],
            search_op="=",
            extra_columns=[date_field],
        )

        if legacy_matches and self.__find_conflicting_visits(
            visits=legacy_matches, field=date_field, value=input_record[date_field]
        ):
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    line=line_num,
                    error_code=SysErrorCodes.DIFF_VISITDATE,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        return True

    def __check_udsv4_initial_visit(
        self,
        *,
        subject_lbl: str,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
        ivp_record: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Validate UDSv4 I4 packet requirements.

        Args:
            subject_lbl: Flywheel subject label
            input_record: input visit record
            module: module label
            module_configs: module configurations
            line_num: line number in CSV file
            ivp_record (optional): IVP packet, if found in current batch, else None

        Returns:
            bool: False, if validations fail
        """

        packet = input_record[FieldNames.PACKET]
        if module != DefaultValues.UDS_MODULE or packet not in [
            DefaultValues.UDS_I4_PACKET,
            DefaultValues.UDS_F_PACKET,
        ]:
            return True

        legacy_module = (
            module_configs.legacy_module if module_configs.legacy_module else module
        )
        date_field = module_configs.date_field
        if module_configs.legacy_date:
            date_field = module_configs.legacy_date

        # retrieve all legacy visits for this module (find_all=True)
        # sorted in descending of visit date
        legacy_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=legacy_module,
            legacy=True,
            search_col=date_field,
            search_val=input_record[date_field],
            search_op="<=",
            extra_columns=[FieldNames.VISITNUM],
            find_all=True,
        )

        legacy_visit = legacy_visits[0] if legacy_visits else None

        if not legacy_visit:
            # For FVP return true, since IVP check (I or I4) is done earlier
            if packet == DefaultValues.UDS_F_PACKET:
                return True

            # For I4 reject, since UDSv3 visit must present to submit I4
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.MISSING_UDS_V3,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        # If participant has UDSv3 visits and trying to submit FVP packet
        # check whether an I4 packet already submitted for the participant
        if packet == DefaultValues.UDS_F_PACKET:
            # if I4 packet is in current batch, return True
            if (
                ivp_record
                and ivp_record[FieldNames.PACKET] == DefaultValues.UDS_I4_PACKET
            ):
                return True

            i4_visits = self.__forms_store.query_form_data(
                subject_lbl=subject_lbl,
                module=module,
                legacy=False,
                search_col=FieldNames.PACKET,
                search_val=DefaultValues.UDS_I4_PACKET,
                search_op="=",
                extra_columns=[module_configs.date_field],
            )

            i4_visit = i4_visits[0] if i4_visits else None

            date_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{module_configs.date_field}"
            if (
                not i4_visit
                or i4_visit[date_lbl] >= input_record[module_configs.date_field]
            ):
                self.__error_writer.write(
                    preprocessing_error(
                        field=FieldNames.PACKET,
                        value=packet,
                        line=line_num,
                        error_code=SysErrorCodes.MISSING_UDS_I4,
                        ptid=input_record[FieldNames.PTID],
                        visitnum=input_record[FieldNames.VISITNUM],
                    )
                )
                return False

        # If participant has UDSv3 visits and trying to submit I4 packet
        # check whether the I4 packet visit date is higher than the latest UDSv3 date
        if packet == DefaultValues.UDS_I4_PACKET:
            date_field_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{date_field}"
            visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
            return self.__compare_visit_order(
                current_record=input_record,
                date_field=module_configs.date_field,
                date_to_compare=legacy_visit[date_field_lbl],
                visitnum_to_compare=legacy_visit[visitnum_lbl],
                date_error=SysErrorCodes.LOWER_I4_VISITDATE,
                visitnum_error=SysErrorCodes.LOWER_I4_VISITNUM,
                line_num=line_num,
            )

        return True

    def __check_supplement_module(
        self,
        *,
        subject_lbl: str,
        input_record: Dict[str, Any],
        module: str,
        module_configs: ModuleConfigs,
        line_num: int,
    ) -> bool:
        """Check whether a matching supplement module found.

        Args:
            subject_lbl: Flywheel subject label
            input_record: input visit record
            module: module label
            module_configs: module configurations
            line_num: line number in CSV file

        Returns:
            bool: True, if a matching supplement module visit found
        """

        if not module_configs.supplement_module:
            log.warning(
                "Supplement module information not defined for module %s", module
            )
            return True

        supplement_module = module_configs.supplement_module

        supplement_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=supplement_module.label,
            legacy=False,
            search_col=supplement_module.date_field,
            search_val=input_record[module_configs.date_field],
            search_op="=" if supplement_module.exact_match else "<=",
            extra_columns=[FieldNames.PACKET, FieldNames.VISITNUM]
            if supplement_module.exact_match
            else None,
        )

        if not supplement_visits and not supplement_module.exact_match:
            supplement_visits = self.__forms_store.query_form_data(
                subject_lbl=subject_lbl,
                module=supplement_module.label,
                legacy=True,
                search_col=supplement_module.date_field,
                search_val=input_record[module_configs.date_field],
                search_op="<=",
            )

        if not supplement_visits:
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.MODULE,
                    value=module,
                    line=line_num,
                    error_code=(
                        SysErrorCodes.UDS_NOT_MATCH
                        if supplement_module.exact_match
                        else SysErrorCodes.UDS_NOT_EXIST
                    ),
                    ptid=input_record.get(FieldNames.PTID),
                    visitnum=input_record.get(FieldNames.VISITNUM),
                )
            )
            return False

        if not supplement_module.exact_match:  # just checking for supplement existence
            return True

        # If checking for exact match, there should be only one matching visit
        if len(supplement_visits) > 1:
            raise PreprocessingException(
                "More than one matching supplement visit exist for "
                f"{subject_lbl}/{supplement_module.label}/{input_record[module_configs.date_field]}"
            )

        supplement_visit = supplement_visits[0]
        date_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{supplement_module.date_field}"
        visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
        if supplement_visit[visitnum_lbl] != input_record[FieldNames.VISITNUM]:
            log.error(
                "%s - %s:%s,%s and %s:%s,%s",
                preprocess_errors[SysErrorCodes.UDS_NOT_MATCH],
                module,
                input_record[module_configs.date_field],
                input_record[FieldNames.VISITNUM],
                supplement_module.label,
                supplement_visit[date_lbl],
                supplement_visit[visitnum_lbl],
            )
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.MODULE,
                    value=module,
                    line=line_num,
                    error_code=SysErrorCodes.UDS_NOT_MATCH,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        packet = input_record[FieldNames.PACKET]
        packet_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PACKET}"
        if (
            packet in module_configs.followup_packets
            and supplement_visit[packet_lbl] == DefaultValues.UDS_I_PACKET
        ):
            log.error(
                "%s - %s:%s,%s,%s and %s:%s,%s,%s",
                preprocess_errors[SysErrorCodes.INVALID_MODULE_PACKET],
                module,
                packet,
                input_record[module_configs.date_field],
                input_record[FieldNames.VISITNUM],
                supplement_visit[packet_lbl],
                supplement_module.label,
                supplement_visit[date_lbl],
                supplement_visit[visitnum_lbl],
            )
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PACKET,
                    value=packet,
                    line=line_num,
                    error_code=SysErrorCodes.INVALID_MODULE_PACKET,
                    ptid=input_record[FieldNames.PTID],
                    visitnum=input_record[FieldNames.VISITNUM],
                )
            )
            return False

        return True

    def is_existing_visit(self, *, input_record: Dict[str, Any], module: str) -> bool:
        """Check for existing visits.

        Args:
            input_record: input visit record
            module (str): module

        Raises:
            PreprocessingException: If issues occur while checking for existing visits

        Returns:
            bool: True if a matching visit found
        """
        module_configs = self.__module_info.get(module)
        if not module_configs:
            raise PreprocessingException(f"No configurations found for module {module}")

        subject_lbl = input_record[self.__primary_key]
        date_field = module_configs.date_field
        log.info(
            "Running existing visit check for subject %s/%s/%s",
            subject_lbl,
            module,
            input_record[date_field],
        )

        filters = []
        filters.append(
            FormFilter(field=date_field, value=input_record[date_field], operator="=")
        )
        if FieldNames.VISITNUM in module_configs.required_fields:
            filters.append(
                FormFilter(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    operator="=",
                )
            )
        if FieldNames.PACKET in module_configs.required_fields:
            filters.append(
                FormFilter(
                    field=FieldNames.PACKET,
                    value=input_record[FieldNames.PACKET],
                    operator="=",
                )
            )

        existing_visits = self.__forms_store.query_form_data_with_custom_filters(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            order_by=date_field,
            list_filters=filters,
        )

        if not existing_visits:
            return False

        # This cannot happen
        if len(existing_visits) > 1:
            raise PreprocessingException(
                "More than one matching visit exist for "
                f"{subject_lbl}/{module}/{input_record[date_field]}"
            )

        existing_visit_info = existing_visits[0]
        existing_visit = self.__forms_store.get_visit_data(
            file_name=existing_visit_info["file.name"],
            acq_id=existing_visit_info["file.parents.acquisition"],
        )
        if not existing_visit:
            raise PreprocessingException(
                "Failed to retrieve existing visit "
                f"{subject_lbl}/{module}/{input_record[date_field]}"
            )

        if is_duplicate_dict(input_record, existing_visit):
            input_record["file_id"] = existing_visit_info["file.file_id"]
            return True

        return False

    def preprocess(  # noqa: C901
        self,
        *,
        input_record: Dict[str, Any],
        module: str,
        line_num: int,
        ivp_record: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Run pre-processing checks for the input record.

        Args:
            input_record: input visit record
            module: module label
            line_num: line number in CSV file
            ivp_record (optional): IVP packet, if found in current batch, else None

        Returns:
            bool: True, if input record pass the pre-processing checks

        Raises:
            PreprocessingException: if error occur while validating
        """

        module_configs = self.__module_info.get(module)
        if not module_configs:
            raise PreprocessingException(f"No configurations found for module {module}")

        if not module_configs.preprocess_checks:
            log.warning(f"No preprocessing checks defined for module {module}")
            return True

        subject_lbl = input_record[self.__primary_key]
        log.info("Running preprocessing checks for subject %s/%s", subject_lbl, module)

        if (
            PreprocessingChecks.VERSION in module_configs.preprocess_checks
            and not self.is_accepted_version(
                module_configs=module_configs,
                module=module,
                input_record=input_record,
                line_num=line_num,
            )
        ):
            return False

        if (
            PreprocessingChecks.PACKET in module_configs.preprocess_checks
            and not self.is_accepted_packet(
                module_configs=module_configs,
                module=module,
                input_record=input_record,
                line_num=line_num,
            )
        ):
            return False

        if (
            PreprocessingChecks.OPTIONAL_FORMS in module_configs.preprocess_checks
            and not self.__check_optional_forms_status(
                module_configs=module_configs,
                module=module,
                input_record=input_record,
                line_num=line_num,
            )
        ):
            return False

        if (
            PreprocessingChecks.IVP in module_configs.preprocess_checks
            and not self.__check_initial_visit(
                subject_lbl=subject_lbl,
                input_record=input_record,
                module=module,
                module_configs=module_configs,
                line_num=line_num,
                ivp_record=ivp_record,
            )
        ):
            return False

        if (
            PreprocessingChecks.UDSV4_IVP in module_configs.preprocess_checks
            and not self.__check_udsv4_initial_visit(
                subject_lbl=subject_lbl,
                input_record=input_record,
                module=module,
                module_configs=module_configs,
                line_num=line_num,
                ivp_record=ivp_record,
            )
        ):
            return False

        if PreprocessingChecks.VISIT_CONFLICT in module_configs.preprocess_checks:
            if not self.__check_visitdate_visitnum(
                subject_lbl=subject_lbl,
                module=module,
                module_configs=module_configs,
                input_record=input_record,
                line_num=line_num,
            ):
                return False

            if not self.__check_visitnum_visitdate(
                subject_lbl=subject_lbl,
                module=module,
                module_configs=module_configs,
                input_record=input_record,
                line_num=line_num,
            ):
                return False

        if PreprocessingChecks.SUPPLEMENT_MODULE in module_configs.preprocess_checks:
            return self.__check_supplement_module(
                subject_lbl=subject_lbl,
                module=module,
                module_configs=module_configs,
                input_record=input_record,
                line_num=line_num,
            )

        return True
