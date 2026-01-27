"""Functions to support gathering Flywheel objects based on the gear context
config object."""

from typing import Optional

from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor, ProjectAdaptor
from fw_gear import GearContext

from inputs.context_parser import get_config


def get_group(
    *,
    context: GearContext,
    proxy: FlywheelProxy,
    key: str,
    default: Optional[str],
) -> GroupAdaptor:
    """Returns the group determined by the context config values for the group
    key.

    Uses the group default as the group name if the key is not in the context.

    Note: for the admin group use NACCGroup.create() instead

    Args:
      context: the gear context
      proxy: the proxy for the flywheel instance
      key: the key for group name
      default: the default group name
    Returns:
      the group identified by the group name in the config
    Raises:
      ConfigurationError if the group is not found
    """
    group_name = get_config(gear_context=context, key=key, default=default)
    group = proxy.find_group(group_name)
    if not group:
        raise ConfigurationError(f"No group {group_name} found")

    return group


def get_project(
    *, context: GearContext, group: GroupAdaptor, project_key: str
) -> ProjectAdaptor:
    """Returns the project determined by the context config values for the
    group and project keys.

    Uses the group default as the group name if the key is not found.

    Args:
      gear_context: the gear context
      proxy: the proxy for the flywheel instance
      group_key: the config key for the group name
      group_default: the default group name
      project_key: the config key for the project name
    Returns:
      the project identified by the group and project name
    Raises:
      ConfigurationError if the group or project are not found
      ConfigParseError if the keys have no value in the context
    """
    project_name: str = get_config(gear_context=context, key=project_key)
    project = group.find_project(project_name)
    if not project:
        raise ConfigurationError(f"No project {group.label}/{project_name}")

    return project


def read_file(*, context: GearContext, source: ProjectAdaptor, key: str) -> bytes:
    """Read the bytes read from the file from the source directory using the
    key to pull the file name from the context config.

    Args:
      context: the gear context
      source: the source project for file
      key: the config key for the filename
    Returns:
      bytes read from the named file
    """
    filename: str = get_config(gear_context=context, key=key)
    return source.read_file(filename)


class ConfigurationError(Exception):
    """Exception class for errors that occur when reading objects from gear
    context config object."""
