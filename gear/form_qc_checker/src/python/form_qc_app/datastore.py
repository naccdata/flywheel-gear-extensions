"""Class for accessing internal or external data sources."""

import logging
from typing import Any, Dict, List, Optional

from centers.nacc_group import NACCGroup
from configs.ingest_configs import ModuleConfigs
from datastore.forms_store import FormsStore
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor, ProjectError
from keys.keys import DefaultValues, FieldNames
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

        try:
            return ProjectAdaptor.create(
                proxy=self.__proxy, group_id=self.__gid, project_label=legacy_label
            )
        except ProjectError as error:
            log.warning(
                "Failed to retrieve legacy project %s/%s: %s",
                self.__gid,
                legacy_label,
                error,
            )
            return None

    def __get_previous_visits(
        self, current_record: Dict[str, str]
    ) -> Optional[List[Dict[str, str]]]:
        """Retrieve the list of previous visits for the specified participant.

        Args:
            current_record: record currently being validated

        Returns:
            List[Dict[str, str]]: previous visit records if found, else None
        """

        required_fields = [self.pk_field, self.orderby, FieldNames.MODULE]

        found_all = True
        for field in required_fields:
            if field not in current_record:
                log.error(
                    (
                        "Field %s not set in current visit data, "
                        "cannot retrieve the previous visits"
                    ),
                    field,
                )
                found_all = False

        # this cannot happen, just a sanity check
        if not found_all:
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
            self.__module_configs.legacy_module
            if self.__module_configs.legacy_module
            else module
        )
        legacy_date = (
            self.__module_configs.legacy_date
            if self.__module_configs.legacy_date
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

    def get_previous_record(
        self, current_record: Dict[str, str]
    ) -> Optional[Dict[str, str]]:
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

    def get_previous_nonempty_record(
        self, current_record: Dict[str, str], fields: List[str]
    ) -> Optional[Dict[str, str]]:
        """Overriding the abstract method to return the previous record where
        all fields are NOT empty for the specified participant.

        Args:
            current_record: Record currently being validated
            fields: Field(s) to check for blanks

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

            if not visit_data:
                continue

            found_all = True
            for field in fields:
                if not visit_data.get(field):
                    found_all = False
                    break

            if found_all:
                return visit_data

        log.warning("No previous visit found with non-empty values for %s", fields)
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
