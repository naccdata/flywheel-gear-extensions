"""Common code to handle triggering of gears."""
import json
import logging
from json.decoder import JSONDecodeError
from typing import Any, Dict, Literal, Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from pydantic import BaseModel, ConfigDict, SerializeAsAny, ValidationError

from gear_execution.gear_execution import GearExecutionError

log = logging.getLogger(__name__)

BatchMode = Literal['projects', 'files']


class GearConfigs(BaseModel):
    """Class to represent base gear configs."""
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    apikey_path_prefix: str


class GearInfo(BaseModel):
    """Class to represent gear information."""
    model_config = ConfigDict(populate_by_name=True)

    gear_name: str
    configs: SerializeAsAny[GearConfigs]

    @classmethod
    def load_from_file(cls,
                       configs_file_path: str,
                       configs_class=GearConfigs) -> Optional[Any]:
        """Load GearInfo from configs file.

        Args:
            configs_file_path: The path to the configs JSON file
            configs_class: The specific GearConfigs class to use
        Returns:
            The GearInfo object with gear name and config, if valid
        """
        configs_data = {}
        try:
            with open(configs_file_path, mode='r',
                      encoding='utf-8') as file_obj:
                configs_data = json.load(file_obj)
        except (FileNotFoundError, JSONDecodeError, TypeError) as error:
            log.error('Failed to read the gear configs file %s - %s',
                      configs_file_path, error)
            return None

        try:
            configs_data[
                'configs'] = configs_class.model_validate(  # type: ignore
                    configs_data.get('configs', {}))  # type: ignore
            gear_configs = cls.model_validate(configs_data)
        except ValidationError as error:
            log.error('Gear config data not in expected format - %s', error)
            return None

        return gear_configs


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

    @classmethod
    def load_from_file(cls,
                       configs_file_path: str) -> Optional['BatchRunInfo']:
        """Load BatchRunInfo from configs file.

        Args:
            configs_file_path: The path to the batch configs JSON file

        Returns:
            The BatchRunInfo object if valid, else None
        """

        try:
            with open(configs_file_path, mode='r',
                      encoding='utf-8') as file_obj:
                configs_data = json.load(file_obj)
        except (FileNotFoundError, JSONDecodeError, TypeError) as error:
            log.error('Failed to read the batch run configs file %s: %s',
                      configs_file_path, error)
            return None

        try:
            return cls.model_validate(configs_data)
        except ValidationError as error:
            log.error('Batch run configs file %s not in expected format: %s',
                      configs_file_path, error)
            return None

    def get_gear_configs(self,
                         configs_class=GearConfigs,
                         **kwargs) -> Optional[GearConfigs]:
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

        Pass kwargs as source=<source id>, target=<target id>

        Args:
            configs_class(optional): The specific GearConfigs class to use
            kwargs: keyword arguments for each key to be replaced in configs

        Returns:
            Optional[GearConfigs]: Gear configs object of provided config class or None
        """
        if self.substitute:
            log.info('Substituting configs for gear %s', self.gear_name)
            for field, value in self.gear_configs.__dict__.items():
                if isinstance(value, str) and value.startswith(
                        '{{') and value.endswith('}}'):
                    key = value.replace('{', "").replace('}', "")
                    if key not in kwargs:
                        log.error(
                            'Error in substituting config %s: %s - '
                            'substitute value not provided for key %s', field,
                            value, key)
                        return None

                    log.info('Replaced config %s: %s with %s=%s', field, value,
                             key, kwargs[key])
                    self.gear_configs[field] = kwargs[key]

        try:
            return configs_class.model_validate(self.gear_configs)
        except ValidationError as error:
            log.error('Configs for gear %s is not in expected format %s: %s',
                      self.gear_name, configs_class, error)
            return None


def trigger_gear(proxy: FlywheelProxy, gear_name: str, **kwargs) -> str:
    """Trigger the gear.

    Args:
        proxy: the proxy for the Flywheel instance
        gear_name: the name of the gear to trigger
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

    destination = kwargs.get('destination')
    if destination:
        destination = destination.label

    log.info(f"Triggering {gear_name} with the following args:")
    log.info(f"config: {kwargs.get('config')}")
    log.info(f"inputs: {kwargs.get('inputs')}")
    log.info(f"destination: {destination}")
    log.info(f"analysis_label: {kwargs.get('analysis_label')}")
    log.info(f"tags: {kwargs.get('tags')}")

    return gear.run(**kwargs)
