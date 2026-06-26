import flywheel
import types
import typing as t
from .config import Config as Config
from .manifest import Manifest as Manifest
from .metadata import Metadata as Metadata
from pathlib import Path


class GearContext:

    config: Config
    manifest: Manifest
    metadata: Metadata

    def __init__(
        self,
        gear_path: str | None = "/flywheel/v0",
        manifest_path: str | None = "/flywheel/v0/manifest.json",
        config_path: str | None = "/flywheel/v0/config.json",
        log_metadata: bool = True,
        fail_on_validation: bool = True,
        clean_on_error: bool = False,
    ) -> None:
        ...

    def init_logging(self, default_config_name=None, update_config=None):
        ...

    @property
    def work_dir(self) -> Path:
        ...

    @property
    def output_dir(self) -> Path:
        ...

    @property
    def client(self) -> flywheel.Client | None:
        ...

    def is_fw_context(self) -> bool:
        ...

    def get_client(self) -> flywheel.Client | None:
        ...

    def log_config(self) -> None:
        ...

    def open_output(self, name: str, mode: str = "w", **kwargs) -> t.IO:
        ...

    def get_context_value(self, name: str) -> dict | None:
        ...

    def __enter__(self):
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        _traceback: types.TracebackType | None,
    ) -> None:
        ...
