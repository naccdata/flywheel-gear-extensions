"""Module to extract/query form data from storage/warehouse."""

import json
import logging
from json import JSONDecodeError
from typing import Dict, List, Literal, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.keys import DefaultValues

log = logging.getLogger(__name__)

SearchOperator = Literal['=', '>', '<', '!=', '>=', '<=', '=|']


class FormsStore():
    """Class to extract/query form data from Flywheel for ingest projects."""

    def __init__(self, ingest_project: ProjectAdaptor,
                 legacy_project: Optional[ProjectAdaptor]) -> None:
        self.__ingest_project = ingest_project
        self.__legacy_project = legacy_project
        self.__proxy = self.__ingest_project.proxy

    def is_new_subject(self, subject_lbl: str) -> bool:
        """_summary_

        Args:
            subject_lbl (str): _description_

        Returns:
            bool: _description_
        """

        if self.__ingest_project.find_subject(subject_lbl):
            return False

        return not (self.__legacy_project
                    and self.__legacy_project.find_subject(subject_lbl))

    def query_ingest_project(
            self,
            *,
            subject_lbl: str,
            module: str,
            search_col: str,
            search_val: str | List[str],
            search_op: SearchOperator,
            qc_gear: Optional[str] = None,
            extra_columns: Optional[List[str]] = None,
            find_all: bool = False) -> Optional[List[Dict[str, str]]]:
        """_summary_

        Args:
            subject_lbl (str): _description_
            module (str): _description_
            search_col (str): _description_
            search_val (str | List[str]): _description_
            search_op (SearchOperator): _description_
            qc_gear (Optional[str], optional): _description_. Defaults to None.

        Returns:
            Optional[List[Dict[str, str]]]: _description_
        """
        return self.__query_project(project=self.__ingest_project,
                                    subject_lbl=subject_lbl,
                                    module=module,
                                    search_col=search_col,
                                    search_val=search_val,
                                    search_op=search_op,
                                    qc_gear=qc_gear,
                                    extra_columns=extra_columns)

    def query_legacy_project(
            self,
            *,
            subject_lbl: str,
            module: str,
            search_col: str,
            search_val: str | List[str],
            search_op: SearchOperator,
            qc_gear: Optional[str] = None,
            extra_columns: Optional[List[str]] = None,
            find_all: bool = False) -> Optional[List[Dict[str, str]]]:
        """_summary_

        Args:
            subject_lbl (str): _description_
            module (str): _description_
            search_col (str): _description_
            search_val (str): _description_
            search_op (SearchOperator): _description_
            qc_gear (Optional[str], optional): _description_. Defaults to None.

        Returns:
            Optional[List[Dict[str, str]]]: _description_
        """
        if not self.__legacy_project:
            log.warning('Legacy project not provided for group %s',
                        self.__ingest_project.group)
            return None

        return self.__query_project(project=self.__legacy_project,
                                    subject_lbl=subject_lbl,
                                    module=module,
                                    search_col=search_col,
                                    search_val=search_val,
                                    search_op=search_op,
                                    qc_gear=qc_gear,
                                    extra_columns=extra_columns)

    def __query_project(
            self,
            *,
            project: ProjectAdaptor,
            subject_lbl: str,
            module: str,
            search_col: str,
            search_val: str | List[str],
            search_op: SearchOperator,
            qc_gear: Optional[str] = None,
            extra_columns: Optional[List[str]] = None,
            find_all: bool = False) -> Optional[List[Dict[str, str]]]:
        """Retrieve previous visit records for the specified project/subject.

        Args:
            project: Flywheel project container
            subject_lbl: Flywheel subject label
            module: module name
            search_col: variable name that visits are sorted by
            search_val: cutoff value on orderby field
            search_op: search operator
            qc_gear (optional): specify qc_gear name to retrieve records that passed QC
            extra_columns (optional): list of extra columns to return if any

        Returns:
            List[Dict]: List of visits matching with the specified cutoff value,
                        sorted in descending order
        """

        subject = project.find_subject(subject_lbl)
        if not subject:
            log.warning('Subject %s is not found in project %s/%s',
                        subject_lbl, project.group, project.label)
            return None

        if isinstance(search_val,
                      List) and search_op != DefaultValues.FW_SEARCH_OR:
            log.error('Unsupported operator "%s" for list input %s', search_op,
                      search_val)
            return None

        if isinstance(search_val,
                      str) and search_op == DefaultValues.FW_SEARCH_OR:
            search_val = [search_val]

        # Dataview to retrieve the previous visits
        title = ('Visits for '
                 f'{project.group}/{project.label}/{subject_lbl}/{module}')

        search_col = f'{DefaultValues.FORM_METADATA_PATH}.{search_col}'
        columns = [
            'file.name', 'file.file_id', "file.parents.acquisition",
            "file.parents.session", search_col
        ]

        if extra_columns:
            for extra_lbl in extra_columns:
                extra_col = f'{DefaultValues.FORM_METADATA_PATH}.{extra_lbl}'
                columns.append(extra_col)

        filters = f'acquisition.label={module}'
        if not find_all:
            filters += f',{search_col}{search_op}{search_val}'

        if qc_gear:
            filters += f',file.info.qc.{qc_gear}.validation.state=PASS'

        log.info('Searching for visits matching with filters: %s', filters)

        visits = self.__proxy.get_matching_acquisition_files_info(
            container_id=subject.id,
            dv_title=title,
            columns=columns,
            filters=filters)

        if not visits:
            return None

        return sorted(visits, key=lambda d: d[search_col], reverse=True)

    def get_visit_data(self, file_name: str,
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
