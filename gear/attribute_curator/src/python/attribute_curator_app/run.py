"""Entry script for Attribute Curator."""

import json
import logging
from json.decoder import JSONDecodeError
from typing import List, Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    get_project_from_destination,
)
from inputs.parameter_store import ParameterStore
from s3.s3_client import S3BucketReader
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
        rxclass_concepts_s3_uri: Optional[str] = None,
        max_num_workers: int = 4,
        ignore_qc: bool = False,
    ):
        super().__init__(client=client)
        self.__project = project
        self.__filename_patterns = filename_patterns
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate
        self.__rxclass_concepts_s3_uri = rxclass_concepts_s3_uri
        self.__max_num_workers = max_num_workers
        self.__ignore_qc = ignore_qc

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

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        proxy = client.get_proxy()

        filename_patterns = parse_string_to_list(
            context.config.get(
                "filename_patterns", ".*\\.json,.*\\.dicom\\,.*\\.zip,.*\\.nii\\.gz"
            ),
            to_lower=False,
        )
        curation_tag = context.config.get("curation_tag", "attribute-curator")
        force_curate = context.config.get("force_curate", False)
        max_num_workers = context.config.get("max_num_workers", 4)
        rxclass_concepts_s3_uri = context.config.get("rxclass_concepts_s3_uri", "")
        ignore_qc = context.config.get("ignore_qc", False)

        fw_project = get_project_from_destination(context=context, proxy=proxy)
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        if context.config.get("debug", False):
            logging.basicConfig(level=logging.DEBUG)

        return AttributeCuratorVisitor(
            client=client,
            project=project,
            filename_patterns=filename_patterns,
            curation_tag=curation_tag,
            force_curate=force_curate,
            rxclass_concepts_s3_uri=rxclass_concepts_s3_uri,
            max_num_workers=max_num_workers,
            ignore_qc=ignore_qc,
        )

    def run(self, context: GearToolkitContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group, self.__project.label)

        rxclass_concepts = None
        if self.__rxclass_concepts_s3_uri:
            log.info(f"Loading RxClass concepts from {self.__rxclass_concepts_s3_uri}")
            s3_bucket, s3_file = S3BucketReader.parse_bucket_and_key(
                self.__rxclass_concepts_s3_uri
            )
            s3_client = S3BucketReader.create_from_environment(s3_bucket)
            if not s3_client or not s3_file:
                raise GearExecutionError(
                    "Invalid S3 URI for RxNorm concepts: "
                    + f"{self.__rxclass_concepts_s3_uri}"
                )

            try:
                rxclass_concepts = json.load(s3_client.read_data(s3_file))
            except (JSONDecodeError, TypeError) as error:
                raise GearExecutionError(
                    f"Failed to read {self.__rxclass_concepts_s3_uri}: {error}"
                ) from error

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                filename_patterns=self.__filename_patterns,
            )
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(
            context=context,
            scheduler=scheduler,
            curation_tag=self.__curation_tag,
            force_curate=self.__force_curate,
            max_num_workers=self.__max_num_workers,
            rxclass_concepts=rxclass_concepts,
            ignore_qc=self.__ignore_qc,
        )


def main():
    """Main method for Attribute Curator."""
    GearEngine.create_with_parameter_store().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
