"""Class for accessing internal or external data sources."""

import logging
from typing import Any, Dict, List, Optional

from centers.nacc_group import NACCGroup
from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from datastore.forms_store import FormsStore
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor, ProjectError
from keys.keys import DefaultValues, MetadataKeys
from nacc_common.field_names import FieldNames
from nacc_form_validator.datastore import Datastore
from rxnav.rxnav_connection import RxCuiConnection, RxCuiStatus

log = logging.getLogger(__name__)


class DatastoreException(Exception):
    pass


class DatastoreHelper(Datastore):
    """This class extends nacc_form_validator.datastore.

    Defines functions to retrieve previous visits and RxNorm validation.
    """

    def __init__(
        self,
        *,
        pk_field: str,
        adcid: int,
        module: str,
        group_id: str,
        project: ProjectAdaptor,
        proxy: FlywheelProxy,
        admin_group: NACCGroup,
        module_configs: ModuleConfigs,
        form_project_configs: FormProjectConfigs,
    ):
        """

        Args:
            pk_field: primary key field to uniquely identify a participant
            adcid: Center's ADCID
            module: module label
            group: Flywheel group id
            project: Flywheel project adaptor
            proxy: Flywheel proxy object
            admin_group: Flywheel admin group
            module_configs: form ingest configs for the module
            form_project_configs: form ingest configs for all modules for the project
        """

        super().__init__(pk_field, module_configs.date_field)

        self.__proxy = proxy
        self.__adcid = adcid
        self.__module = module.upper()
        self.__gid = group_id
        self.__project = project
        self.__admin_group = admin_group
        self.__module_configs = module_configs
        self.__form_configs = form_project_configs

        legacy_label = (
            self.__form_configs.legacy_project_label
            if self.__form_configs.legacy_project_label
            else DefaultValues.LEGACY_PRJ_LABEL
        )
        self.__forms_store = FormsStore(
            ingest_project=self.__project,
            legacy_project=self.__get_legacy_project(legacy_label),
        )

        self.__current_adcids = self.__pull_adcids_list()

        # cache for grabbing previous records
        self.__prev_visits: Dict[str, Any] = {}  # by subject, module, date

        # cache for initial visits
        self.__initial_visits: Dict[str, Any] = {}  # by subject and module

        # cache for UDS IVP visits
        self.__uds_ivp_visits: Dict[str, Any] = {}  # by subject

    def __pull_adcids_list(self) -> Optional[List[int]]:
        """Pull the list of ADCIDs from the admin group metadata project.

        Returns:
            Optional[List[int]]: List of ADCIDs
        """
        adcid_list = self.__admin_group.get_form_ingest_adcids()
        if adcid_list:
            return adcid_list

        log.error(
            "Failed to retrieve the list of ADCIDs form admin group %s",
            self.__admin_group.label,
        )
        return None

    def __get_legacy_project(self, legacy_label: str) -> Optional[ProjectAdaptor]:
        """Get the legacy form project for the center group.

        Returns:
            Optional[ProjectAdaptor]: Flywheel project adaptor or None
        """

        if legacy_label == "NA":
            log.info("Retrospective project not applicable, skipping lookup")
            return None

        retrospective_prj_label = legacy_label
        # assumes project label is in <pipeline>-<datatype>-[<study]] format
        tokens = self.__project.label.split("-")
        if len(tokens) > 2:
            retrospective_prj_label = legacy_label + "-" + "-".join(tokens[2:])

        log.info(
            f"Looking up retrospective project: {self.__gid}/{retrospective_prj_label}"
        )

        try:
            return ProjectAdaptor.create(
                proxy=self.__proxy,
                group_id=self.__gid,
                project_label=retrospective_prj_label,
            )
        except ProjectError as error:
            log.warning(
                "Failed to retrieve retrospective project %s/%s: %s",
                self.__gid,
                retrospective_prj_label,
                error,
            )
            return None

    def __validate_current_record(self, current_record: Dict[str, Any]) -> bool:
        """Validate the current record and ensure it has all required fields.
        Technically this should not happen, but run as a sanity check.

        Args:
            current_record: record currently being validated

        Returns:
            bool: whether or not record has all required fields
        """
        required_fields = [self.pk_field, self.orderby, FieldNames.MODULE]

        found_all = True
        for field in required_fields:
            if field not in current_record:
                log.error(
                    (
                        "Field %s not set in current visit data, "
                        "cannot retrieve the previous/initial visits"
                    ),
                    field,
                )
                found_all = False

        if found_all and self.__module != current_record[FieldNames.MODULE].upper():
            raise DatastoreException(
                f"Datastore module {self.__module} mismatch with the "
                f"module specified in the record {current_record[FieldNames.MODULE]}"
            )

        return found_all

    def __get_previous_visits(
        self, current_record: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """Retrieve the list of previous visits for the specified participant.

        Args:
            current_record: record currently being validated

        Returns:
            List[Dict[str, Any]]: previous visit records if found, else None
        """
        if not self.__validate_current_record(current_record):
            return None

        subject_lbl = current_record[self.pk_field]
        module = current_record[FieldNames.MODULE].upper()
        orderby_value = current_record[self.orderby]

        # see if we've already cached the previous records
        prev_visit_cached = (
            self.__prev_visits.get(subject_lbl, {})
            .get(module, {})
            .get(orderby_value, {})
            .get("cached", False)
        )
        if prev_visit_cached:
            log.info("Already searched for previous visit, using cached records")
            return self.__prev_visits[subject_lbl][module][orderby_value]["prev_visits"]

        # otherwise try to grab from either project or legacy
        prev_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=self.orderby,
            search_val=orderby_value,
            search_op="<",
            qc_gear=self.__form_configs.qc_gear,
        )

        if prev_visits:
            # cache the previous visit
            self.__prev_visits.update(
                {
                    subject_lbl: {
                        module: {
                            orderby_value: {"prev_visits": prev_visits, "cached": True}
                        }
                    }
                }
            )
            return prev_visits

        # if no previous visits found in the current project, check the legacy project
        legacy_module = (
            self.__module_configs.legacy_module.label
            if self.__module_configs.legacy_module
            else module
        )
        legacy_date = (
            self.__module_configs.legacy_module.date_field
            if self.__module_configs.legacy_module
            else self.orderby
        )

        legacy_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=legacy_module,
            legacy=True,
            search_col=legacy_date,
            search_val=orderby_value,
            search_op="<",
            qc_gear=self.__form_configs.legacy_qc_gear,
        )

        if not legacy_visits:
            log.error("No previous visits found for %s/%s", subject_lbl, module)

        # cache either the fact there is no previous visit or the found legacy one
        self.__prev_visits.update(
            {
                subject_lbl: {
                    module: {
                        orderby_value: {"prev_visits": legacy_visits, "cached": True}
                    }
                }
            }
        )

        return legacy_visits

    def __get_initial_visit(
        self, current_record: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the initial visit for the specified participant. Return the
        IVP packet for the modules that has only one initial packet, else
        return the first record sorted by visit date or form date.

        Args:
            current_record: record currently being validated

        Returns:
            Dict[str, Any]: initial visit record if found, else None
        """

        subject_lbl = current_record[self.pk_field]
        module = current_record[FieldNames.MODULE].upper()
        ivp_codes = self.__module_configs.initial_packets
        date_field = self.__module_configs.date_field

        # remove current packet from ivp_codes, e.g. I4 should not be
        # considered if this is the I4 record
        current_packet = current_record.get(FieldNames.PACKET)
        if ivp_codes and current_packet in ivp_codes:
            # each item should be unique but loop as sanity check
            ivp_codes = [packet for packet in ivp_codes if packet != current_packet]

        initial_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=FieldNames.PACKET,
            search_val=ivp_codes,
            search_op=DefaultValues.FW_SEARCH_OR,
            qc_gear=self.__form_configs.qc_gear,
            extra_columns=[date_field],
        )

        if not initial_visits:
            if self.__module_configs.legacy_module:
                date_field = self.__module_configs.legacy_module.date_field
                if self.__module_configs.legacy_module.initial_packets:
                    ivp_codes = self.__module_configs.legacy_module.initial_packets

            initial_visits = self.__forms_store.query_form_data(
                subject_lbl=subject_lbl,
                module=module,
                legacy=True,
                search_col=FieldNames.PACKET,
                search_val=ivp_codes,
                search_op=DefaultValues.FW_SEARCH_OR,
                qc_gear=self.__form_configs.legacy_qc_gear,
                extra_columns=[date_field],
            )

        if not initial_visits:
            log.warning("No initial visit found for %s, module %s", subject_lbl, module)
            return None

        if len(initial_visits) > 1:
            log.warning(
                "Multiple initial visits found for %s, module %s", subject_lbl, module
            )
            date_col_key = f"{MetadataKeys.FORM_METADATA_PATH}.{date_field}"
            initial_visits = sorted(initial_visits, key=lambda d: d[date_col_key])

        return initial_visits[0]

    def __get_uds_ivp_visit(
        self, current_record: Dict[str, Any], uds_configs: ModuleConfigs
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the UDS IVP for the specified participant if present.

        Args:
            current_record: record currently being validated
            uds_configs: form ingest configs for UDS module

        Returns:
            Dict[str, Any]: UDS IVP record if found, else None
        """

        subject_lbl = current_record[self.pk_field]
        ivp_codes = uds_configs.initial_packets
        date_field = uds_configs.date_field

        uds_ivp_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=DefaultValues.UDS_MODULE,
            legacy=False,
            search_col=FieldNames.PACKET,
            search_val=ivp_codes,
            search_op=DefaultValues.FW_SEARCH_OR,
            qc_gear=self.__form_configs.qc_gear,
            extra_columns=[date_field],
        )

        if not uds_ivp_visits:
            if uds_configs.legacy_module:
                date_field = uds_configs.legacy_module.date_field
                if uds_configs.legacy_module.initial_packets:
                    ivp_codes = uds_configs.legacy_module.initial_packets

            uds_ivp_visits = self.__forms_store.query_form_data(
                subject_lbl=subject_lbl,
                module=DefaultValues.UDS_MODULE,
                legacy=True,
                search_col=FieldNames.PACKET,
                search_val=ivp_codes,
                search_op=DefaultValues.FW_SEARCH_OR,
                qc_gear=self.__form_configs.legacy_qc_gear,
                extra_columns=[date_field],
            )

        if not uds_ivp_visits:
            log.warning("No UDS IVP record found for %s", subject_lbl)
            return None

        if len(uds_ivp_visits) > 1:
            log.error("Multiple UDS IVP records found for %s", subject_lbl)
            return None

        return uds_ivp_visits[0]

    def get_previous_record(
        self, current_record: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Overriding the abstract method, get the previous visit record for
        the specified participant.

        Args:
            current_record: record currently being validated

        Returns:
            dict[str, str]: previous visit record if found, else None
        """

        prev_visits = self.__get_previous_visits(current_record)
        if not prev_visits:
            return None

        latest_rec_info = prev_visits[0]
        return self.__forms_store.get_visit_data(
            file_name=latest_rec_info["file.name"],
            acq_id=latest_rec_info["file.parents.acquisition"],
        )

    def __check_nonempty(
        self,
        ignore_empty_fields: Optional[List[str]] = None,
        visit_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Returns whether all specified fields are not empty in visit_data.

        Args:
            ignore_empty_fields: Field(s) to check for blanks
            visit_data: Record to check
        """
        if not ignore_empty_fields:
            return True

        if not visit_data:
            return False

        return all(visit_data.get(field) for field in ignore_empty_fields)

    def get_previous_nonempty_record(
        self, current_record: Dict[str, Any], ignore_empty_fields: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Overriding the abstract method to return the previous record where
        all fields are NOT empty for the specified participant.

        Args:
            current_record: Record currently being validated
            ignore_empty_fields: Field(s) to check for blanks

        Returns:
            Dict[str, str]: Previous non-empty record if found, else None
        """
        prev_visits = self.__get_previous_visits(current_record)
        if not prev_visits:
            return None

        for visit in prev_visits:
            visit_data = self.__forms_store.get_visit_data(
                file_name=visit["file.name"], acq_id=visit["file.parents.acquisition"]
            )

            if self.__check_nonempty(ignore_empty_fields, visit_data):
                return visit_data

        log.warning(
            "No previous visit found with non-empty values for %s", ignore_empty_fields
        )
        return None

    def get_initial_record(
        self, current_record: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Overriding the abstract method, get the initial visit record for the
        specified participant.

        Args:
            current_record: record currently being validated

        Returns:
            Dict[str, Any]: initial visit record if found, None otherwise
        """

        if not self.__validate_current_record(current_record):
            return None

        subject_lbl = current_record[self.pk_field]
        module = current_record[FieldNames.MODULE].upper()

        # see if we've already cached the initial record
        cached_initial_record = self.__initial_visits.get(subject_lbl, {}).get(module)

        # will be None if we've never looked for it, and empty dict if
        # we tried looking for it but it could not be found
        if cached_initial_record is None:
            initial_record = self.__get_initial_visit(current_record)

            if not initial_record:
                initial_record = {}

            self.__initial_visits.update({subject_lbl: {module: initial_record}})
        else:
            log.info("Already searched for initial visit, using cached records")
            initial_record = cached_initial_record

        if not initial_record:
            return None

        return self.__forms_store.get_visit_data(
            file_name=initial_record["file.name"],
            acq_id=initial_record["file.parents.acquisition"],
        )

    def get_uds_ivp_record(
        self, current_record: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Overriding the abstract method, get the UDS IVP record for the
        specified participant.

        Args:
            current_record: record currently being validated

        Returns:
            Dict[str, Any]: UDS IVP record if found, else None
        """

        if not self.__validate_current_record(current_record):
            return None

        uds_configs = self.__form_configs.module_configs.get(DefaultValues.UDS_MODULE)

        if not uds_configs:
            raise DatastoreException("Module configurations not found for UDS module")

        subject_lbl = current_record[self.pk_field]

        # see if we've already cached the UDS IVP record
        cached_uds_ivp = self.__uds_ivp_visits.get(subject_lbl)

        # will be None if we've never looked for it, and empty dict if
        # we tried looking for it but it could not be found
        if cached_uds_ivp is None:
            uds_ivp_record = self.__get_uds_ivp_visit(current_record, uds_configs)

            if not uds_ivp_record:
                uds_ivp_record = {}

            self.__uds_ivp_visits.update({subject_lbl: uds_ivp_record})
        else:
            log.info("Already searched for UDS IVP visit, using cached records")
            uds_ivp_record = cached_uds_ivp

        if not uds_ivp_record:
            return None

        return self.__forms_store.get_visit_data(
            file_name=uds_ivp_record["file.name"],
            acq_id=uds_ivp_record["file.parents.acquisition"],
        )

    def is_valid_rxcui(self, drugid: int) -> bool:
        """Overriding the abstract method, check whether a given drug ID is
        valid RXCUI.

        Args:
            drugid: provided drug ID (rxcui to validate)

        Returns:
            bool: True if provided drug ID is valid, else False
        """
        return RxCuiConnection.get_rxcui_status(drugid) == RxCuiStatus.ACTIVE

    def is_valid_adcid(self, adcid: int, own: bool) -> bool:
        """Overriding the abstract method to check whether a given ADCID is
        valid.

        Args:
            adcid: provided ADCID
            own: whether to validate against own ADCID or list of current ADCIDs

        Returns:
            bool: True if provided ADCID is valid, else False
        """

        if own:
            return self.__adcid == adcid

        if self.__current_adcids:
            return adcid in self.__current_adcids

        return False
