#!/usr/bin/env python
"""The run script."""

import logging
import sys

from flywheel_gear_toolkit import GearToolkitContext

# This design with a separate main and parser module
# allows the gear to be publishable and the main interfaces
# to it can then be imported in another project which enables
# chaining multiple gears together.
from loni_csv_metadata_processor_app.main import run
from loni_csv_metadata_processor_app.parser import parse_config
from loni_csv_metadata_processor_app.utils.results_processor import process_results

# The run.py should be as minimal as possible.
# The gear is split up into 2 main components. The run.py file which is executed
# when the container runs. The run.py file then imports the rest of the gear as a
# module.


log = logging.getLogger(__name__)


def main(context: GearToolkitContext) -> None:  # pragma: no cover
    """Parses gear config and run."""
    # Call parse_config to extract the args, kwargs from the context
    # (e.g. config.json).
    dry_run, csv_path = parse_config(context)

    # Pass the args, kwargs to fw_gear_skeleton.main.run function to execute
    # the main functionality of the gear.
    results = run(input_path=csv_path)
    
    # Process results and add tags to the output file
    process_results(context, results)

    # Exit with success code
    sys.exit(0)


# Only execute if file is run as main, not when imported by another module
if __name__ == "__main__":  # pragma: no cover
    # Get access to gear config, inputs, and sdk client if enabled.
    with GearToolkitContext() as gear_context:
        # Initialize logging, set logging level based on `debug` configuration
        # key in gear config.
        gear_context.init_logging()

        # Pass the gear context into main function defined above.
        main(gear_context)
