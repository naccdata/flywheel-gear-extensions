"""Class for accessing internal or external data sources."""

import logging
from typing import Any, Dict, List, Optional

from centers.nacc_group import NACCGroup
from configs.ingest_configs import ModuleConfigs
from datastore.forms_store import FormsStore
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor, ProjectError
from keys.keys import DefaultValues, MetadataKeys
from nacc_common.field_names import FieldNames
from nacc_form_validator.datastore import Datastore
from rxnorm.rxnorm_connection import RxcuiStatus, RxNormConnection

log = logging.getLogger(__name__)


class DatastoreHelper(Datastore):
    """This class extends nacc_form_validator.datastore.

    Defines functions to retrieve previous visits and RxNorm validation.
    """

    def __init__(
        self,
        *,
        pk_field: str,
        adcid: int,
        group_id: str,
        project: ProjectAdaptor,
        proxy: FlywheelProxy,
        admin_group: NACCGroup,
        module_configs: ModuleConfigs,
        legacy_label: str,
    ):
        """

        Args:
            pk_field: primary key field to uniquely identify a participant
            adcid: Center's ADCID
            group: Flywheel group id
            project: Flywheel project adaptor
            proxy: Flywheel proxy object
            admin_group: Flywheel admin group
            module_configs: form ingest configs for the module
            legacy_label: legacy project label
        """

        super().__init__(pk_field, module_configs.date_field)

        self.__proxy = proxy
        self.__adcid = adcid
        self.__gid = group_id
        self.__project = project
        self.__admin_group = admin_group
        self.__module_configs = module_configs

        self.__forms_store = FormsStore(
            ingest_project=self.__project,
            legacy_project=self.__get_legacy_project(legacy_label),
        )

        self.__current_adcids = self.__pull_adcids_list()

        # cache for grabbing previous records
        self.__prev_visits: Dict[str, Any] = {}
        self.__initial_visit: Dict[str, Any] | None = None

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
            qc_gear=DefaultValues.QC_GEAR,
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
            qc_gear=DefaultValues.LEGACY_QC_GEAR,
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

    def __get_initial_visit(self, current_record: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve the initial visit for the specified participant. Return the
        IVP packet for the modules that has only one initial packet, else
        return the first record sorted by visit date or form date.

        Args:
            current_record: record currently being validated

        Returns:
            List[Dict[str, Any]: initial visit record if found, else empty dict
        """
        if not self.__validate_current_record(current_record):
            return {}

        subject_lbl = current_record[self.pk_field]
        module = current_record[FieldNames.MODULE].upper()
        date_field = self.__module_configs.date_field

        initial_visits = self.__forms_store.query_form_data(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=FieldNames.PACKET,
            search_val=self.__module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR,
            qc_gear=DefaultValues.QC_GEAR,
            extra_columns=[date_field],
        )

        if not initial_visits:
            ivp_codes = self.__module_configs.initial_packets
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
                qc_gear=DefaultValues.QC_GEAR,
                extra_columns=[date_field],
            )

        if not initial_visits:
            log.warning("No initial visit found for %s, module %s", subject_lbl, module)
            return {}

        if len(initial_visits) > 1:
            log.warning(
                "Multiple initial visits found for %s, module %s", subject_lbl, module
            )
            date_col_key = f"{MetadataKeys.FORM_METADATA_PATH}.{date_field}"
            initial_visits = sorted(initial_visits, key=lambda d: d[date_col_key])

        return initial_visits[0]

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
        self,
        current_record: Dict[str, Any],
        ignore_empty_fields: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Overriding the abstract method, get the initial visit record for the
        specified participant if non-empty.

        Args:
            current_record: record currently being validated
            ignore_empty_fields: Field(s) to check for blanks

        Returns:
            dict[str, str]: initial visit record if found and non-empty,
                            None otherwise
        """
        # will be None if we've never looked for it, and empty dict if
        # we tried looking for it but it could not be found
        if self.__initial_visit is None:
            self.__initial_visit = self.__get_initial_visit(current_record)

        if not self.__initial_visit:
            return None

        visit_data = self.__forms_store.get_visit_data(
            file_name=self.__initial_visit["file.name"],
            acq_id=self.__initial_visit["file.parents.acquisition"],
        )

        if self.__check_nonempty(ignore_empty_fields, visit_data):
            return visit_data

        log.warning(
            "No initial visit found with non-empty values for %s", ignore_empty_fields
        )
        return None

    def is_valid_rxcui(self, drugid: int) -> bool:
        """Overriding the abstract method, check whether a given drug ID is
        valid RXCUI.

        Args:
            drugid: provided drug ID (rxcui to validate)

        Returns:
            bool: True if provided drug ID is valid, else False
        """
        return RxNormConnection.get_rxcui_status(drugid) == RxcuiStatus.ACTIVE

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
