"""Parser module to parse gear config.json."""

from pathlib import Path
from typing import Tuple

from flywheel_gear_toolkit import GearToolkitContext


# This function mainly parses gear_context's config.json file and returns relevant
# inputs and options.
def parse_config(
    gear_context: GearToolkitContext,
) -> Tuple[str, Path]:
    """[Summary].

    Returns:
        [type]: [description]
    """
    dry_run = gear_context.config.get("dry_run")
    input_csv_path = gear_context.get_input_path("input_file")

    return dry_run, input_csv_path
