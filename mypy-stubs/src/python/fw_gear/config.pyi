import flywheel
import typing as t
from .manifest import (
    Manifest as Manifest,
)

from pathlib import Path


class Config:
    def __init__(
        self, client: flywheel.Client | None, config: dict | None, path: Path = ...
    ) -> None:
        ...

    @property
    def opts(self):
        ...

    @property
    def job(self):
        ...

    @property
    def inputs(self):
        ...

    @property
    def destination(self):
        ...


    def update_opts(self, vals: dict):
        ...

    def update_destination(self, dest: dict):
        ...

    def add_input(
        self, name: str, val: str, type_: str = "file", file_: t.Any | None = None
    ):
        ...

    @classmethod
    def default_config_from_manifest(cls, manifest: Path | Manifest) -> Config:
        ...

    def get_input(self, name: str) -> dict | None:
        ...

    def get_input_path(self, name: str) -> Path | None:
        ...

    def get_input_filename(self, name) -> str | None:
        ...

    def get_input_file_object(self, name: str) -> dict | None:
        ...

    def get_input_file_object_value(self, name: str, key: str) -> t.Any:
        ...

    def open_input(self, name: str, mode: str = "r", **kwargs) -> t.IO:
        ...

    def get_destination_container(self):
        ...

    def get_destination_parent(self):
        ...

    def to_json(self, path: Path | None = None):
        ...
