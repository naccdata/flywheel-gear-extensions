"""Gear context parser for user management."""

from typing import Optional, TypeVar

from fw_gear import GearContext  # type: ignore


def get_api_key(gear_context: GearContext) -> Optional[str]:
    """Returns the api key from the gear context if there is one.

    Args:
      gear_context: the gear context
    Returns:
      the API key if exists in context, None otherwise
    """
    api_key_dict = gear_context.config.get_input("api-key")
    if not api_key_dict:
        raise ConfigParseError(message="No API Key")

    return api_key_dict.get("key")


T = TypeVar("T")


def get_config(
    *, gear_context: GearContext, key: str, default: Optional[T] = None
) -> T:
    """Returns the value for the key in the config of the gear context.

    Args:
      gear_context: context for the gear
      key: name of config value
      default: value for default
    Returns:
      the value for the key if exists in the context config
    Raises:
      ConfigParseError if the key doesn't occur in the context
    """
    value = gear_context.config.opts.get(key, default)
    if value is None:
        raise ConfigParseError(message=f"No value for {key}")

    return value


class ConfigParseError(Exception):
    """Indicates that the gear context config doesn't have an expected key."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def __str__(self) -> str:
        return self.message

    @property
    def message(self):
        """The error message."""
        return self._message
