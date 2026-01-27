"""Common code to handle triggering of gears."""

import json
import logging
from json.decoder import JSONDecodeError
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Literal, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from pydantic import (
    BaseModel,
    ConfigDict,
    SerializeAsAny,
    ValidationError,
    model_validator,
)

from gear_execution.gear_execution import GearExecutionError

log = logging.getLogger(__name__)

BatchMode = Literal["projects", "files"]
LocatorType = Literal["matched", "module", "fixed"]


class GearInput(BaseModel):
    label: str
    file_locator: LocatorType
    file_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_iteration_mode(self) -> "GearInput":
        """Validates whether the file_locator type matches with the file_name
        value."""

        if self.file_locator != "matched" and not self.file_name:
            raise ValueError(
                f"Gear input {self.label} not in expected format: "
                f"file_name is required for file_locator of type {self.file_locator}"
            )

        if (
            self.file_locator == "module"
            and self.file_name
            and self.file_name.find(f"${{{self.file_locator}}}") == -1
        ):
            raise ValueError(
                f"Gear input {self.label} not in expected format: "
                f"file_locator type placeholder ${{{self.file_locator}}} "
                f"not present in file_name {self.file_name}"
            )

        return self


class GearConfigs(BaseModel):
    """Class to represent base gear configs."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class CredentialGearConfigs(GearConfigs):
    """Class to represent credentials gear configs."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apikey_path_prefix: str


class GearInputs(BaseModel):
    """Class to represent base gear inputs."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class GearInfo(BaseModel):
    """Class to represent gear information."""

    model_config = ConfigDict(populate_by_name=True)

    gear_name: str
    configs: SerializeAsAny[GearConfigs]
    inputs: Optional[List[GearInput]] = None

    @classmethod
    def load_from_file(
        cls, configs_file_path: str | Path, configs_class=GearConfigs
    ) -> Optional[Any]:
        """Load GearInfo from configs file.

        Args:
            configs_file_path: The path to the configs JSON file
            configs_class: The specific GearConfigs class to use
        Returns:
            The GearInfo object with gear name and config, if valid
        """
        configs_data = {}
        try:
            with Path(configs_file_path).open(
                mode="r", encoding="utf-8-sig"
            ) as file_obj:
                configs_data = json.load(file_obj)
        except (FileNotFoundError, JSONDecodeError, TypeError) as error:
            log.error(
                "Failed to read the gear configs file %s - %s", configs_file_path, error
            )
            return None

        if "configs" not in configs_data:
            log.error("No gear config data found")
            return None

        input_configs = configs_data.get("configs")
        try:
            configs_data["configs"] = configs_class.model_validate(input_configs)
            gear_configs = cls.model_validate(configs_data)
        except ValidationError as error:
            log.error("Gear config data not in expected format - %s", error)
            return None

        return gear_configs

    def get_inputs_by_file_locator_type(
        self, locators: List[LocatorType]
    ) -> Optional[Dict[str, List[GearInput]]]:
        """Get the list of gear inputs by file_locator type.

        Args:
            locators: list of file_locator types

        Returns:
            Dict[str, List[GearInput]](optional): list of gear inputs by locator
        """
        if not self.inputs:
            log.info("No inputs specified for gear %s", self.gear_name)
            return None

        inputs_list: Dict[str, List[GearInput]] = {}
        for gear_input in self.inputs:
            if gear_input.file_locator not in locators:
                continue

            if gear_input.file_locator not in inputs_list:
                inputs_list[gear_input.file_locator] = []
            inputs_list[gear_input.file_locator].append(gear_input)

        return inputs_list


class BatchRunInfo(BaseModel):
    """Class to represent batch run information."""

    model_config = ConfigDict(populate_by_name=True)

    source: str
    target: Optional[str] = None
    substitute: bool = False
    batch_mode: BatchMode
    batch_size: int
    gear_name: str
    gear_configs: Dict[str, Any]
    gear_inputs: Dict[str, Any] = {}

    @classmethod
    def load_from_file(cls, configs_file_path: str) -> Optional["BatchRunInfo"]:
        """Load BatchRunInfo from configs file.

        Args:
            configs_file_path: The path to the batch configs JSON file

        Returns:
            The BatchRunInfo object if valid, else None
        """

        try:
            with open(configs_file_path, mode="r", encoding="utf-8-sig") as file_obj:
                configs_data = json.load(file_obj)
        except (FileNotFoundError, JSONDecodeError, TypeError) as error:
            log.error(
                "Failed to read the batch run configs file %s: %s",
                configs_file_path,
                error,
            )
            return None

        try:
            return cls.model_validate(configs_data)
        except ValidationError as error:
            log.error(
                "Batch run configs file %s not in expected format: %s",
                configs_file_path,
                error,
            )
            return None

    def get_gear_configs(
        self, configs_class=GearConfigs, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Get the gear configs from batch run info gear template. Substitute
        config keys with kwargs if `substitute`=true.

        e.g. If batch run configs defined as follows
        {
            "source": "retrospective-form",
            "target": "accepted",
            "substitute": true,
            "batch_mode": "files",
            "batch_size": 100000,
            "gear_name": "test-gear",
            "gear_configs": {
                "source_id": "{{source}}",
                "destination_id": "{{target}}",
                "dry_run": true
            }
        }

        Pass kwargs as source="source id", target="target id"

        Args:
            configs_class(optional): The specific GearConfigs class to use
            kwargs: keyword arguments for each key to be replaced in configs

        Returns:
            Optional[Dict[str, Any]]: Gear configs dict or None
        """

        configs = self.gear_configs
        if self.substitute:
            log.info("Substituting configs for gear %s", self.gear_name)
            # make a copy
            configs = dict(self.gear_configs)
            for field, value in configs.items():
                if (
                    isinstance(value, str)
                    and value.startswith("{{")
                    and value.endswith("}}")
                ):
                    key = value.replace("{", "").replace("}", "")
                    if key not in kwargs:
                        log.error(
                            "Error in substituting config %s: %s - "
                            "substitute value not provided for key %s",
                            field,
                            value,
                            key,
                        )
                        return None

                    log.info(
                        "Replaced config %s: %s with %s=%s",
                        field,
                        value,
                        key,
                        kwargs[key],
                    )
                    configs[field] = kwargs[key]

        try:
            configs_class.model_validate(configs)
        except ValidationError as error:
            log.error(
                "Configs for gear %s is not in expected format %s: %s",
                self.gear_name,
                configs_class,
                error,
            )
            return None

        return configs

    def get_gear_inputs(
        self,
        center,
        gear_input_class=GearInputs,
    ) -> Dict[str, Any]:
        """Get the gear inputs from batch run info gear template.

        Args:
            center: The source center project
            gear_input_class: GearInputs class

        Returns:
            File inputs, if specified
        """
        if not self.gear_inputs:
            return {}

        results = {}
        for input_file, filename in self.gear_inputs.items():
            file = center.get_file(filename)
            if not file:
                raise GearExecutionError(
                    f"Project {center.group}/{center.label} has no file {filename}"
                )

            results[input_file] = file

        return results


