"""Entry script for UDS Curator."""

import importlib.metadata
import logging
from typing import List, Optional

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

from utils.utils import parse_string_to_list

from attribute_curator_app.main import run

log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        project: ProjectAdaptor,
        filename_patterns: List[str],
        curation_tag: str,
        force_curate: bool = False,
        blacklist_file: Optional[InputFileWrapper] = None,
        max_num_workers: int = 4,
    ):
        super().__init__(client=client)
        self.__project = project
        self.__filename_patterns = filename_patterns
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate
        self.__blacklist_file = blacklist_file
        self.__max_num_workers = max_num_workers

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "AttributeCuratorVisitor":
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

        blacklist_file = InputFileWrapper.create(
            input_name="blacklist_file", context=context
        )

        filename_patterns = parse_string_to_list(
            context.config.get("filename_patterns",
                               ".*\\.json,.*\\.dicom\\.zip,.*\\.nii\\.gz"),
            to_lower=False
        )
        curation_tag = context.config.get("curation_tag", "attribute-curator")
        force_curate = context.config.get("force_curate", False)
        max_num_workers = context.config.get("max_num_workers", 4)

        #fw_project = get_project_from_destination(context=context, proxy=proxy)
        fw_project = proxy.get_project_by_id("68261ccff461d81205581549")
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        if context.config.get("debug", False):
            logging.basicConfig(level=logging.DEBUG)

        return AttributeCuratorVisitor(
            client=client,
            project=project,
            filename_patterns=filename_patterns,
            curation_tag=curation_tag,
            force_curate=force_curate,
            blacklist_file=blacklist_file,
            max_num_workers=max_num_workers,
        )

    def run(self, context: GearToolkitContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group, self.__project.label)

        blacklist = None
        if self.__blacklist_file:
            with open(self.__blacklist_file.filepath, mode="r") as fh:
                blacklist = [x.strip() for x in fh.readlines()]

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                filename_patterns=self.__filename_patterns,
                blacklist=blacklist,
            )
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(
            context=context,
            scheduler=scheduler,
            curation_tag=self.__curation_tag,
            force_curate=self.__force_curate,
            max_num_workers=self.__max_num_workers,
        )


def main():
    """Main method for Attribute Curator."""
    GearEngine().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
