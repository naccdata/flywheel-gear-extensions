"""Defines ADD DETAIL computation."""
import datetime
import json
import logging
import yaml
from typing import Any, Dict, List, Optional

from curator.symbol_table import SymbolTable
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    GearExecutionError,
    InputFileWrapper,
)
from s3.s3_client import S3BucketReader

from nacc_form_validator.normalization import NACCNormalizer

log = logging.getLogger(__name__)


class FormCurator():

    def __init__(self,
                 context: GearToolkitContext,
                 curation_schema_uri: str,
                 form_date_key: str,
                 aggregation_containers: List[str],
                 apply_containers: List[str]):
        self.context = context
        self.curation_schema = self.__load_from_s3(curation_schema_uri)
        self.form_date_key = form_date_key
        self.aggregation_containers = aggregation_containers
        self.apply_containers = apply_containers

    def curate(self, document: Dict[Any, Any], file) -> Dict[Any, Any]:
        """Curates the file. Returns the curated results
        as a SymbolTable.

        Args:
            
            file_: JSON data for file
        """
        log.info("Curating data")
        #log.info(json.dumps(self.curation_schema, indent=4))

        normalizer = NACCNormalizer(schema=self.curation_schema)
        if not self.form_date_key:
            form_date = datetime.fromisoformat(file['modified']).date()
            normalizer.execute(document, form_date=form_date)
        else:
            normalizer.execute(document, form_date_key=self.form_date_key)

        if normalizer.errors:
            log.error(f"Deriver encountered errors: {normalizer.errors}")
            return

        curated_file = normalizer.derived_document
        return normalizer.uncompress_document(curated_file)


    def aggregate_metadata(self,
                           parents: Dict[str, str],
                           target_containers: Optional[List[str]] = None
                           ) -> Dict[Any, Any]:
        """Aggregate metadata from all aggregation containers into
        a SymbolTable, the top key is the container level. Skips if there
        is no corresponding parent.

        Args:
            parents: Parent container_ids, pulled from file_object
        """
        if not target_containers:
            target_containers = self.aggregation_containers

        log.info(f"Target containers for aggregating metadata: {target_containers}")

        table = SymbolTable()
        for hierarchy in target_containers:
            if hierarchy not in table:
                table[hierarchy] = {}

            parts = hierarchy.split('.')
            container_name = parts[0]
            container_key = '.'.join(parts[1:]) if len(parts) > 1 else None

            container_id = parents.get(container_name)
            if not container_id:
                log.warning(f"Parent container '{container_name}' not found")
                continue

            container = SymbolTable(dict(self.context.client.get_container(container_id)))
            value = container.get(container_key) if container_key else container

            if isinstance(value, dict):
                table[hierarchy].update(value)
            else:
                table[hierarchy] = value

            log.info(f"Aggregated metadata from {container_name}, container ID {container_id}")

        return table

    def apply_metadata(self,
                       table: Dict[Any, Any],
                       parents: Dict[str, object],
                       target_containers: Optional[List[str]] = None) -> None:
        """Applies metadata to the specified parent containers. Currently
        assumes will be applied to the .info location.

        Args:
            parents: Parent container_ids, pulled from file_object
        """
        if not target_containers:
            target_containers = self.apply_containers

        log.info(f"Target containers for applying metadata: {target_containers}")

        for container_name in target_containers:
            container_id = parents.get(container_name)
            if not container_id:
                log.warning(f"Parent container {container_name} not found")
                continue

            info = table.get(container_name, {}).get('info')
            if not info:
                log.info(f"No data to apply for {container_name}")
                continue

            container = self.context.client.get_container(container_id)
            container.update(info=info)
            log.info(f"Updated metadata for {container_name}, container ID {container_id}")

    def __load_from_s3(self, curation_schema_uri: str) -> Dict[str, object]:
        """Load curation schema from S3

        Args:
            curation_schema_uri: S3 URI for curation schema
        """
        log.info(f"Loading curation schema from {curation_schema_uri}")

        parts = curation_schema_uri.replace('s3://', '').split('/')
        s3_bucket_name, s3_key = parts[0], '/'.join(parts[1:])
        s3_bucket = S3BucketReader.create_from_environment(s3_bucket_name)

        if not s3_bucket:
            raise GearExecutionError(
                f"Unable to access S3 bucket: {s3_bucket}")
        
        # check if JSON
        if s3_key.endswith('.json'):
            return json.load(s3_bucket.read_data(s3_key))

        # otherwise assume YAML
        return yaml.safe_load(s3_bucket.read_data(s3_key))


def run(*,
        proxy: FlywheelProxy,
        curator: FormCurator,
        file_input: InputFileWrapper):
    """Runs ADD DETAIL process.

    Args:
      proxy: the proxy for the Flywheel instance
    """
    try:
        file = proxy.get_file(file_input.file_id)
    except ApiException as error:
        raise GearExecutionError(
            f'Failed to find the input file: {error}') from error

    log.info(f"Curating {file_input.filename}")
    log.info(f"Parent hierarchy: {file.parents}")

    document = curator.aggregate_metadata(file.parents)
    document['file'] = {'info': file.info}
    curated_data = curator.curate(document, file)

    if proxy.dry_run:
        log.info(f"DRY RUN: Curated data: {json.dumps(curated_data, indent=4)}")
    else:
        log.info(json.dumps(curated_data, indent=4))
        log.info("Curation completed successfully, applying data")
        curator.apply_metadata(curated_data, file.parents)
