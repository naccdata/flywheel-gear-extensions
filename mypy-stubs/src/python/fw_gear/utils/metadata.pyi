import json
import typing as t
from fw_gear.file import File as File
from fw_gear.context import GearContext as GearContext
from pathlib import Path


def create_qc_result_dict(name: str, state: str, **data) -> dict:
    ...


def sanitize_periods(
    d: dict | str | list | float | int | None,
) -> dict | str | list | float | int | None:
    ...

class Metadata:

    def __init__(
        self,
        context: GearContext | None = None,
        name_override: str = "",
        version_override: str = "",
    ) -> None:
        ...

    def update_container(
        self, container_type: str, deep: bool = True, **kwargs
    ) -> None:
        ...

    def update_file_metadata(
        self, file_: t.Any, container_type: str, deep: bool = True, **kwargs
    ) -> None:
        ...

    def update_zip_member_count(
        self, path: Path, container_type: str | None = None
    ) -> None:
        ...

    def modify_container_file_info(self, file_: File, **info) -> None:
        ...

    def modify_container_info(self, cont_id: str, **info) -> None:
        ...

    def clean(self) -> None:
        ...

    def log(self) -> None:
        ...

    def write(
        self, directory: Path, fail_on_validation: bool = False, log_meta: bool = True
    ) -> None:
        ...

    def add_qc_result(self, file_: t.Any, name: str, state: str, **data) -> None:
        ...

    def add_qc_result_to_analysis(self, name: str, state: str, **data) -> None:
        ...

    def add_qc_result_via_sdk(self, cont_: t.Any, name: str, state: str, **data):
        ...

    def add_file_tags(self, file_: t.Any, tags: str | t.Iterable[str]) -> None:
        ...

    def pull_job_info(self) -> None:
        ...

    def add_or_update_gear_info(
        self, top_level_keys: list[str], cont_info: t.Any, **kwargs: t.Any
    ) -> dict:
        ...

    def add_gear_info(self, top_level: str, cont_: t.Any, **kwargs: t.Any) -> dict:
        ...


def get_file(
    file_: t.Any, context: GearContext | None, container_type: str | None = None
) -> File:
    ...


class MetadataEncoder(json.JSONEncoder):
    def default(self, obj: t.Any) -> t.Any:
        ...
