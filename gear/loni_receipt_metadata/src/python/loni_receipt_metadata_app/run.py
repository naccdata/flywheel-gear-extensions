"""Entry script for LONI Receipt Metadata."""

import logging
from pathlib import Path
from typing import Optional

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
from loni_receipt_metadata_app.flywheel_io import (
    DryRunAcquisitionTarget,
    DryRunReceiptTagger,
    FlywheelAcquisitionTarget,
    FlywheelFileResolver,
    FlywheelReceiptTagger,
)
from loni_receipt_metadata_app.main import (
    FileResolver,
    ReceiptProcessor,
    ReceiptTagger,
)
from loni_receipt_metadata_app.receipt import ReceiptError, parse_receipt

log = logging.getLogger(__name__)


class LoniReceiptMetadataVisitor(GearExecutionEnvironment):
    """Gear execution environment for LONI Receipt Metadata."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        gear_name: str,
        dry_run: bool = False,
    ) -> None:
        super().__init__(client=client)
        self.__file_input = file_input
        self.__gear_name = gear_name
        self.__dry_run = dry_run

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "LoniReceiptMetadataVisitor":
        """Creates the execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store (unused)
        Returns:
          the execution environment
        """
        client = ContextClient.create(context=context)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "missing expected input, input_file"

        return LoniReceiptMetadataVisitor(
            client=client,
            file_input=file_input,
            gear_name=cls.get_gear_name(context, "loni-receipt-metadata"),
            dry_run=bool(context.config.opts.get("dry_run", False)),
        )

    def run(self, context: GearContext) -> None:
        """Records the receipt metadata on the acquisitions.

        Args:
          context: the gear execution context
        Raises:
          GearExecutionError: if the receipt is not readable or any row failed
        """
        try:
            with Path(self.__file_input.filepath).open(
                encoding="utf-8-sig", newline=""
            ) as stream:
                receipt = parse_receipt(self.__file_input.filename, stream)
        except (ReceiptError, OSError, UnicodeDecodeError) as error:
            log.error("Cannot read receipt: %s", error)
            raise GearExecutionError(f"Cannot read receipt: {error}") from error

        resolver: FileResolver
        tagger: ReceiptTagger
        if self.__dry_run:
            resolver = FlywheelFileResolver(
                self.proxy,
                lambda acquisition: DryRunAcquisitionTarget(acquisition.label),
            )
            tagger = DryRunReceiptTagger(self.__gear_name)
        else:
            resolver = FlywheelFileResolver(self.proxy, FlywheelAcquisitionTarget)
            tagger = FlywheelReceiptTagger(
                client=self.client.client,
                file_id=self.__file_input.file_id,
                gear_name=self.__gear_name,
            )

        result = ReceiptProcessor(receipt, resolver).run()
        if not result.passed:
            log.error(
                "%d row(s) of receipt %s failed", result.failed_rows, receipt.name
            )

        tagger.mark(result.passed)

        if not result.passed:
            raise GearExecutionError(
                f"{result.failed_rows} row(s) of receipt {receipt.name} failed"
            )


def main():
    """Main method for LONI Receipt Metadata."""
    GearEngine().run(gear_type=LoniReceiptMetadataVisitor)


if __name__ == "__main__":
    main()
