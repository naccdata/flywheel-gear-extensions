"""Entry point for the PHI Image Removal gear.

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

from phi_image_removal_app.main import run

log = logging.getLogger(__name__)


class PHIImageRemovalVisitor(GearExecutionEnvironment):
    """Visitor for the PHI Image Removal gear."""

    def __init__(
        self,
        client: ClientWrapper,
        *,
        file_input: InputFileWrapper,
        gear_name: str,
        gear_version: str | None,
        confirmed_tag: str,
        tombstone_tag: str,
    ):
        """Initialize the visitor with the gear's configuration.

        Args:
            client: Flywheel SDK client wrapper
            file_input: the input image file wrapper
            gear_name: name of this gear, recorded in the tombstone
            gear_version: version of this gear, recorded in the tombstone
            confirmed_tag: tag that marks a file as confirmed PHI
            tombstone_tag: tag added to the tombstone file
        """
        super().__init__(client=client)
        self.__file_input = file_input
        self.__gear_name = gear_name
        self.__gear_version = gear_version
        self.__confirmed_tag = confirmed_tag
        self.__tombstone_tag = tombstone_tag

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: ParameterStore | None = None,
    ) -> "PHIImageRemovalVisitor":
        """Creates a PHI Image Removal execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store.
        Returns:
            the execution environment
        Raises:
            GearExecutionError if the expected input file is missing
        """
        client = ContextClient.create(context=context)

        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        if not file_input:
            raise GearExecutionError("Missing expected input, input_file")

        opts = context.config.opts

        return PHIImageRemovalVisitor(
            client=client,
            file_input=file_input,
            gear_name=cls.get_gear_name(context, "phi-image-removal"),
            gear_version=context.manifest.version,
            confirmed_tag=opts.get("confirmed_tag", "PHI-Confirmed"),
            tombstone_tag=opts.get("tombstone_tag", "PHI-Tombstone"),
        )

    def run(self, context: GearContext) -> None:
        """Runs the PHI Image Removal app."""
        try:
            file = self.proxy.get_file(self.__file_input.file_id)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        acquisition_id = file.parents.acquisition
        if not acquisition_id:
            raise GearExecutionError(
                f"Input file {file.name} is not contained in an acquisition"
            )
        acquisition = self.proxy.get_acquisition(acquisition_id)

        success = run(
            file=file,
            acquisition=acquisition,
            gear_name=self.__gear_name,
            gear_version=self.__gear_version,
            confirmed_tag=self.__confirmed_tag,
            tombstone_tag=self.__tombstone_tag,
            dry_run=self.proxy.dry_run,
        )

        if not success:
            raise GearExecutionError(
                "PHI Image Removal completed with errors; see logs for details"
            )


def main():
    """Main method for PHI Image Removal."""

    GearEngine().run(gear_type=PHIImageRemovalVisitor)


if __name__ == "__main__":
    main()
