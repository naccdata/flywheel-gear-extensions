"""Pulls metadata from LONI."""

import logging
from typing import Dict, List

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from s3.s3_client import S3BucketReader
from tabular_data.site_table import SiteTable, upload_split_table

log = logging.getLogger(__name__)


def run(
    *,
    table_list: List[str],
    s3_client: S3BucketReader,
    project_map: Dict[str, ProjectAdaptor],
    dry_run: bool = False,
) -> None:
    """Pulls tabular data from S3, splits the data by center, and uploads the
    data to the center-specific FW project indicated by the project map.

    Args:
      table_list: the list of metadata table names
      s3_client: the S3 client for accessing files
      bucket_name: name of the source bucket
      project_map: map from ADCID to FW project for upload
    """

    for filename in table_list:
        log.info("Downloading %s from S3", filename)
        try:
            data = s3_client.read_data(filename=filename)
        except s3_client.exceptions.NoSuchKey:
            log.error("File %s not found in bucket %s", filename, s3_client.bucket_name)
            continue
        except s3_client.exceptions.InvalidObjectState as obj_error:
            log.error("Unable to access file %s: %s", filename, obj_error)
            continue

        table = SiteTable.create_from(data)
        if not table:
            log.error(
                "Table %s does not have a column with recognized center ID", filename
            )
            continue

        # remap projects from ADCID instead of center tag
        # TODO: need to abstract tag format
        upload_map = {
            adcid: project_map.get(f"adcid-{adcid}") for adcid in table.get_adcids()
        }

        log.info("Splitting table %s", filename)
        upload_split_table(
            table=table, project_map=upload_map, file_name=filename, dry_run=dry_run
        )
