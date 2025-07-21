"""Defines case converters for pydantic model serialization."""


def kebab_case(name: str) -> str:
    """Converts the name to kebab case.

    Args:
      name: the name to convert
    Returns:
      the name in kebab case
    """
    return name.lower().replace("_", "-")


def camel_case(name: str) -> str:
    """Converts the name to camel case.

    Args:
      name: the name to convert
    Returns:
      the name in camel case
    """
    return "".join([token.title() for token in name.split("_")])
