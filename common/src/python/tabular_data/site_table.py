"""Defines class for handling tabular data that needs to be split by site."""
import logging
import re
from io import StringIO
from typing import Dict, Optional, Set

import pandas as pd
from flywheel import FileSpec, Project

log = logging.getLogger(__name__)


class SiteTable:
    """Wrapper for data frame for table with Center ID column.

    Supports splitting table by Center ID. Center ID could be in column
    named ADCID or SITE.
    """

    def __init__(self, *, data: pd.DataFrame, site_id_column: str,
                 site_map: Dict[str, str]) -> None:
        self.__data_table = data
        self.__site_column = site_id_column
        self.__site_map = site_map

    @classmethod
    def create_from(cls, *, object_data: StringIO, site_id_name: str = 'ADCID') -> Optional['SiteTable']:
        """Creates table object and recognizes which column is used for site
        ID.

        Args:
          table_data: the data frame with data
        Returns:
          a wrapper object for the data frame or None if no center id column
        """
        table_data = pd.read_csv(object_data)

        if site_id_name not in table_data.columns:
            return None

        site_ids = table_data[site_id_name].to_list()
        site_map = {}
        for site_key in site_ids:
            # TODO: check if site_key is digits

            adcid = str(site_key)
            site_map[adcid] = site_key

        return SiteTable(data=table_data,
                         site_id_column=site_id_name,
                         site_map=site_map)

    def get_adcids(self) -> Set[str]:
        """Returns the set of ADCIDs for data in the table.

        Returns:
          set of ADCIDs that occur in the table
        """
        return set(self.__site_map.keys())

    def select_site(self, adcid: str) -> Optional[str]:
        """Selects the rows of the table for the site.

        Args:
          adcid: the ID of the table to select
        Returns:
          Data frame with rows of the table for the site_id
        """
        site_id = self.__site_map.get(adcid)
        if not site_id:
            return None

        site_table = self.__data_table.loc[self.__data_table[
            self.__site_column] == site_id]
        return site_table.to_csv(index=False)


def upload_split_table(*, table: SiteTable,
                       project_map: Dict[str, Optional[Project]],
                       file_name: str, dry_run: bool) -> None:
    """Splits the site table by ADCID and uploads partitions to a project.

    Args:
      table: the table to be split
      project_map: ADCID to project mapping
    """
    for adcid, project in project_map.items():
        if not project:
            log.warning('No project for ADCID %s', adcid)
            continue

        site_table = table.select_site(adcid)
        if not site_table:
            log.error('Unable to select site data for ADCID %s', adcid)
            continue

        if dry_run:
            log.info('Dry run: would upload file %s to project %s', file_name,
                     project.label)
            continue

        file_spec = FileSpec(name=file_name,
                             contents=site_table,
                             content_type='text/csv')
        project.upload_file(file_spec)
