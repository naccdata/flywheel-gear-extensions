"""
Utility for tagging files in Flywheel using the Gear Toolkit.
"""
from typing import Any, Dict, Optional

from loni_csv_metadata_processor_app.data_model.processor_output import \
    ProcessorOutput


class FileTagger:
    """
    Utility class for tagging Flywheel files with metadata via the Gear Toolkit.
    """

    def __init__(self, gear_context: Any = None):
        """
        Initialize the file tagger with the gear toolkit context.

        Args:
            gear_context: The Gear Toolkit context for interacting with Flywheel.
        """
        self.gear_context = gear_context

    def add_tag_to_metadata(self, tag_name: str, output: ProcessorOutput) -> None:
        """
        Add a tag to the metadata.json file.

        Args:
            tag_name: Name of the tag to add (typically processor name).
            output: Processor output containing status and value to tag with.
        """
        # This is a placeholder implementation
        # In a real implementation, this would use the gear toolkit to add metadata
        # to the .metadata.json file for the appropriate container

        print(f"Adding tag {tag_name} with value={output.value}")
        # Implementation will use gear_context to add metadata
