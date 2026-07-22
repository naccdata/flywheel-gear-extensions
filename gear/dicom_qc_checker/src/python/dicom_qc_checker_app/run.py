"""Entry point for the dicom-qc-checker gear.

Builds the gear execution visitor from the gear context and config, and
defines the main function the container runs.
"""

import logging

from flywheel.rest import ApiException
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from nacc_common.error_models import GearTags

from dicom_qc_checker_app.main import run

log = logging.getLogger(__name__)

GEAR_NAME = "dicom-qc-checker"


class DicomQCCheckerVisitor(GearExecutionEnvironment):
    """Gear execution environment for the dicom-qc-checker gear."""

    def __init__(
        self,
        client: ClientWrapper,
        *,
        file_input: InputFileWrapper,
    ) -> None:
        super().__init__(client=client)
        self.__file_input = file_input

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: ParameterStore | None = None,
    ) -> "DicomQCCheckerVisitor":
        """Creates a DicomQCChecker execution visitor."""
        client = ContextClient.create(context=context)

        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        if not file_input:
            raise GearExecutionError("Missing expected input, input_file")

        return DicomQCCheckerVisitor(
            client=client,
            file_input=file_input,
        )

    def run(self, context: GearContext) -> None:
        """Runs the dicom-qc-checker gear."""
        try:
            file = self.proxy.get_file(self.__file_input.file_id)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        status = run(file=file)

        if status is None:
            return

        gear_tags = GearTags(gear_name=GEAR_NAME)
        updated_tags = gear_tags.update_tags(tags=file.tags, status=status)
        context.metadata.update_file_metadata(
            self.__file_input.file_input,
            tags=updated_tags,
            container_type=context.config.destination["type"],
        )


def main():
    """Main method for dicom-qc-checker."""
    GearEngine().run(gear_type=DicomQCCheckerVisitor)


if __name__ == "__main__":
    main()
