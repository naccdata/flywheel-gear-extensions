"""Common code to handle triggering of gears."""
import json
import logging
from json.decoder import JSONDecodeError
from typing import Any, Dict, Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from pydantic import BaseModel, ConfigDict, SerializeAsAny, ValidationError

from gear_execution.gear_execution import GearExecutionError

log = logging.getLogger(__name__)


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
                       configs_file_path: str | Dict[str, Any],
                       configs_class=GearConfigs) -> Optional[Any]:
        """Load GearInfo from configs file.

        Args:
            configs_file_path: The path to the configs JSON file
            configs_class: The specific GearConfigs class to use
        Returns:
            The GearInfo object with gear name and config, if valid
        """
        configs_data = configs_file_path
        try:
            if isinstance(configs_file_path, str):
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


def trigger_gear(proxy: FlywheelProxy, gear_name: str, **kwargs) -> str:
    """Trigger the gear.

    Args:
        proxy: the proxy for the Flywheel instance
        gear_name: the name of the gear to trigger
        kwargs: keyword arguments to pass to gear.run, which include:
            configs: the configs to pass to the gear
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

    log.info(f"Triggering {gear} with the following args:")
    log.info(kwargs)

    return gear.run(**kwargs)
