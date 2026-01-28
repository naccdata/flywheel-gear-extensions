"""Module to implement form data pre-processing checks."""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Dict, List, Optional

from configs.ingest_configs import (
    FormProjectConfigs,
    ModuleConfigs,
    SupplementModuleConfigs,
)
from datastore.forms_store import FormFilter, FormsStore
from dates.form_dates import DEFAULT_DATE_FORMAT, build_date, parse_date
from keys.keys import (
    DefaultValues,
    MetadataKeys,
    PreprocessingChecks,
    SysErrorCodes,
)
from nacc_common.field_names import FieldNames
from outputs.error_writer import ErrorWriter
from outputs.errors import preprocess_errors
from uploads.acquisition import is_duplicate_dict

from preprocess.preprocessor_helpers import (
    FormPreprocessorErrorHandler,
    PreprocessingContext,
    PreprocessingException,
    validate_age_at_death,
    validate_sex_reported_on_np,
)

log = logging.getLogger(__name__)


class FormPreprocessor:
    """Class to carryout preprocessing checks for a participant visit
    record."""

    def __init__(
        self,
        form_configs: FormProjectConfigs,
        forms_store: FormsStore,
        module: str,
        module_configs: ModuleConfigs,
        error_writer: ErrorWriter,
    ) -> None:
        self.__primary_key = form_configs.primary_key
        self.__forms_store = forms_store
        self.__module = module
        self.__module_configs = module_configs
        self.__error_handler = FormPreprocessorErrorHandler(
            module=module, module_configs=module_configs, error_writer=error_writer
        )
        self.__qc_gear = form_configs.qc_gear
        self.__legacy_qc_gear = form_configs.legacy_qc_gear

        # Dispatcher mapping pre-processing checks to their corresponding handlers
        # Checks should be added in the order they need to be evaluated
        # DON'T add `duplicate-record` check here
        # It'll be evaluated directly after transformations
        self.__dispatcher: Dict[str, Callable[[PreprocessingContext], bool]] = {
            PreprocessingChecks.VERSION: self.is_accepted_version,
            PreprocessingChecks.PACKET: self.is_accepted_packet,
            PreprocessingChecks.OPTIONAL_FORMS: self._check_optional_forms_status,
            PreprocessingChecks.IVP: self._check_initial_visit,
            PreprocessingChecks.UDSV4_IVP: self._check_udsv4_initial_visit,
            PreprocessingChecks.VISIT_CONFLICT: self._check_visit_conflict,
            PreprocessingChecks.SUPPLEMENT_MODULE: self._check_supplement_module,
            PreprocessingChecks.CLINICAL_FORMS: self._check_clinical_forms,
            PreprocessingChecks.NP_UDS_RESTRICTIONS: self._check_np_uds_restrictions,
            PreprocessingChecks.NP_MLST_RESTRICTIONS: self._check_np_mlst_restrictions,
        }

        # order the preprocessing checks defined for the module
        self.__preprocess_checks: List[Callable[[PreprocessingContext], bool]] = []
        if self.__module_configs.preprocess_checks:
            for check, check_function in self.__dispatcher.items():
                if check in self.__module_configs.preprocess_checks:
                    self.__preprocess_checks.append(check_function)

    def is_accepted_packet(self, pp_context: PreprocessingContext) -> bool:
        """Validate whether the provided packet code matches with an expected
        code for the module.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: True if packet code is valid
        """

        module_configs = self.__module_configs
        input_record = pp_context.input_record

        packet = input_record[FieldNames.PACKET]
        if (
            packet not in module_configs.initial_packets
            and packet not in module_configs.followup_packets
        ):
            self.__error_handler.write_packet_error(
                pp_context=pp_context, error_code=SysErrorCodes.INVALID_PACKET
            )
            return False

        return True

    def is_accepted_version(self, pp_context: PreprocessingContext) -> bool:
        """Validate whether the provided version matches with an expected
        version for the module.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: True if form version is valid
        """

        module_configs = self.__module_configs
        input_record = pp_context.input_record

        version = float(input_record[FieldNames.FORMVER])
        accepted_versions = [float(version) for version in module_configs.versions]
        if version not in accepted_versions:
            self.__error_handler.write_formver_error(
                pp_context=pp_context, error_code=SysErrorCodes.INVALID_VERSION
            )
            return False

        return True

    def _check_optional_forms_status(self, pp_context: PreprocessingContext) -> bool:
        """Validate whether the submission status filled for optional forms for
        the respective module/version/packet.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: True if submission status filled for all optional forms
        """

        module_configs = self.__module_configs
        input_record = pp_context.input_record

        if not module_configs.optional_forms:
            log.warning(
                "Optional forms information not defined for module %s",
                self.__module,
            )
            return True

        version = float(input_record[FieldNames.FORMVER])
        packet = input_record[FieldNames.PACKET]

        optional_forms = module_configs.optional_forms.get_optional_forms(
            version=str(version), packet=packet
        )

        if not optional_forms:
            log.warning(
                "Optional forms information not available for %s/%s/%s",
                self.__module,
                version,
                packet,
            )
            return True

        found_all = True
        missing_vars = []
        for form in optional_forms:
            mode_var = f"{FieldNames.MODE}{form.lower()}"
            mode = input_record.get(mode_var, "")
            if mode is None or not str(mode).strip():
                missing_vars.append(mode_var)
                found_all = False

        if not found_all:
            self.__error_handler.write_preprocessing_error(
                field="MODExx",
                value="",
                pp_context=pp_context,
                error_code=SysErrorCodes.MISSING_SUBMISSION_STATUS,
                extra_args=missing_vars,
            )
            return False

        return True

    def __compare_visit_order(
        self,
        *,
        pp_context: PreprocessingContext,
        date_to_compare: str,
        visitnum_to_compare: str,
        date_error: str,
        visitnum_error: str,
    ) -> bool:
        """Check whether the current visit date and visit number is greater
        than the provided visit date and visit number.

        Note: CH 050225 - removed visitnum order check to support centers
        already using visitnum scheme that doesn't follow natural order

        Args:
            pp_context: PreprocessingContext, contains the input (current) record
            date_to_compare: visit date to compare with
            visitnum_to_compare: visit number to compare with
            date_error: error code to report if dates are not in order
            visitnum_error: error code to report if visit numbers are not in order

        Returns:
            bool: True if records are in correct order
        """
        date_field = self.__module_configs.date_field
        input_record = pp_context.input_record

        correct_order = True
        ptid = input_record.get(FieldNames.PTID)
        current_visitnum = input_record.get(FieldNames.VISITNUM)
        current_date = input_record[date_field]

        if date_to_compare >= current_date:
            self.__error_handler.write_date_error(
                pp_context=pp_context, error_code=date_error
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

    def _check_initial_visit(  # noqa: C901
        self, pp_context: PreprocessingContext
    ) -> bool:
        """Initial visit validations (missing, duplicate, multiple, etc)

        Args:
            pp_context: preprocessing context

        Returns:
            bool: False if any of the validations fail
        """

        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        module_configs = self.__module_configs
        input_record = pp_context.input_record
        ivp_record = pp_context.ivp_record

        date_field = module_configs.date_field
        packet = input_record[FieldNames.PACKET]
        legacy_ivp = False

        if (
            packet in module_configs.initial_packets
            and self.__forms_store.is_new_subject(pp_context.subject_lbl)
        ):
            return True

        if packet in module_configs.followup_packets and ivp_record:
            return self.__compare_visit_order(
                pp_context=pp_context,
                date_to_compare=ivp_record[module_configs.date_field],
                visitnum_to_compare=ivp_record[FieldNames.VISITNUM],
                date_error=SysErrorCodes.LOWER_FVP_VISITDATE,
                visitnum_error=SysErrorCodes.LOWER_FVP_VISITNUM,
            )

        initial_packets = self.__forms_store.query_form_data(
            subject_lbl=pp_context.subject_lbl,
            module=self.__module,
            legacy=False,
            search_col=FieldNames.PACKET,
            search_val=module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR,  # type: ignore
            extra_columns=[FieldNames.VISITNUM, date_field],
        )

        if not initial_packets:
            module = self.__module
            ivp_codes = module_configs.initial_packets
            if module_configs.legacy_module:
                module = module_configs.legacy_module.label
                date_field = module_configs.legacy_module.date_field
                if module_configs.legacy_module.initial_packets:
                    ivp_codes = module_configs.legacy_module.initial_packets

            legacy_ivp = True
            initial_packets = self.__forms_store.query_form_data(
                subject_lbl=pp_context.subject_lbl,
                module=module,
                legacy=True,
                search_col=FieldNames.PACKET,
                search_val=ivp_codes,
                search_op=DefaultValues.FW_SEARCH_OR,  # type: ignore
                extra_columns=[FieldNames.VISITNUM, date_field],
            )

        # this cannot happen, adding as a sanity check
        if initial_packets and len(initial_packets) > 1:
            self.__error_handler.write_packet_error(
                pp_context=pp_context, error_code=SysErrorCodes.MULTIPLE_IVP
            )
            return False

        initial_packet = initial_packets[0] if initial_packets else None

        date_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{date_field}"
        visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
        packet_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PACKET}"

        if packet in module_configs.followup_packets:
            if not initial_packet:
                self.__error_handler.write_packet_error(
                    pp_context=pp_context, error_code=SysErrorCodes.MISSING_IVP
                )
                return False

            return self.__compare_visit_order(
                pp_context=pp_context,
                date_to_compare=initial_packet[date_lbl],
                visitnum_to_compare=initial_packet[visitnum_lbl],
                date_error=SysErrorCodes.LOWER_FVP_VISITDATE,
                visitnum_error=SysErrorCodes.LOWER_FVP_VISITNUM,
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
                legacy_ivp
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

            self.__error_handler.write_packet_error(
                pp_context=pp_context,
                error_code=SysErrorCodes.IVP_EXISTS,
                suppress_logs=True,
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

    def __check_visitdate_visitnum(self, pp_context: PreprocessingContext) -> bool:
        """Check for conflicting visitnum for same visit date.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: False, if a conflicting visitnum found
        """
        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        subject_lbl = pp_context.subject_lbl
        input_record = pp_context.input_record
        date_field = self.__module_configs.date_field

        date_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=self.__module,
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
            self.__error_handler.write_date_error(
                pp_context=pp_context, error_code=SysErrorCodes.DIFF_VISITNUM
            )
            return False

        module = self.__module
        if self.__module_configs.legacy_module:
            module = self.__module_configs.legacy_module.label
            date_field = self.__module_configs.legacy_module.date_field

        legacy_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=True,
            search_col=date_field,
            search_val=input_record[self.__module_configs.date_field],
            search_op="=",
            extra_columns=[FieldNames.VISITNUM],
        )

        if legacy_matches and self.__find_conflicting_visits(
            visits=legacy_matches,
            field=FieldNames.VISITNUM,
            value=input_record[FieldNames.VISITNUM],
        ):
            self.__error_handler.write_date_error(
                pp_context=pp_context,
                error_code=SysErrorCodes.DIFF_VISITNUM,
            )
            return False

        return True

    def __check_visitnum_visitdate(self, pp_context: PreprocessingContext) -> bool:
        """Check for conflicting visit date for same visitnum.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: False, if a conflicting visit date found
        """
        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        subject_lbl = pp_context.subject_lbl
        input_record = pp_context.input_record
        date_field = self.__module_configs.date_field

        visitnum_matches = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=self.__module,
            legacy=False,
            search_col=FieldNames.VISITNUM,
            search_val=input_record[FieldNames.VISITNUM],
            search_op="=",
            extra_columns=[date_field],
        )

        if visitnum_matches and self.__find_conflicting_visits(
            visits=visitnum_matches, field=date_field, value=input_record[date_field]
        ):
            self.__error_handler.write_visitnum_error(
                pp_context=pp_context, error_code=SysErrorCodes.DIFF_VISITDATE
            )
            return False

        module = self.__module
        if self.__module_configs.legacy_module:
            module = self.__module_configs.legacy_module.label
            date_field = self.__module_configs.legacy_module.date_field

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
            visits=legacy_matches,
            field=date_field,
            value=input_record[self.__module_configs.date_field],
        ):
            self.__error_handler.write_visitnum_error(
                pp_context=pp_context, error_code=SysErrorCodes.DIFF_VISITDATE
            )
            return False

        return True

    def _check_udsv4_initial_visit(self, pp_context: PreprocessingContext) -> bool:
        """Validate UDSv4 I4 packet requirements.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: False, if validations fail
        """

        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        module_configs = self.__module_configs
        input_record = pp_context.input_record
        ivp_record = pp_context.ivp_record

        packet = input_record[FieldNames.PACKET]
        if self.__module != DefaultValues.UDS_MODULE or packet not in [
            DefaultValues.UDS_I4_PACKET,
            DefaultValues.UDS_F_PACKET,
        ]:
            return True

        legacy_module = (
            module_configs.legacy_module.label
            if module_configs.legacy_module
            else self.__module
        )
        date_field = (
            module_configs.legacy_module.date_field
            if module_configs.legacy_module
            else module_configs.date_field
        )

        # retrieve all legacy visits for this module (find_all=True)
        # sorted in descending of visit date
        legacy_visits = self.__forms_store.query_form_data(
            subject_lbl=pp_context.subject_lbl,
            module=legacy_module,
            legacy=True,
            search_col=date_field,
            search_val=input_record[module_configs.date_field],
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
            self.__error_handler.write_packet_error(
                pp_context=pp_context, error_code=SysErrorCodes.MISSING_UDS_V3
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
                subject_lbl=pp_context.subject_lbl,
                module=self.__module,
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
                self.__error_handler.write_packet_error(
                    pp_context=pp_context, error_code=SysErrorCodes.MISSING_UDS_I4
                )
                return False

        # If participant has UDSv3 visits and trying to submit I4 packet
        # check whether the I4 packet visit date is higher than the latest UDSv3 date
        if packet == DefaultValues.UDS_I4_PACKET:
            date_field_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{date_field}"
            visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
            return self.__compare_visit_order(
                pp_context=pp_context,
                date_to_compare=legacy_visit[date_field_lbl],
                visitnum_to_compare=legacy_visit[visitnum_lbl],
                date_error=SysErrorCodes.LOWER_I4_VISITDATE,
                visitnum_error=SysErrorCodes.LOWER_I4_VISITNUM,
            )

        return True

    def _check_visit_conflict(self, pp_context: PreprocessingContext) -> bool:
        """Check for conflicting visitnum, visitdate combinations.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: False if conflict found
        """
        return self.__check_visitdate_visitnum(
            pp_context
        ) and self.__check_visitnum_visitdate(pp_context)

    def _check_supplement_module(self, pp_context: PreprocessingContext) -> bool:
        """Check whether a matching supplement module found.

        Args:
            pp_context: preprocessing context

        Returns:
            bool: True, if a matching supplement module visit found
        """

        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        module_configs = self.__module_configs
        input_record = pp_context.input_record

        if not module_configs.supplement_module:
            log.warning(
                "Supplement module information not defined for module %s",
                self.__module,
            )
            return True

        supplement_module = module_configs.supplement_module
        supplement_visits = self.__get_supplement_visits(supplement_module, pp_context)

        if not supplement_visits:
            self.__error_handler.write_module_error(
                pp_context=pp_context,
                error_code=(
                    SysErrorCodes.UDS_NOT_MATCH
                    if supplement_module.exact_match
                    else SysErrorCodes.UDS_NOT_EXIST
                ),
            )
            return False

        # just checking for supplement existence
        if not supplement_module.exact_match:
            return True

        # If checking for exact match, there should be only one matching visit
        if len(supplement_visits) > 1:
            raise PreprocessingException(
                "More than one matching supplement visit exist for "
                f"{pp_context.subject_lbl}/{supplement_module.label}/"
                f"{input_record[module_configs.date_field]}"
            )

        return self.__check_supplement_exact_match(supplement_visits[0], pp_context)

    def __get_supplement_visits(
        self,
        supplement_module: SupplementModuleConfigs,
        pp_context: PreprocessingContext,
        qc_passed: Optional[bool] = False,
    ) -> Optional[List[Dict[str, str]]]:
        """Get supplement visits for the given supplement module.

        Args:
            supplement_module: The SupplementModuleConfigs
            pp_context: preprocessing context
            qc_passed (optional): return only QC passed visits, Default: False

        Returns:
            List of supplement visits, if found
        """
        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        module_configs = self.__module_configs
        input_record = pp_context.input_record

        supplement_visits = self.__forms_store.query_form_data(
            subject_lbl=pp_context.subject_lbl,
            module=supplement_module.label,
            legacy=False,
            search_col=supplement_module.date_field,
            search_val=input_record[module_configs.date_field],
            search_op="=" if supplement_module.exact_match else "<=",
            extra_columns=[FieldNames.PACKET, FieldNames.VISITNUM]
            if supplement_module.exact_match
            else None,
            qc_gear=self.__qc_gear if qc_passed else None,
        )

        if not supplement_visits and not supplement_module.exact_match:
            supplement_visits = self.__forms_store.query_form_data(
                subject_lbl=pp_context.subject_lbl,
                module=supplement_module.label,
                legacy=True,
                search_col=supplement_module.date_field,
                search_val=input_record[module_configs.date_field],
                search_op="<=",
                qc_gear=self.__legacy_qc_gear if qc_passed else None,
            )

        return supplement_visits

    def __check_supplement_exact_match(
        self, supplement_visit: Dict[str, str], pp_context: PreprocessingContext
    ) -> bool:
        """Check that the found supplement visit matches exactly.

        Args:
            supplement_visit: Found supplement visit to compare for exact match
            pp_context: PreprocessingContext; contains:
                input_record: Input record of current visit to compare for exact match
                line_num: Line number of input record being evaluated
        Returns:
            Whether or not the supplement is an exact match
        """
        """
        NOTE: Currently this assumes an exact match on an UDS visit, which at the
            moment is the only context in which this is called.

            Since this logic does not currently make sense for other modules, throw
            an error and implement as needed.
        """
        module_configs = self.__module_configs
        supplement_module = module_configs.supplement_module

        assert supplement_module, "supplement_module required"

        if supplement_module.label != DefaultValues.UDS_MODULE:
            raise PreprocessingException(
                f"Supplement exact match check undefined for {supplement_module.label}"
            )

        input_record = pp_context.input_record
        date_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{supplement_module.date_field}"
        visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"

        if supplement_visit[visitnum_lbl] != input_record[FieldNames.VISITNUM]:
            log.error(
                "%s - %s:%s,%s and %s:%s,%s",
                preprocess_errors[SysErrorCodes.UDS_NOT_MATCH],
                self.__module,
                input_record[module_configs.date_field],
                input_record[FieldNames.VISITNUM],
                supplement_module.label,
                supplement_visit[date_lbl],
                supplement_visit[visitnum_lbl],
            )
            self.__error_handler.write_module_error(
                pp_context=pp_context,
                error_code=SysErrorCodes.UDS_NOT_MATCH,
                suppress_logs=True,
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
                self.__module,
                packet,
                input_record[module_configs.date_field],
                input_record[FieldNames.VISITNUM],
                supplement_visit[packet_lbl],
                supplement_module.label,
                supplement_visit[date_lbl],
                supplement_visit[visitnum_lbl],
            )
            self.__error_handler.write_packet_error(
                pp_context=pp_context,
                error_code=SysErrorCodes.INVALID_MODULE_PACKET,
                suppress_logs=True,
            )
            return False

        return True

    def is_existing_visit(self, *, input_record: Dict[str, Any]) -> bool:
        """Check for existing visits.

        Args:
            input_record: input visit record

        Raises:
            PreprocessingException: If issues occur while checking for existing visits

        Returns:
            bool: True if a matching visit found
        """
        subject_lbl = input_record[self.__primary_key]
        date_field = self.__module_configs.date_field
        log.info(
            "Running existing visit check for subject %s/%s/%s",
            subject_lbl,
            self.__module,
            input_record[date_field],
        )

        filters = []
        filters.append(
            FormFilter(field=date_field, value=input_record[date_field], operator="=")
        )
        if FieldNames.VISITNUM in self.__module_configs.required_fields:
            filters.append(
                FormFilter(
                    field=FieldNames.VISITNUM,
                    value=input_record[FieldNames.VISITNUM],
                    operator="=",
                )
            )
        if FieldNames.PACKET in self.__module_configs.required_fields:
            filters.append(
                FormFilter(
                    field=FieldNames.PACKET,
                    value=input_record[FieldNames.PACKET],
                    operator="=",
                )
            )

        existing_visits = self.__forms_store.query_form_data_with_custom_filters(
            subject_lbl=subject_lbl,
            module=self.__module,
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
                f"{subject_lbl}/{self.__module}/{input_record[date_field]}"
            )

        existing_visit_info = existing_visits[0]
        existing_visit = self.__forms_store.get_visit_data(
            file_name=existing_visit_info["file.name"],
            acq_id=existing_visit_info["file.parents.acquisition"],
        )
        if not existing_visit:
            raise PreprocessingException(
                "Failed to retrieve existing visit "
                f"{subject_lbl}/{self.__module}/{input_record[date_field]}"
            )

        if is_duplicate_dict(input_record, existing_visit):
            input_record["file_id"] = existing_visit_info["file.file_id"]
            return True

        return False

    def _check_clinical_forms(self, pp_context: PreprocessingContext) -> bool:
        """Check at least one clinical form (UDS, BDS, MDS) exists.

        Args:
            pp_context: preprocessing context

        Returns:
            True if the preprocessing checks pass, false otherwise
        """
        # treat each form like a fake supplement module and see if any visits exist
        for module in [
            DefaultValues.UDS_MODULE,
            DefaultValues.BDS_MODULE,
            DefaultValues.MDS_MODULE,
        ]:
            supplement_module = SupplementModuleConfigs(
                label=module, date_field=FieldNames.DATE_COLUMN, exact_match=False
            )

            # passes if at least one visit is found
            if (
                self.__get_supplement_visits(supplement_module, pp_context, True)
                is not None
            ):
                return True

        # no clinical visits found; fail preprocessing check
        error_code = SysErrorCodes.CLINICAL_FORM_REQUIRED
        if self.__module == DefaultValues.MLST_MODULE:
            error_code = SysErrorCodes.CLINICAL_FORM_REQUIRED_MLST
        elif self.__module == DefaultValues.NP_MODULE:
            error_code = SysErrorCodes.CLINICAL_FORM_REQUIRED_NP

        self.__error_handler.write_module_error(
            pp_context=pp_context, error_code=error_code
        )

        return False

    def __check_np_uds_demographics_conflicts(
        self,
        pp_context: PreprocessingContext,
        uds_visits: List[Dict[str, Any]],
        last_uds_visit: Dict[str, Any],
        np_dod: Optional[datetime],
    ) -> bool:
        """Compare the demographics entered in NP form against UDS IVP.

        Args:
            pp_context: preprocessing context
            uds_visits: list of UDS visits metadata
            last_uds_visit: latest UDS visit record for participant
            np_dod (optional): date of death computed from NP form

        Raises:
            PreprocessingException: If issues occur while comparing NP and UDS packets

        Returns:
            bool: True if the demographic checks pass, false otherwise
        """

        # find UDS IVP packet
        ivp_visit = None
        ivp_packets = [
            DefaultValues.UDS_I4_PACKET,
            DefaultValues.UDS_I_PACKET,
            DefaultValues.UDS_IT_PACKET,
        ]

        if last_uds_visit[FieldNames.PACKET] in ivp_packets:
            ivp_visit = last_uds_visit

        num_matches = len(uds_visits)
        packet_key = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PACKET}"
        if (
            num_matches > 1
            and not ivp_visit
            and uds_visits[num_matches - 1][packet_key] in ivp_packets
        ):
            ivp_visit = self.__forms_store.get_visit_data(
                file_name=uds_visits[num_matches - 1]["file.name"],
                acq_id=uds_visits[num_matches - 1]["file.parents.acquisition"],
            )

        if not ivp_visit:
            # check the retrospective project
            ivp_matches = self.__forms_store.query_form_data(
                subject_lbl=pp_context.subject_lbl,  # type: ignore
                module=DefaultValues.UDS_MODULE,
                legacy=True,
                search_col=FieldNames.PACKET,
                search_val=ivp_packets,
                search_op=DefaultValues.FW_SEARCH_OR,  # type: ignore
                extra_columns=[FieldNames.VISITNUM, FieldNames.DATE_COLUMN],
            )

            # this should not be possible
            if not ivp_matches or len(ivp_matches) > 1:
                raise PreprocessingException(
                    "Failed to retrieve UDS IVP visit for participant "
                    f"{pp_context.subject_lbl}"
                )

            ivp_visit = self.__forms_store.get_visit_data(
                file_name=ivp_matches[0]["file.name"],
                acq_id=ivp_matches[0]["file.parents.acquisition"],
            )

        if not ivp_visit:
            raise PreprocessingException(
                "Failed to retrieve UDS IVP visit for participant "
                f"{pp_context.subject_lbl}"
            )

        valid = True
        np_record = pp_context.input_record
        npsex = np_record.get(FieldNames.NPSEX)
        if npsex is None or not validate_sex_reported_on_np(
            npsex=int(npsex), uds_record=ivp_visit
        ):
            self.__error_handler.write_preprocessing_error(
                field=FieldNames.NPSEX,
                value=npsex,
                pp_context=pp_context,
                error_code=SysErrorCodes.NP_UDS_SEX_MISMATCH,
            )
            valid = False

        death_age = np_record.get(FieldNames.NPDAGE)
        if (
            np_dod is None
            or death_age is None
            or not validate_age_at_death(
                np_dod=np_dod,
                uds_record=ivp_visit,
                np_dage=int(death_age),
            )
        ):
            self.__error_handler.write_preprocessing_error(
                field=FieldNames.NPDAGE,
                value=death_age,
                pp_context=pp_context,
                error_code=SysErrorCodes.NP_UDS_DAGE_MISMATCH,
            )
            valid = False

        return valid

    def _check_np_uds_restrictions(self, pp_context: PreprocessingContext) -> bool:
        """If participant has UDS visits, compare the details entered in the NP
        form against the UDS IVP packet and latest UDS visit.

        Args:
            pp_context: preprocessing context

        Returns:
            True if the preprocessing checks pass, false otherwise
        """

        if self.__module != DefaultValues.NP_MODULE:
            raise PreprocessingException(
                "Cannot evaluate NP demographic conflict "
                f"checks for non-NP module: {self.__module}"
            )

        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        input_record = pp_context.input_record
        uds_visits = self.__forms_store.query_form_data(
            subject_lbl=pp_context.subject_lbl,
            module=DefaultValues.UDS_MODULE,
            legacy=False,
            search_col=FieldNames.DATE_COLUMN,
            extra_columns=[FieldNames.PACKET, FieldNames.VISITNUM],
            find_all=True,
            qc_gear=self.__qc_gear,
        )

        if not uds_visits:
            uds_visits = self.__forms_store.query_form_data(
                subject_lbl=pp_context.subject_lbl,
                module=DefaultValues.UDS_MODULE,
                legacy=True,
                search_col=FieldNames.DATE_COLUMN,
                extra_columns=[FieldNames.PACKET, FieldNames.VISITNUM],
                find_all=True,
                qc_gear=self.__legacy_qc_gear,
            )

        # checks not applicable if no UDS visits
        if not uds_visits:
            return True

        # check NP DOD and last UDS visit date
        last_uds_visit = self.__forms_store.get_visit_data(
            file_name=uds_visits[0]["file.name"],
            acq_id=uds_visits[0]["file.parents.acquisition"],
        )

        if not last_uds_visit:
            raise PreprocessingException(
                "Failed to retrieve last UDS visit for participant "
                f"{pp_context.subject_lbl}"
            )

        uds_date = parse_date(
            date_string=last_uds_visit[FieldNames.DATE_COLUMN],
            formats=[DEFAULT_DATE_FORMAT],
        )

        input_record = pp_context.input_record
        np_dod = build_date(
            year=input_record.get("npdodyr"),
            month=input_record.get("npdodmo"),
            day=input_record.get("npdoddy"),
        )

        valid = True
        if np_dod and uds_date > np_dod:
            self.__error_handler.write_date_error(
                pp_context=pp_context,
                error_code=SysErrorCodes.LOWER_NP_DOD,
                date_field="npdoddy",
            )
            valid = False

        return (
            # check whether NP and UDS IVP demographics matches
            self.__check_np_uds_demographics_conflicts(
                pp_context=pp_context,
                np_dod=np_dod,
                uds_visits=uds_visits,
                last_uds_visit=last_uds_visit,
            )
            and valid
        )

    def _check_np_mlst_restrictions(self, pp_context: PreprocessingContext) -> bool:
        """Check NP/MLST restrictions; compares NP form against most recent
        MLST form.

        Args:
            pp_context: preprocessing context
        Returns:
            True if the preprocessing checks pass, false otherwise
        """
        if self.__module != DefaultValues.NP_MODULE:
            raise PreprocessingException(
                "Cannot evaluate NP/MLST preprocessing "
                + f"checks for non-NP module: {self.__module}"
            )

        assert pp_context.subject_lbl, "pp_context.subject_lbl required"

        # get most recent MLST form
        mlst_fields = ["deathyr", "deathmo", "deathdy", "deceased", "autopsy"]
        all_mlst_forms = self.__forms_store.query_form_data(
            subject_lbl=pp_context.subject_lbl,
            module=DefaultValues.MLST_MODULE,
            legacy=False,
            search_col=FieldNames.DATE_COLUMN,
            find_all=True,
            extra_columns=mlst_fields,
            qc_gear=self.__qc_gear,
        )

        # try legacy if not found
        if not all_mlst_forms:
            all_mlst_forms = self.__forms_store.query_form_data(
                subject_lbl=pp_context.subject_lbl,
                module=DefaultValues.MLST_MODULE,
                legacy=True,
                search_col=FieldNames.DATE_COLUMN,
                find_all=True,
                extra_columns=mlst_fields,
                qc_gear=self.__legacy_qc_gear,
            )

        # if no MLST forms, fails
        if not all_mlst_forms:
            self.__error_handler.write_preprocessing_error(
                field="missing_mlst_form",
                value="",
                pp_context=pp_context,
                error_code=SysErrorCodes.DEATH_DENOTED_ON_MLST,
            )

            return False

        mlst_form = all_mlst_forms[0]
        input_record = pp_context.input_record

        # preprocess-026: deceased and autopsy must be 1 in MLST form for
        # NP to be accepted
        result_death_denoted = True
        for field in ["autopsy", "deceased"]:
            value = mlst_form.get(f"{MetadataKeys.FORM_METADATA_PATH}.{field}", "")
            if value is None or str(value) != "1":
                result_death_denoted = False
                self.__error_handler.write_preprocessing_error(
                    field=field,
                    value=str(value) if value is not None else "",
                    pp_context=pp_context,
                    error_code=SysErrorCodes.DEATH_DENOTED_ON_MLST,
                )

        if not result_death_denoted:
            return False

        # preprocess-027: death dates in MLST/NP must match
        mlst_year = mlst_form.get(f"{MetadataKeys.FORM_METADATA_PATH}.deathyr")
        np_year = input_record.get("npdodyr")

        mlst_dod = build_date(
            year=mlst_year,
            month=mlst_form.get(f"{MetadataKeys.FORM_METADATA_PATH}.deathmo"),
            day=mlst_form.get(f"{MetadataKeys.FORM_METADATA_PATH}.deathdy"),
        )
        np_dod = build_date(
            year=np_year,
            month=input_record.get("npdodmo"),
            day=input_record.get("npdoddy"),
        )

        # mlst_dod and np_dod will be None if any parts are 99/invalid
        # they must both be valid for this preprocessing check to pass
        result_dod = (mlst_dod is not None and np_dod is not None) and (
            mlst_dod == np_dod
        )

        if not result_dod:
            self.__error_handler.write_date_error(
                pp_context=pp_context,
                error_code=SysErrorCodes.NP_MLST_DOD_MISMATCH,
                date_field="npdoddy",
            )

        return result_dod

    def preprocess(
        self,
        *,
        input_record: Dict[str, Any],
        line_num: int,
        ivp_record: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Run pre-processing checks for the input record.

        Args:
            input_record: input visit record
            line_num: line number in CSV file
            ivp_record (optional): IVP packet, if found in current batch, else None

        Returns:
            bool: True, if input record pass the pre-processing checks

        Raises:
            PreprocessingException: if error occur while validating
        """

        if not self.__preprocess_checks:
            log.warning(f"No preprocessing checks defined for module {self.__module}")
            return True

        subject_lbl = input_record[self.__primary_key]
        log.info(
            "Running preprocessing checks for subject %s/%s", subject_lbl, self.__module
        )

        pp_context = PreprocessingContext(
            subject_lbl=subject_lbl,
            input_record=input_record,
            line_num=line_num,
            ivp_record=ivp_record,
        )

        # execute the pre-processing checks defined for the module
        return all(check_fn(pp_context) for check_fn in self.__preprocess_checks)
