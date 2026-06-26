import flywheel
import typing as t


def get_container_from_ref(client: flywheel.Client, ref: dict):
    ...


def get_parent(client: flywheel.Client, container):
    ...


def setup_gear_run(
    client: flywheel.Client, gear_name: str, gear_args: dict
) -> tuple[t.Any, dict, dict]:
    ...
