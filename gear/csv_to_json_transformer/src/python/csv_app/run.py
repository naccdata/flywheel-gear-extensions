"""Entrypoint script for the csv-to-json transformer app."""

import logging
import sys
from typing import Dict, Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from outputs.errors import ListErrorWriter
from pydantic import ValidationError
from transform.transformer import FieldTransformations, TransformerFactory

from csv_app.main import run
from csv_app.uploader import LabelTemplate, UploadTemplateList

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class CsvToJsonVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the csv-to-json-transformer app."""

    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper,
                 transform_input: Optional[InputFileWrapper],
                 hierarchy_labels: Dict[str, str]) -> None:
        self.__client = client
        self.__file_input = file_input
        self.__hierarchy_labels = hierarchy_labels
        self.__transform_input = transform_input

    @classmethod
    def create(
            cls, context: GearToolkitContext,
            parameter_store: Optional[ParameterStore]) -> 'CsvToJsonVisitor':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store

        Returns:
          the execution environment

        Raises:
          GearExecutionError if any expected inputs are missing
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        assert file_input, "create raises exception if missing expected input"

        transform_input = InputFileWrapper.create(input_name='transform_file',
                                                  context=context)

        hierarchy_labels = context.config.get('hierarchy_labels')
        if not hierarchy_labels:
            raise GearExecutionError("Expecting non-empty label templates")

        return CsvToJsonVisitor(client=client,
                                file_input=file_input,
                                transform_input=transform_input,
                                hierarchy_labels=hierarchy_labels)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the CSV to JSON Transformer app.

        Args:
          context: the gear execution context
        """

        proxy = self.__client.get_proxy()
        file_id = self.__file_input.file_id
        try:
            file = proxy.get_file(file_id)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        project = proxy.get_project_by_id(file.parents.project)
        if not project:
            raise GearExecutionError(
                f'Failed to find the project with ID {file.parents.project}')

        template_map = self.__load_template(self.__hierarchy_labels)

        with open(self.__file_input.filepath, mode='r',
                  encoding='utf-8') as csv_file:
            error_writer = ListErrorWriter(container_id=file_id,
                                           fw_path=proxy.get_lookup_path(file))
            success = run(input_file=csv_file,
                          destination=ProjectAdaptor(project=project,
                                                     proxy=proxy),
                          transformer_factory=self.__build_transformer(
                              self.__transform_input),
                          template_map=template_map,
                          error_writer=error_writer)

            context.metadata.add_qc_result(self.__file_input.file_input,
                                           name='validation',
                                           state='PASS' if success else 'FAIL',
                                           data=error_writer.errors())

            context.metadata.add_file_tags(self.__file_input.file_input,
                                           tags=context.manifest.get(
                                               'name',
                                               'csv-to-json-transformer'))

    def __build_transformer(
            self, transformer_input: Optional[InputFileWrapper]
    ) -> TransformerFactory:
        """Loads the transformation file and creates a transformer factory.

        If the input is None, returns a factory for empty transformations.
        Otherwise, loads the file as a FileTransformations object and creates
        a factory using those.

        Args:
          transformer_input: the input file wrapper
        Returns:
          the TransformerFactory for the input
        """
        if not transformer_input:
            return TransformerFactory(FieldTransformations())

        with open(transformer_input.filepath, mode='r',
                  encoding='utf-8') as json_file:
            try:
                return TransformerFactory(
                    FieldTransformations.model_validate_json(json_file.read()))
            except ValidationError as error:
                raise GearExecutionError('Error reading transformation file'
                                         f'{error}') from error

    def __load_template(
            self, template_list: Dict[str, str]) -> Dict[str, LabelTemplate]:
        """Creates the list of label templates from the input objects.

        Args:
          template_list: dictionary with label template details
        Returns:
          Dictionary from label types to label template object
        Raises:
          GearExecutionError if the model validation fails
        """
        try:
            upload_templates = UploadTemplateList.model_validate(template_list)
        except ValidationError as error:
            raise GearExecutionError('Error reading label templates: '
                                     f'{error}') from error

        return {
            template_info.type: LabelTemplate(template_info)
            for template_info in upload_templates
        }


def main():
    """Gear main method to transform CSV where row is participant data to set
    of JSON files, one per participant."""

    GearEngine.create_with_parameter_store().run(gear_type=CsvToJsonVisitor)


if __name__ == "__main__":
    main()
