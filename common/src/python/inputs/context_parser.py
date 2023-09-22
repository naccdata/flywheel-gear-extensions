"""Gear context parser for user management."""
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext  # type: ignore


def parse_config(*, gear_context: GearToolkitContext, filename: Optional[str]):
    """Parses gear config for inputs."""
    args = {}
    args['dry_run'] = gear_context.config.get("dry_run", False)
    args['new_only'] = gear_context.config.get("new_only", False)
    if filename:
        args[filename] = gear_context.get_input_path(filename)
    args['admin_group'] = gear_context.config.get('admin_group', 'nacc')
    api_key_dict = gear_context.get_input('api-key')
    if api_key_dict:
        args['api_key'] = api_key_dict.get('key')

    return args
