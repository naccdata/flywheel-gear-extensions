"""Module to extract/query form data from storage/warehouse."""

import json
import logging
from json import JSONDecodeError
from typing import Dict, List, Literal, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.keys import DefaultValues
from pydantic import BaseModel

log = logging.getLogger(__name__)

SearchOperator = Literal['=', '>', '<', '!=', '>=', '<=', '=|']


class FormsStoreException(Exception):
    pass


class FormQueryArgs(BaseModel):
    """Make pydantic model for query arguments to make them easier to pass
    around."""
    subject_lbl: str
    module: str
    legacy: bool
    search_col: str
    search_val: Optional[str] | Optional[List[str]] = None
    search_op: Optional[SearchOperator] | Optional[str] = None
    qc_gear: Optional[str] = None
    extra_columns: Optional[List[str]] = None
    find_all: bool = False


class FormsStore():
    """Class to extract/query form data from Flywheel for ingest projects."""

    def __init__(self, ingest_project: ProjectAdaptor,
                 legacy_project: Optional[ProjectAdaptor]) -> None:
        self.__ingest_project = ingest_project
        self.__legacy_project = legacy_project
        self.__proxy = self.__ingest_project.proxy

    def is_new_subject(self, subject_lbl: str) -> bool:
        """Check whether the given subject exists.

        Args:
            subject_lbl: Flywheel subject label

        Returns:
            bool: True, if this is a new subject
        """

        if self.__ingest_project.find_subject(subject_lbl):
            return False

        return not (self.__legacy_project
                    and self.__legacy_project.find_subject(subject_lbl))

    def query_form_data(  # noqa: C901
            self,
            *,
            subject_lbl: str,
            module: str,
            legacy: bool,
            search_col: str,
            search_val: Optional[str] | Optional[List[str]] = None,
            search_op: Optional[SearchOperator] | Optional[str] = None,
            qc_gear: Optional[str] = None,
            extra_columns: Optional[List[str]] = None,
            find_all: bool = False) -> Optional[List[Dict[str, str]]]:
        """Retrieve previous visit records for the specified project/subject.

        Args:
            subject_lbl: Flywheel subject label
            module: module name
            legacy: whether to query legacy project or not
            search_col: field to search
            search_val: value(s) to search
            search_op: search operator
            qc_gear (optional): specify qc_gear name to retrieve records that passed QC
            extra_columns (optional): list of extra columns to return if any
            find_all (optional): bypass search and return all visits for the module

        Returns:
            List[Dict] (optional): List of visits matching the search,
                                sorted in descending order or None
        """

        if legacy and not self.__legacy_project:
            log.warning('Legacy project not provided for group %s',
                        self.__ingest_project.group)
            return None

        project = self.__legacy_project if legacy else self.__ingest_project
        if not project:  # this cannot happen
            raise FormsStoreException(
                f'Project not found to query data for subject {subject_lbl}/{module}'
            )

        subject = project.find_subject(subject_lbl)
        if not subject:
            log.warning('Subject %s is not found in project %s/%s',
                        subject_lbl, project.group, project.label)
            return None

        if isinstance(search_val,
                      List) and search_op != DefaultValues.FW_SEARCH_OR:
            raise FormsStoreException(
                'Unsupported operator "%s" for list input %s', search_op,
                search_val)

        if not find_all and (not search_val or not search_op):
            raise FormsStoreException(
                'search_val and search_op must be set if find_all is False')

        if isinstance(search_val,
                      str) and search_op == DefaultValues.FW_SEARCH_OR:
            search_val = [search_val.replace(", ", ",")]

        # remove spaces for OR search (=|)
        if isinstance(search_val,
                      List) and search_op == DefaultValues.FW_SEARCH_OR:
            search_val = f"[{','.join(search_val)}]"

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
