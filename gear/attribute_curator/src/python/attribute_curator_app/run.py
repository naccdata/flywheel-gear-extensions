"""Entry script for Attribute Curator."""

import logging
from typing import List, Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from curator.scheduling_models import FileModel
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from fw_gear import GearContext
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
from rxnav.rxnav_connection import load_rxclass_concepts_from_file
from utils.utils import parse_string_to_list

from .form_curator import FormCurator
from .main import run

log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        project: ProjectAdaptor,
        filename_patterns: List[str],
        include_subjects: List[str],
        exclude_subjects: List[str],
        curation_tag: str,
        force_curate: bool = False,
        rxclass_concepts_file: Optional[InputFileWrapper] = None,
        max_num_workers: int = 4,
        ignore_qc: bool = False,
    ):
        super().__init__(client=client)
        self.__project = project
        self.__filename_patterns = filename_patterns
        self.__include_subjects = include_subjects
        self.__exclude_subjects = exclude_subjects
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate
        self.__rxclass_concepts_file = rxclass_concepts_file
        self.__max_num_workers = max_num_workers
        self.__ignore_qc = ignore_qc

    @classmethod
    def create(
        cls,
        context: GearContext,
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

        options = context.config.opts
        rxclass_concepts_file = InputFileWrapper.create(
            input_name="rxclass_concepts_file", context=context
        )

        filename_patterns = parse_string_to_list(
            options.get(
                "filename_patterns", ".*\\.json,.*\\.dicom\\,.*\\.zip,.*\\.nii\\.gz"
            ),
            to_lower=False,
        )

        include_subjects = parse_string_to_list(
            options.get("include_subjects", ""), to_lower=False
        )
        exclude_subjects = parse_string_to_list(
            options.get("exclude_subjects", ""), to_lower=False
        )

        if include_subjects and exclude_subjects:
            raise GearExecutionError("Cannot define both include and exclude lists")

        fw_project = get_project_from_destination(context=context, proxy=proxy)
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        if options.get("debug", False):
            logging.basicConfig(level=logging.DEBUG)

        return AttributeCuratorVisitor(
            client=client,
            project=project,
            filename_patterns=filename_patterns,
            include_subjects=include_subjects,
            exclude_subjects=exclude_subjects,
            curation_tag=options.get("curation_tag", "attribute-curator"),
            force_curate=options.get("force_curate", False),
            rxclass_concepts_file=rxclass_concepts_file,
            max_num_workers=options.get("max_num_workers", 4),
            ignore_qc=options.get("ignore_qc", False),
        )

    def run(self, context: GearContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group, self.__project.label)

        rxclass_concepts = None
        if self.__rxclass_concepts_file:
            with open(
                self.__rxclass_concepts_file.filepath, mode="r", encoding="utf-8-sig"
            ) as fh:
                rxclass_concepts = load_rxclass_concepts_from_file(fh)

        dataview = FileModel.create_dataview(self.__filename_patterns)
        curator = FormCurator(
            dataview=dataview,
            curation_tag=self.__curation_tag,
            force_curate=self.__force_curate,
            rxclass_concepts=rxclass_concepts,
            ignore_qc=self.__ignore_qc,
        )

        try:
            scheduler = ProjectCurationScheduler(
                project=self.__project,
                include_subjects=self.__include_subjects,
                exclude_subjects=self.__exclude_subjects,
            )
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(
            context=context,
            curator=curator,
            scheduler=scheduler,
            max_num_workers=self.__max_num_workers,
        )


def main():
    """Main method for Attribute Curator."""
    GearEngine().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
