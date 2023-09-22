"""Pulls SCAN metadata from LONI."""

import logging
from csv import DictReader
from typing import Mapping, Optional

from loni.loni_connection import LONIConnection, LONIConnectionError
from projects.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)


def run(*, flywheel_proxy: FlywheelProxy, loni_proxy: LONIConnection):
    """Pulls SCAN metadata from LONI and attaches to participants.

    Args:
      flywheel_proxy: the proxy for the Flywheel instance
      loni_proxy: the proxy for the LONI IDA server
    """

    upload_data = pull_table(proxy=loni_proxy,
                             table_name="v_scan_upload_with_qc")
    mri_dashboard = pull_table(proxy=loni_proxy,
                               table_name="v_scan_mri_dashboard")
    pet_dashboard = pull_table(proxy=loni_proxy,
                               table_name="v_scan_pet_dashboard")

    try:
        mri_dashboard = loni_proxy.get_table(database_name="scan",
                                             table_name="v_scan_mri_dashboard")
    except LONIConnectionError as error:
        log.error("%s", error)

    try:
        pet_dashboard = loni_proxy.get_table(database_name="scan",
                                             table_name="v_scan_pet_dashboard")
    except LONIConnectionError as error:
        log.error("%s", error)


def pull_table(*, proxy, table_name) -> Optional[Mapping[str, str]]:
    try:
        table = proxy.get_table(database_name="scan", table_name=table_name)
    except LONIConnectionError as error:
        log.error("%s", error)
        return None

    table_lines = table.splitlines()
    reader = DictReader(table_lines)
    table_map = {}
    #

    return table
