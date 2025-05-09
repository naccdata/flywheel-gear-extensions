"""Entry script for NCRAD Biomarker Mapping."""
import logging
import re
from io import StringIO
from typing import Optional

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

from ncrad_biomarker_mapping_app.main import run

log = logging.getLogger(__name__)


class NCRADBiomarkerMappingVisitor(GearExecutionEnvironment):
    """Visitor for the NCRAD Biomarker Mapping gear."""

    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper,
                 target_project: str):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__target_project = target_project

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'NCRADBiomarkerMappingVisitor':
        """Creates a NCRAD Biomarker Mapping execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        target_project = context.config.get('target_project', None)

        if not file_input:
            raise GearExecutionError("Missing required input file")

        return NCRADBiomarkerMappingVisitor(client=client,
                                            file_input=file_input,
                                            target_project=target_project)

    def run(self, context: GearToolkitContext) -> None:
        """Run the NCRAD Biomarker Mapping gear."""
        file_id = self.__file_input.file_id
        try:
            file = self.proxy.get_file(file_id)
            fw_path = self.proxy.get_lookup_path(file)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        error_writer = ListErrorWriter(container_id=file_id, fw_path=fw_path)
        fw_project = self.__file_input.get_parent_project(self.proxy,
                                                          file=file)
        parent_project = ProjectAdaptor(project=fw_project, proxy=self.proxy)

        # find corresponding QC file based on input filename
        # assumes its named the same but with "Control Data" instead of "Biomarker"
        # but need to remove the ADCID identifier on the front
        qc_filename = self.__file_input.filename.replace(
            "Biomarker", "Control Data")
        qc_filename = '_'.join(qc_filename.split('_')[1:])

        qc_files = parent_project.find_files(re.escape(qc_filename))
        if len(qc_files) != 1:
            raise GearExecutionError(
                f"Could not find exactly one QC file with the name {qc_filename} "
                + f"in project {parent_project.group}/{parent_project.label}")

        with open(self.__file_input.filepath, mode='r',
                  encoding='utf-8-sig') as fh:
            qc_contents = str(parent_project.read_file(qc_files[0].name),
                              encoding='utf-8')
            success = run(proxy=self.proxy,
                          biomarker_file=fh,
                          qc_file=StringIO(qc_contents),
                          biomarker_filename=self.__file_input.filename,
                          qc_filename=qc_filename,
                          target_project=self.__target_project,
                          error_writer=error_writer)

            context.metadata.add_qc_result(self.__file_input.file_input,
                                           name='validation',
                                           state='PASS' if success else 'FAIL',
                                           data=error_writer.errors())
            context.metadata.add_file_tags(self.__file_input.file_input,
                                           tags=context.manifest.get(
                                               'name',
                                               'ncrad-biomarker-mapping'))


def main():
    """Main method for NCRAD Biomarker Mapping."""

    GearEngine.create_with_parameter_store().run(
        gear_type=NCRADBiomarkerMappingVisitor)


if __name__ == "__main__":
    main()