def trigger_gear(
    proxy: FlywheelProxy, gear_name: str, log_args: bool = True, **kwargs
) -> str:
    """Trigger the gear.

    Args:
        proxy: the proxy for the Flywheel instance
        gear_name: the name of the gear to trigger
        log_args: whether to log argument details (default True)
        kwargs: keyword arguments to pass to gear.run, which include:
            config: the configs to pass to the gear
            inputs: The inputs to pass to the gear
            destination: The destination container
            analysis_label: The label of the analysis, if running an analysis gear
            tags: The list of tags to set for the job
    Returns:
        The job or analysis ID of the gear run
    """
    gear = None
    try:
        gear = proxy.lookup_gear(gear_name)
    except ApiException as error:
        raise GearExecutionError(error) from error

    if not gear:
        raise GearExecutionError(f"Failed to find gear: {gear_name}")

    destination = kwargs.get("destination")
    if destination:
        destination = destination.label

    if log_args:
        log.info(f"Triggering {gear_name} with the following args:")
        log.info(f"config: {kwargs.get('config')}")
        log.info(f"inputs: {kwargs.get('inputs')}")
        log.info(f"destination: {destination}")
        log.info(f"analysis_label: {kwargs.get('analysis_label')}")
        log.info(f"tags: {kwargs.get('tags')}")

    return gear.run(**kwargs)


def set_gear_inputs(
    *,
    project: ProjectAdaptor,
    gear_name: str,
    locator: LocatorType,
    gear_inputs_list: List[GearInput],
    gear_inputs: Dict[str, FileEntry],
    module: Optional[str] = None,
    matched_file: Optional[FileEntry] = None,
):
    if locator == "matched" and not matched_file:
        raise ValueError("matched_file is required when locator is 'matched'")

    if locator == "module" and not module:
        raise ValueError("module is required when locator is 'module'")

    for input_info in gear_inputs_list:
        label = input_info.label

        if locator == "matched":
            gear_inputs[label] = matched_file  # type: ignore
            continue

        filename = input_info.file_name
        # Build filename (substitute module if needed)
        if locator == "module":
            if module is None:
                raise ValueError("module must have a value if locator is module")
            filename = Template(input_info.file_name).substitute(  # type: ignore
                {"module": module.lower()}
            )  # type: ignore

        gear_input_file = project.get_file(name=filename)  # type: ignore
        if not gear_input_file:
            raise GearExecutionError(
                f"Cannot find required input file {filename} for gear {gear_name}"
            )

        gear_inputs[label] = gear_input_file
