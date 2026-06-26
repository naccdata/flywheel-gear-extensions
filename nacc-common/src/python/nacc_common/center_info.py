"""Utilities for getting center information from NACC Data Platform."""

from flywheel import Client


def get_center_id(client: Client, adcid: str) -> str:
    """Look up the center group ID for a given ADCID.

    Args:
        adcid (str): The ADCID of the center.

    Returns:
        Optional[str]: The group ID of the center, or None if not found.
    Raises:
        CenterError if no center data is found or no center with ID exists
    """
    metadata = client.lookup("nacc/metadata")
    if not metadata:
        raise CenterError("Failed to find nacc/metadata project")
    metadata = metadata.reload()
    if "centers" not in metadata.info:
        raise CenterError("No 'centers' key in nacc/metadata")

    if adcid not in metadata.info["centers"]:
        raise CenterError(f"No center with ADCID {adcid} in nacc/metadata")

    return metadata.info["centers"][str(adcid)]["group"]


class CenterError(Exception):
    """Error for accessing center information."""
