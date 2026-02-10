"""Maps ADCID to projects."""

import logging
from typing import Any, Dict, Iterable, List, Optional

from centers.center_group import CenterError, CenterGroup
from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError

log = logging.getLogger(__name__)


def build_project_map(
    *,
    proxy: FlywheelProxy,
    destination_label: str,
    center_filter: Optional[List[str]] = None,
) -> Dict[str, ProjectAdaptor]:
    """Builds a map from adcid to the project of center group with the given
    label.

    Args:
      proxy: the flywheel instance proxy
      destination_label: the project of center to map to
      center_filter: Optional list of ADCIDs to filter on for a mapping subset
    Returns:
      dictionary mapping from adcid to group
    """
    center_map = NACCGroup.create(proxy=proxy).get_center_map(
        center_filter=center_filter
    )

    if not center_map:
        log.warning("No centers found to build project map")
        return {}

    project_map = {}
    try:
        for adcid, center_info in center_map.centers.items():
            group = CenterGroup.create_from_center(center=center_info, proxy=proxy)
            project = group.find_project(destination_label)
            if not project:
                continue
            project_map[f"adcid-{adcid}"] = project

    except CenterError as error:
        log.error("failed to create center from group: %s", error.message)
        return {}

    if not project_map:
        log.warning("No projects found while building project map")

    return project_map


def generate_project_map(
    *,
    proxy: FlywheelProxy,
    centers: Iterable[str],
    target_project: Optional[str] = None,
    staging_project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates the project map.

    Args:
        proxy: the proxy for the Flywheel instance
        centers: The list of centers to map
        target_project: The FW target project name to write results to for
                        each ADCID
        staging_project_id: Project ID to stage results to; will override
                            target_project if specified
    Returns:
        Evaluated project mapping
    """
    if staging_project_id:
        # if writing results to a staging project, manually build a project map
        # that maps all to the specified project ID
        project = proxy.get_project_by_id(staging_project_id)
        if not project:
            raise GearExecutionError(
                f"Cannot find staging project with ID {staging_project_id}, "
                + "possibly a permissions issue?"
            )

        return {f"adcid-{adcid}": project for adcid in centers}

    # else build project map from ADCID to corresponding
    # FW project for upload, and filter as needed
    assert target_project, "target_project required if no staging_project_id provided"
    return build_project_map(
        proxy=proxy, destination_label=target_project, center_filter=list(centers)
    )
