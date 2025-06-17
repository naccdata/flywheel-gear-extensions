"""Entry script for UDS Curator."""

import logging
from typing import Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
    get_project_from_destination,
)
from inputs.parameter_store import ParameterStore
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver

from attribute_curator_app.main import run

log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(self,
                 client: ClientWrapper,
                 project: ProjectAdaptor,
                 filename_pattern: str,
                 curation_tag: str,
                 force_curate: bool = False,
                 blacklist_file: Optional[InputFileWrapper] = None):
        super().__init__(client=client)
        self.__project = project
        self.__filename_pattern = filename_pattern
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate
        self.__blacklist_file = blacklist_file

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'AttributeCuratorVisitor':
        """Creates a UDS Curator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)
        proxy = client.get_proxy()

        blacklist_file = InputFileWrapper.create(input_name='blacklist_file',
                                                 context=context)

        filename_pattern = context.config.get('filename_pattern', "*.json")
        curation_tag = context.config.get('curation_tag', "attribute-curator")
        force_curate = context.config.get('force_curate', False)

        #fw_project = get_project_from_destination(context=context, proxy=proxy)
        fw_project = proxy.get_project_by_id("68261ccff461d81205581549")
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        return AttributeCuratorVisitor(client=client,
                                       project=project,
                                       filename_pattern=filename_pattern,
                                       curation_tag=curation_tag,
                                       force_curate=force_curate,
                                       blacklist_file=blacklist_file)

    def run(self, context: GearToolkitContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group,
                 self.__project.label)

        deriver = AttributeDeriver()

        blacklist = None
        if self.__blacklist_file:
            with open(self.__blacklist_file.filepath, mode='r') as fh:
                blacklist = [x.strip() for x in fh.readlines()]

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                filename_pattern=self.__filename_pattern,
                blacklist=blacklist)
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(context=context,
            deriver=deriver,
            scheduler=scheduler,
            curation_tag=self.__curation_tag,
            force_curate=self.__force_curate)


def main():
    """Main method for Attribute Curator."""
    GearEngine().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
