"""Entrypoint script for the csv-subject splitter app."""

import json
import logging
import sys
from json.decoder import JSONDecodeError
from typing import Dict, Optional, Set

from configs.ingest_configs import UploadTemplateInfo
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.hierarchy_creator import HierarchyCreationClient
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterError, ParameterStore
from outputs.error_writer import ListErrorWriter
from pydantic import ValidationError
from uploads.provenance import FileProvenance
from uploads.uploader import JSONUploader
from utils.utils import parse_string_to_list

from csv_app.main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class CsvToJsonVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the csv-subject-splitter app."""

    def __init__(
        self,
        client: ClientWrapper,
        device_key: str,
        file_input: InputFileWrapper,
        hierarchy_labels: Dict[str, str],
        preserve_case: bool,
        req_fields: Set[str],
    ) -> None:
        self.__client = client
        self.__device_key = device_key
        self.__file_input = file_input
        self.__hierarchy_labels = hierarchy_labels
        self.__preserve_case = preserve_case
        self.__req_fields = req_fields

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore]
    ) -> "CsvToJsonVisitor":
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store

        Returns:
          the execution environment

        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)

        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing expected input"

        options = context.config.opts

        device_key_prefix = options.get("device_key_path_prefix")
        if not device_key_prefix:
            raise GearExecutionError("Device key path prefix required")

        assert parameter_store, "Parameter store expected"
        try:
            device_key = parameter_store.get_api_key(path_prefix=device_key_prefix)
        except ParameterError as error:
            raise GearExecutionError(error) from error

        hierarchy_labels = options.get("hierarchy_labels")
        if not hierarchy_labels:
            raise GearExecutionError("Expecting non-empty label templates")

        try:
            hierarchy_labels = json.loads(hierarchy_labels)
        except (JSONDecodeError, TypeError, ValueError) as error:
            raise GearExecutionError(f"Failed to load JSON string: {error}") from error

        preserve_case = options.get("preserve_case", False)
        req_fields = set(parse_string_to_list(options.get("required_fields", "")))

        return CsvToJsonVisitor(
            client=client,
            device_key=device_key,
            file_input=file_input,
            hierarchy_labels=hierarchy_labels,
            preserve_case=preserve_case,
            req_fields=req_fields,
        )

    def run(self, context: GearContext) -> None:
        """Runs the CSV to JSON Transformer app.

        Args:
          context: the gear execution context
        """

        proxy = self.__client.get_proxy()
        file_id = self.__file_input.file_id
        hierarchy_client = HierarchyCreationClient(self.__device_key)
        try:
            file = proxy.get_file(file_id)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        project = self.__file_input.get_parent_project(proxy, file=file)
        destination = ProjectAdaptor(project=project, proxy=proxy)
        template_map = self.__load_template(self.__hierarchy_labels)

        provenance = FileProvenance.create_from_parent(proxy, file)
        uploader = JSONUploader(
            proxy=proxy,
            hierarchy_client=hierarchy_client,
            project=destination,
            template_map=template_map,
            environment={"filename": self.__file_input.basename},
        )

        with open(
            self.__file_input.filepath, mode="r", encoding="utf-8-sig"
        ) as csv_file:
            error_writer = ListErrorWriter(
                container_id=file_id, fw_path=proxy.get_lookup_path(file)
            )

            success = run(
                provenance=provenance,
                uploader=uploader,
                input_file=csv_file,
                destination=destination,
                error_writer=error_writer,
                preserve_case=self.__preserve_case,
                req_fields=self.__req_fields,
            )

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors().model_dump(by_alias=True),
            )

            manifest_name = context.manifest.name
            context.metadata.add_file_tags(
                self.__file_input.file_input,
                tags=manifest_name if manifest_name else "csv-subject-splitter",
            )

    def __load_template(self, template_list: Dict[str, str]) -> UploadTemplateInfo:
        """Creates the list of label templates from the input objects.

        Args:
          template_list: dictionary with label template details
        Returns:
          Dictionary from label types to label template object
        Raises:
          GearExecutionError if the model validation fails
        """
        try:
            return UploadTemplateInfo.model_validate(template_list)
        except ValidationError as error:
            raise GearExecutionError(
                f"Error reading label templates: {error}"
            ) from error


def main():
    """Gear main method to transform CSV where row is participant data to set
    of JSON files, one per participant."""

    GearEngine.create_with_parameter_store().run(gear_type=CsvToJsonVisitor)


if __name__ == "__main__":
    main()
