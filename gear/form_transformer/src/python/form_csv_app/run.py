"""Entry script for Form CSV to JSON Transformer."""

import logging
from typing import Optional

from datastore.forms_store import FormsStore
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from flywheel_gear_toolkit.context.context import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from outputs.errors import ListErrorWriter
from preprocess.preprocessor import FormPreprocessor, FormProjectConfigs
from pydantic import ValidationError
from transform.transformer import FieldTransformations, TransformerFactory
from utils.utils import parse_string_to_list

from form_csv_app.main import run

log = logging.getLogger(__name__)


class FormCSVtoJSONTransformer(GearExecutionEnvironment):
    """Visitor for the templating gear."""

    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper,
                 config_input: InputFileWrapper,
                 transform_input: Optional[InputFileWrapper]) -> None:
        self.__client = client
        self.__file_input = file_input
        self.__config_input = config_input
        self.__transform_input = transform_input

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'FormCSVtoJSONTransformer':
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
        assert file_input, "missing expected input, input_file"

        form_configs_input = InputFileWrapper.create(
            input_name='form_configs_file', context=context)
        assert form_configs_input, "missing expected input, form_configs_file"

        transform_input = InputFileWrapper.create(input_name='transform_file',
                                                  context=context)

        return FormCSVtoJSONTransformer(client=client,
                                        file_input=file_input,
                                        config_input=form_configs_input,
                                        transform_input=transform_input)

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

        gear_name = context.manifest.get('name', 'form-transformer')

        downstream_gears = parse_string_to_list(
            context.config.get('downstream_gears', None))

        prj_adaptor = ProjectAdaptor(project=project, proxy=proxy)

        error_writer = ListErrorWriter(container_id=file_id,
                                       fw_path=proxy.get_lookup_path(file))

        preprocessor = self.__get_preprocessor(
            form_config_input=self.__config_input,
            ingest_project=prj_adaptor,
            error_writer=error_writer)

        with open(self.__file_input.filepath, mode='r',
                  encoding='utf-8') as csv_file:
            success = run(input_file=csv_file,
                          destination=prj_adaptor,
                          transformer_factory=self.__build_transformer(
                              self.__transform_input),
                          preprocessor=preprocessor,
                          error_writer=error_writer,
                          gear_name=gear_name,
                          downstream_gears=downstream_gears)

            context.metadata.add_qc_result(self.__file_input.file_input,
                                           name='validation',
                                           state='PASS' if success else 'FAIL',
                                           data=error_writer.errors())

            context.metadata.add_file_tags(self.__file_input.file_input,
                                           tags=gear_name)

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
                raise GearExecutionError(
                    'Error reading transformation file'
                    f'{transformer_input.filename}: {error}') from error

    def __get_preprocessor(self, form_config_input: InputFileWrapper,
                           ingest_project: ProjectAdaptor,
                           error_writer: ListErrorWriter) -> FormPreprocessor:
        """Reads the forms config file and initialize the preprocessor.

        Args:
          form_config_input: the input file wrapper for form configs file

        Returns:
          the FormPreprocessor with given configs
        """

        with open(form_config_input.filepath, mode='r',
                  encoding='utf-8') as configs_file:
            try:
                form_configs = FormProjectConfigs.model_validate_json(
                    configs_file.read())
            except ValidationError as error:
                raise GearExecutionError(
                    'Error reading form configurations file'
                    f'{form_config_input.filename}: {error}') from error

            legacy_label = (form_configs.legacy_project_label
                            if form_configs.legacy_project_label else
                            DefaultValues.LEGACY_PRJ_LABEL)
            try:
                legacy_project = ProjectAdaptor.create(
                    proxy=ingest_project.proxy,
                    group_id=ingest_project.group,
                    project_label=legacy_label)
            except ProjectError as error:
                raise GearExecutionError(
                    f'Failed to retrieve legacy project: {error}') from error

            forms_store = FormsStore(ingest_project=ingest_project,
                                     legacy_project=legacy_project)

            return FormPreprocessor(primary_key=form_configs.primary_key,
                                    forms_store=forms_store,
                                    module_info=form_configs.module_configs,
                                    error_writer=error_writer)


def main():
    """Main method for Form CSV to JSON Transformer."""

    GearEngine.create_with_parameter_store().run(
        gear_type=FormCSVtoJSONTransformer)


if __name__ == "__main__":
    main()
