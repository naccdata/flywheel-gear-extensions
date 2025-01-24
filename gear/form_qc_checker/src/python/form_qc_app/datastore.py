"""Class for accessing internal or external data sources."""

import json
import logging
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

from centers.nacc_group import LegacyModuleInfo, NACCGroup, ValidationError
from flywheel import Project
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from keys.keys import DefaultValues, FieldNames, MetadataKeys
from nacc_form_validator.datastore import Datastore
from rxnorm.rxnorm_connection import RxcuiStatus, RxNormConnection

log = logging.getLogger(__name__)


class DatastoreHelper(Datastore):
    """This class extends nacc_form_validator.datastore.

    Defines functions to retrieve previous visits and RxNorm validation.
    """

    def __init__(self, pk_field: str, orderby: str, proxy: FlywheelProxy,
                 adcid: int, group_id: str, project: Project,
                 admin_group: NACCGroup, legacy_label: str):
        """

        Args:
            pk_field: primary key field to uniquely identify a participant
            orderby: field to sort the records by
            proxy: Flywheel proxy object
            adcid: Center's ADCID
            group: Flywheel group id
            project: Flywheel project container
            admin_group: Flywheel admin group
            legacy_label: legacy project label
        """

        super().__init__(pk_field, orderby)

        self.__proxy = proxy
        self.__adcid = adcid
        self.__gid = group_id
        self.__project = project
        self.__admin_group = admin_group
        self.__legacy_label = legacy_label

        self.__current_adcids = self.__pull_adcids_list()
        self.__legacy_project = self.__get_legacy_project()
        self.__legacy_info = self.__get_legacy_modules_info()

        self.__prev_visits: Dict[str, Any] = {
        }  # cache for grabbing previous records

    def __pull_adcids_list(self) -> Optional[List[int]]:
        """Pull the list of ADCIDs from the admin group metadata project.

        Returns:
            Optional[List[int]]: List of ADCIDs
        """
        center_map = self.__admin_group.get_center_map()
        if center_map and center_map.centers:
            return list(center_map.centers.keys())

        log.error('Failed to retrieve the list of ADCIDs form admin group %s',
                  self.__admin_group.label)
        return None

    def __get_legacy_project(self) -> Optional[Project]:
        """Get the legacy form project for the center group.

        Returns:
            Optional[Project]: legacy Flywheel project or None
        """

        projects = self.__proxy.find_projects(
            group_id=self.__gid, project_label=self.__legacy_label)

        if not projects:
            log.warning('Failed to retrieve legacy project %s in group %s',
                        self.__legacy_label, self.__gid)
            return None

        if len(projects) > 1:
            log.warning(
                'More than one matching project with label %s in group %s',
                self.__legacy_label, self.__gid)
            return None

        return projects[0]

    def __get_legacy_modules_info(self) -> Dict[str, Dict[str, str]]:
        """Get current modules->legacy modules mapping from Flywheel admin
        group metadata project.

        Returns:
            Dict[str, Dict[str, str]]: current modules->legacy modules mapping
        """

        info = {}

        metadata_prj = self.__admin_group.find_project(
            DefaultValues.METADATA_PRJ_LBL)
        if metadata_prj:
            info = metadata_prj.get_info()

        return info.get(MetadataKeys.LEGACY_KEY, {})

    def __query_project(
            self,
            *,
            project: Project,
            subject_lbl: str,
            module: str,
            orderby: str,
            cutoff_val: str,
            qc_gear: Optional[str] = None) -> Optional[List[Dict[str, str]]]:
        """Retrieve previous visit records for the specified project/subject.

        Args:
            project: Flywheel project container
            subject_lbl: Flywheel subject label
            module: module name
            orderby: variable name that visits are sorted by
            cutoff_val: cutoff value on orderby field
            qc_gear (optional): specify qc_gear name to retrieve records that passed QC

        Returns:
            List[Dict]: List of visits matching with the specified cutoff value,
                        sorted in descending order
        """

        subject = project.subjects.find_first(f'label={subject_lbl}')
        if not subject:
            log.error('Failed to retrieve subject %s in project %s',
                      subject_lbl, project.label)
            return None

        # Dataview to retrieve the previous visits
        title = ('Visits for '
                 f'{self.__gid}/{project.label}/{subject_lbl}/{module}')

        orderby_col = f'file.info.forms.json.{orderby}'
        columns = [
            'file.name', 'file.file_id', "file.parents.acquisition",
            "file.parents.session", orderby_col
        ]
        filters = (f'acquisition.label={module},{orderby_col}<{cutoff_val}')

        if qc_gear:
            filters += f',file.info.qc.{qc_gear}.validation.state=PASS'

        visits = self.__proxy.get_matching_acquisition_files_info(
            container_id=subject.id,
            dv_title=title,
            columns=columns,
            filters=filters)

        if not visits:
            return None

        return sorted(visits, key=lambda d: d[orderby_col], reverse=True)

    def __get_visit_data(self, file_name: str,
                         acq_id: str) -> dict[str, str] | None:
        """Read the previous visit file and convert to python dictionary.

        Args:
            file_name: Previous visit file name
            acq_id: Previous visit acquisition id

        Returns:
            dict[str, str] | None: Previous visit data or None
        """
        visit_data = None

        acquisition = self.__proxy.get_acquisition(acq_id)
        file_content = acquisition.read_file(file_name)

        try:
            visit_data = json.loads(file_content)
            log.info('Found previous visit file: %s', file_name)
        except (JSONDecodeError, TypeError, ValueError) as error:
            log.error('Failed to read the previous visit file - %s : %s',
                      file_name, error)

        return visit_data

    def __get_legacy_visits(
            self, *, module: str, subject_lbl: str,
            cutoff_value: str) -> Optional[List[Dict[str, str]]]:
        """Retrieve previous visits records from the respective legacy project.

        Args:
            module: module name
            subject_lbl: Flywheel subject label
            cutoff_val: cutoff value on orderby field

        Returns:
            List[Dict]: List of visits matching with the specified cutoff value,
                        sorted in descending order
        """

        if not self.__legacy_project:
            return None

        try:
            legacy_module = LegacyModuleInfo.model_validate(
                self.__legacy_info.get(module, {}))
            log.info('Legacy module info found for module %s - %s', module,
                     legacy_module)
        # If legacy module info not in metadata, assume it is same as current version
        except ValidationError:
            legacy_module = LegacyModuleInfo(legacy_label=module,
                                             legacy_orderby=self.orderby)

        return self.__query_project(project=self.__legacy_project,
                                    subject_lbl=subject_lbl,
                                    module=legacy_module.legacy_label,
                                    orderby=legacy_module.legacy_orderby,
                                    cutoff_val=cutoff_value,
                                    qc_gear=DefaultValues.LEGACY_QC_GEAR)

    def __get_previous_visits(
            self, current_record: Dict[str,
                                       str]) -> Optional[List[Dict[str, str]]]:
        """Retrieve the list of previous visits for the specified participant.

        Args:
            current_record: record currently being validated

        Returns:
            List[Dict[str, str]]: previous visit records if found, else None
        """

        if self.pk_field not in current_record:
            log.error(('Variable %s not set in current visit data, '
                       'cannot retrieve the previous visits'), self.pk_field)
            return None

        if self.orderby not in current_record:
            log.error(('Variable %s not set in current visit data, '
                       'cannot retrieve the previous visits'), self.orderby)
            return None

        if FieldNames.MODULE not in current_record:
            log.error(('Variable %s not set in current visit data, '
                       'cannot retrieve the previous visits'),
                      FieldNames.MODULE)
            return None

        subject_lbl = current_record[self.pk_field]
        module = current_record[FieldNames.MODULE].upper()
        orderby_value = current_record[self.orderby]

        # see if we've already cached the previous records
        prev_visit_cached = self.__prev_visits.get(subject_lbl, {})\
            .get(module, {}).get(orderby_value, {}).get('cached', False)
        if prev_visit_cached:
            log.info(
                "Already searched for previous visit, using cached records")
            return self.__prev_visits[subject_lbl][module][orderby_value][
                'prev_visits']

        # otherwise try to grab from either project or legacy
        prev_visits = self.__query_project(project=self.__project,
                                           subject_lbl=subject_lbl,
                                           module=module,
                                           orderby=self.orderby,
                                           cutoff_val=orderby_value,
                                           qc_gear=DefaultValues.QC_GEAR)

        if prev_visits:
            # cache the previous visit
            self.__prev_visits.update({
                subject_lbl: {
                    module: {
                        orderby_value: {
                            'prev_visits': prev_visits,
                            'cached': True
                        }
                    }
                }
            })
            return prev_visits

        # if no previous visits found in the current project, check the legacy project
        legacy_visits = self.__get_legacy_visits(module=module,
                                                 subject_lbl=subject_lbl,
                                                 cutoff_value=orderby_value)

        if not legacy_visits:
            log.error('No previous visits found for %s/%s', subject_lbl,
                      module)

        # cache either the fact there is no previous visit or the found legacy one
        self.__prev_visits.update({
            subject_lbl: {
                module: {
                    orderby_value: {
                        'prev_visits': legacy_visits,
                        'cached': True
                    }
                }
            }
        })

        return legacy_visits

    def get_previous_record(
            self, current_record: Dict[str, str]) -> Optional[Dict[str, str]]:
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
        return self.__get_visit_data(
            latest_rec_info['file.name'],
            latest_rec_info['file.parents.acquisition'])

    def get_previous_nonempty_record(
            self, current_record: Dict[str, str],
            fields: List[str]) -> Optional[Dict[str, str]]:
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
            visit_data = self.__get_visit_data(
                visit['file.name'], visit['file.parents.acquisition'])

            if not visit_data:
                continue

            found_all = True
            for field in fields:
                if not visit_data.get(field):
                    found_all = False
                    break

            if found_all:
                return visit_data

        log.warning('No previous visit found with non-empty values for %s',
                    fields)
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
